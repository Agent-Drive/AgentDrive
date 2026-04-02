# Agent Drive

Agent-native file intelligence layer. Ingests files, chunks them semantically, embeds via Voyage AI, and provides hybrid search (vector + BM25 + Cohere reranking) via REST API and MCP.

## Commands

```bash
# Setup
uv venv && uv pip install -e ".[dev]"
cp .env.example .env  # fill in API keys

# Run server
uv run uvicorn agentdrive.main:app --port 8080

# Run tests (requires pgvector on port 5434)
uv run pytest tests/ -v

# Run migrations
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5434/agentdrive uv run alembic upgrade head

# Start test DB
docker run -d --name agentdrive-test-db -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=agentdrive_test -p 5434:5432 pgvector/pgvector:pg16
```

## Architecture

```
src/agentdrive/
├── main.py              # FastAPI app entrypoint
├── config.py            # Pydantic settings from .env
├── dependencies.py      # Auth dependency (API key → tenant)
├── routers/             # REST endpoints (files, collections, search)
├── models/              # SQLAlchemy models (tenant, file, chunk, collection, chunk_alias)
├── schemas/             # Pydantic request/response schemas
├── services/            # Business logic (ingest, storage, auth)
├── chunking/            # File-type-specific chunkers + registry
├── embedding/           # Voyage AI client + batch pipeline
├── enrichment/          # Haiku contextual enrichment + table questions
├── search/              # Vector search, BM25, RRF fusion, Cohere rerank
└── mcp/                 # MCP server (9 tools for agent integration)
```

## Gotchas

- **Use `uv` always** — never pip. `uv run`, `uv pip install`.
- **SQLAlchemy `metadata` conflict** — models use `extra_metadata` as the Python attribute (DB column is still `metadata`). Pydantic schemas use `validation_alias="extra_metadata"`.
- **pgvector columns not in ORM** — `chunks.embedding` and `chunks.embedding_full` are added via Alembic migration, not SQLAlchemy model. Updated via raw SQL `text()`.
- **Test DB on port 5434** — not 5432. Tests connect to `postgresql+asyncpg://postgres:postgres@localhost:5434/agentdrive_test`.
- **Alembic needs psycopg2** — `uv pip install psycopg2-binary` for sync driver. The async app uses asyncpg.
- **Code chunks use separate embedding space** — `voyage-code-3` vs `voyage-4`. Separate filtered HNSW indexes in the same `chunks` table.
- **Enrichment mocked in all tests** — conftest.py has an autouse fixture that no-ops `enrich_chunks`, `generate_table_aliases`, `embed_file_chunks`, and `embed_file_aliases`.

## External APIs

| Service | Purpose | Env Var |
|---------|---------|---------|
| Voyage AI | Embedding (voyage-4, voyage-code-3, voyage-4-lite) | `VOYAGE_API_KEY` |
| Cohere | Reranking (rerank-v3.5) | `COHERE_API_KEY` |
| Anthropic | Contextual enrichment (Haiku) | `ANTHROPIC_API_KEY` |
| GCP/GCS | File storage | `gcloud auth application-default login` |

## Git Worktrees

- **Worktree directory:** `.claude/worktrees/` — always use this location for feature branches
- **Branch naming:** `feat/<feature-name>` or `fix/<feature-name>`

## Testing

- Tests require pgvector Docker container on port 5434
- External APIs (Voyage, Cohere, Anthropic, GCS) are mocked in all tests
- `conftest.py` drops and recreates all tables per test for isolation
- Integration tests in `test_files.py` and `test_collections.py` use real DB
