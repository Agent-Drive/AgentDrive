# Design: Download & Open File Locally

**Date:** 2026-04-02
**Status:** Draft
**Scope:** Download files from AgentDrive to local disk via MCP, optionally open in native app

## Problem

AgentDrive stores files in GCS and exposes search over chunked content, but there is no way to retrieve the original file. Users working in Claude Code cannot download a file to read, edit, or open it locally. The storage layer already has `StorageService.download()` and `download_to_tempfile()`, but neither is exposed via REST or MCP.

## Goals

- Download any uploaded file to a structured local directory
- Optionally open the file in the native OS application
- Cache downloads locally with staleness detection
- Expose via both MCP implementations (standalone package and in-process server)

## Non-Goals

- File update/re-upload (deferred to a future spec)
- Web UI download experience
- `list_local_files` or `cleanup` tools

## Design

### REST Endpoint

```
GET /v1/files/{file_id}/download
Auth: Bearer sk-ad-...
Response: 200 OK
  Content-Type: <original file mime type>
  Content-Disposition: attachment; filename="<original filename>"
  Body: streaming bytes from GCS
```

- Lives in `src/agentdrive/routers/files.py` alongside existing file endpoints
- Looks up File record, verifies tenant ownership (same pattern as `GET /v1/files/{file_id}`)
- No status restriction — files are downloadable as soon as they exist in GCS, regardless of ingestion status
- Uses `StreamingResponse` to avoid loading full file into server memory
- Requires a new `StorageService.download_stream()` method that yields chunks via GCS blob's `open()` API — the existing `download()` method loads everything into memory and is not suitable for streaming
- The existing `download()` and `download_to_tempfile()` methods are unchanged

**Error cases:**
- 404: file not found or wrong tenant
- 502: GCS blob missing or storage unavailable (file record exists but blob was deleted or GCS is down)

### MCP Tool

```
Tool: download_file
Inputs:
  file_id:  string (required)  — UUID of the file to download
  open:     boolean (optional, default false) — open in native app after download

Output:
  {
    "local_path": "/Users/.../.agentdrive/files/research/report.xlsx",
    "filename": "report.xlsx",
    "collection": "research",
    "file_size": 48210,
    "already_cached": false
  }
```

**Flow:**

1. Check manifest — is file already downloaded and not stale?
   - If cached and fresh: return cached path, set `already_cached: true`
2. `GET /v1/files/{file_id}` — fetch metadata (filename, collection_id, collection_name, updated_at)
   - Requires adding `updated_at` and `collection_name` to `FileDetailResponse` (currently missing from the Pydantic schema)
3. Resolve collection name from response (or `"default"` if no collection)
4. `GET /v1/files/{file_id}/download` — stream bytes
5. Write to `~/.agentdrive/files/{collection_name}/{filename}`
   - Name collision: append `_{file_id[:8]}` to stem (e.g. `report_a3f2b1c4.xlsx`)
6. Update `.manifest.json`
7. If `open=true`: run `open <path>` (macOS) or `xdg-open <path>` (Linux) via non-blocking `subprocess.Popen` — tool returns immediately, does not wait for the application to close. Windows is out of scope (Claude Code runs on macOS/Linux).
8. Return result

**Staleness check:** Compare `remote_updated_at` in manifest against file's `updated_at` from the API. If remote is newer, re-download and overwrite.

### Local File Structure

```
~/.agentdrive/
  files/
    .manifest.json
    research/                    <- collection name
      quarterly-report.xlsx
      competitor-analysis.pdf
    engineering/                 <- another collection
      api-design.md
    default/                     <- files with no collection
      notes.txt
```

### Manifest Schema

```json
{
  "version": 1,
  "files": {
    "<file_id>": {
      "local_path": "research/quarterly-report.xlsx",
      "filename": "quarterly-report.xlsx",
      "collection": "research",
      "file_id": "<file_id>",
      "file_size": 48210,
      "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      "downloaded_at": "2026-04-02T10:30:00Z",
      "remote_updated_at": "2026-04-01T08:00:00Z"
    }
  }
}
```

**Properties:**
- `local_path` is relative to `~/.agentdrive/files/` for portability
- Keyed by `file_id` for O(1) lookup
- `version` field for future schema migration
- Atomic writes: write to temp file, then rename to `.manifest.json`
- Missing or corrupt manifest treated as empty — re-download as needed, no crash
- Concurrent writes: last writer wins. This can silently drop a manifest entry if two downloads finish simultaneously. Acceptable for single-user local tool — the lost entry is re-downloaded on next access, no data loss. No file locking required.

### Shared Module

Location: `packages/mcp/src/agentdrive_mcp/local_files.py`

Both MCP implementations (standalone and in-process) import from this module. The in-process server at `src/agentdrive/mcp/server.py` imports from `agentdrive_mcp.local_files`. Prerequisite: `packages/mcp` must be installed in the main project's virtualenv (`uv pip install -e packages/mcp`). Verify this is already the case; if not, add it as a dev dependency.

**Functions:**

| Function | Purpose |
|----------|---------|
| `resolve_local_path(filename, collection, file_id)` | Build path under `~/.agentdrive/files/`, handle collisions |
| `read_manifest()` | Load manifest, return empty dict if missing/corrupt |
| `write_manifest(data)` | Atomic write (temp + rename) |
| `is_cached(file_id)` | Check if file exists in manifest and on disk |
| `is_stale(file_id, remote_updated_at)` | Compare manifest timestamp against remote |
| `save_file(file_id, byte_stream, metadata)` | Write bytes to resolved path, update manifest |
| `open_native(local_path)` | `open` (macOS) or `xdg-open` (Linux) via subprocess |

### Changes to Both MCP Servers

Both `packages/mcp/src/agentdrive_mcp/server.py` and `src/agentdrive/mcp/server.py`:

- Add `download_file` to tool list with schema (file_id: string, open: boolean)
- Tool handler calls REST API for metadata + bytes, delegates to `local_files.py` for disk operations
- Both use HTTP — no direct `StorageService` calls from MCP layer

### Schema Changes Required

- **`FileDetailResponse`**: Add `updated_at: datetime` and `collection_name: str | None` fields. The model already has `updated_at` via `TimestampMixin`, it just needs to be serialized. `collection_name` requires a join or eager load of the collection relationship.
- **`StorageService`**: Add `download_stream(gcs_path) -> Generator[bytes]` method using GCS blob's chunked read API.

### What Already Exists (No Changes)

- `StorageService.download()` and `download_to_tempfile()` — unchanged, still used for internal processing
- File model, tenant auth, GCS storage — unchanged
- Existing MCP tools — unchanged

## Testing

- **REST endpoint:** Integration test — upload file, download it, verify bytes match
- **Shared module:** Unit tests for path resolution, manifest CRUD, staleness logic, collision handling, atomic write
- **MCP tool:** Test full flow with mocked HTTP responses — fresh download, cached hit, stale re-download, open flag
- **Edge cases:** Missing manifest, corrupt manifest, file not found, name collision, no collection
