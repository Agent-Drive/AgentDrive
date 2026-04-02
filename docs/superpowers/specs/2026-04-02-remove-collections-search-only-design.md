# Remove Collections — Search-Only Architecture

**Date:** 2026-04-02
**Status:** Approved
**Approach:** A (clean break)

## Problem

The current collection system puts organizational burden on the user. Users must create collections, name them, and pass the right IDs during upload. Files uploaded without a collection are orphaned. This friction exists on the write path, but the value of organization is only realized on the read path (search/retrieval).

## Decision

Remove collections entirely. The only way to find files is search. Upload is frictionless — just the file, nothing else. This is the right primitive for an agent-native product. Agents don't browse folders — they search.

For the future web UI, the interface is a Spotlight-style search bar with a recent files list — not a file browser.

## Principles

- **Search is the only navigation.** No folders, no taxonomy, no tags-for-organization.
- **Zero friction on upload.** File goes in, that's it.
- **One search engine, two clients.** MCP tools and future web UI hit the same `POST /v1/search` endpoint. Same quality, same ranking.
- **Enrichment stays.** Haiku contextual enrichment during ingestion exists to improve search quality, not for organization. It remains unchanged.
- **Local cache is just a cache.** Flat directory, not a browsable file system.

## Data Model Changes

### Drop

- `collections` table (entire table)
- `collection_id` column from `files` table
- `idx_files_collection` index
- `idx_collections_tenant` index

### Unchanged

- `files` table (minus `collection_id`)
- `chunks`, `chunk_aliases` tables
- `tenants` table

### Migration

Alembic migration to:
1. Drop `collection_id` FK and column from `files`
2. Drop `collections` table
3. Drop related indexes

## API Changes

### Removed Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/v1/collections` | Create collection |
| GET | `/v1/collections` | List collections |
| DELETE | `/v1/collections/{id}` | Delete collection |

### Modified Endpoints

**POST /v1/files** (upload)
- Remove: `collection` form parameter

**POST /v1/files/upload-url** (large file upload)
- Remove: `collection_id` from request body

**GET /v1/files** (list)
- Remove: `collection` query parameter
- Returns all tenant files sorted by recency

**POST /v1/search**
- Remove: `collections` parameter from request body
- Keep: `content_types` filter (still useful)

**GET /v1/files/{id}** (detail)
- Remove: `collection_id`, `collection_name` from response

### Unchanged Endpoints

- `GET /v1/files/{id}/download`
- `POST /v1/files/{id}/complete`
- `DELETE /v1/files/{id}`
- `GET /v1/chunks/{id}`
- `POST /v1/auth/keys`, `GET /v1/auth/keys`, `DELETE /v1/auth/keys/{id}`

## MCP Tool Changes

### Removed Tools

- `create_collection`
- `delete_collection`
- `list_collections`

### Modified Tools

| Tool | Change |
|------|--------|
| `upload_file` | Remove `collection` parameter |
| `search` | Remove `collection` parameter |
| `list_files` | Remove `collection` parameter |

### Unchanged Tools

- `get_file_status`, `delete_file`, `get_chunk`, `download_file`
- `create_api_key`, `list_api_keys`, `revoke_api_key`

## Search Engine

No changes to the search pipeline:

```
Query -> Embed (Voyage) -> Vector search --+
                                           +--> RRF Fusion -> Cohere Rerank -> Results
Query -> BM25 (tsvector) -----------------+
```

Changes:
- Remove `collections` parameter from `vector_search()`, `bm25_search()`, `SearchEngine.search()`
- Remove `f.collection_id = ANY(:collections)` WHERE clauses
- `content_types` filter remains

## Local File Cache

### Before

```
~/.agentdrive/files/
  default/
    test_nexus_report_d547c40d.pdf
  series-a/
    nda_head_discovery_1aee3191.pdf
  .manifest.json
```

### After

```
~/.agentdrive/files/
  d547c40d_test_nexus_annual_report.pdf
  1aee3191_nda_head_discovery.pdf
  .manifest.json
```

Changes in `local_files.py`:
- Path: `{file_id_short}_{filename}` — no subdirectories
- Remove `collection` from manifest entries
- Download handler: stop reading `collection_name` from metadata

## Files to Delete

- `src/agentdrive/models/collection.py`
- `src/agentdrive/routers/collections.py`
- `src/agentdrive/schemas/collections.py`
- `tests/test_collections.py`

## Files to Modify

| File | Change |
|------|--------|
| `alembic/versions/` | New migration: drop collection_id, drop collections table |
| `src/agentdrive/models/__init__.py` | Remove Collection import |
| `src/agentdrive/models/file.py` | Remove collection_id, collection relationship |
| `src/agentdrive/models/tenant.py` | Remove `collections` relationship |
| `src/agentdrive/schemas/files.py` | Remove collection_id, collection_name |
| `src/agentdrive/schemas/search.py` | Remove collections param |
| `src/agentdrive/routers/files.py` | Remove collection param from upload + list |
| `src/agentdrive/routers/search.py` | Remove collections param |
| `src/agentdrive/main.py` | Remove collections router registration |
| `src/agentdrive/search/engine.py` | Remove collections param |
| `src/agentdrive/search/vector.py` | Remove collections filter |
| `src/agentdrive/search/bm25.py` | Remove collections filter |
| `src/agentdrive/mcp/server.py` | Remove 3 tools, strip collection from others |
| `packages/mcp/src/agentdrive_mcp/server.py` | Same changes |
| `packages/mcp/src/agentdrive_mcp/local_files.py` | Flatten cache structure |
| `tests/conftest.py` | Remove collection fixtures |
| `tests/test_files.py` | Remove collection references |
| `tests/mcp/test_server.py` | Remove collection tool assertions |
| `tests/test_schema_progress.py` | Remove `collection_id` from test data |
| `tests/test_prefix_auth.py` | Replace `/v1/collections` with another endpoint in auth tests |
| `packages/mcp/tests/test_local_files.py` | Remove collection from manifest entries, flatten directory tests |
| `packages/mcp/tests/test_download_tool.py` | Remove `collection` key from mock metadata |
| `CLAUDE.md` | Update architecture diagram and model descriptions |

## Notes

- Python stdlib `collections.abc` imports (in `services/storage.py`, `db/session.py`) are unrelated — no changes needed.
- Old migration `19f589d55e82_add_updated_at` references the `collections` table name. Since migrations run forward from current state in production and tests drop/recreate all tables, this is not a blocker. If running migrations from scratch becomes necessary, patch that migration to skip missing tables.
- `test_prefix_auth.py` tests auth prefix matching, not collections. The `/v1/collections` endpoint is just the test target — replace it with `/v1/files` or another existing endpoint.

## Data Cleanup

- Clear all existing data (files + chunks) from the database. No production data exists — this is test data only.
- Clear local cache: `rm -rf ~/.agentdrive/files/*`
