# Agent Drive

Agent-native file intelligence layer. Ingests files, chunks them semantically, embeds via Voyage AI, and provides hybrid search (vector + BM25 + Cohere reranking) via REST API and MCP.

## Commands

```bash
# Setup
uv venv && uv pip install -e ".[dev]"
cp .env.example .env  # fill in API keys

# Run server
uv run uvicorn agentdrive.api.app:app --port 8080

# Run web (marketing + dashboard)
cd web && pnpm dev

# Run tests (requires pgvector on port 5434)
uv run pytest tests/ -v

# Run a single test
uv run pytest tests/engine/pipeline/enrichment/test_client.py::test_generate_context -v

# Run migrations
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5434/agentdrive uv run alembic upgrade head

# Start test DB
docker run -d --name agentdrive-test-db -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=agentdrive_test -p 5434:5432 pgvector/pgvector:pg16
```

## Architecture

```
src/agentdrive/
├── config.py            # Pydantic settings from .env
├── api/                 # HTTP door
│   ├── app.py
│   ├── dependencies.py
│   ├── files/           # router, service, schemas
│   ├── search/
│   ├── auth/
│   └── mcp/             # hosted MCP (HTTP + WorkOS OAuth)
└── engine/              # data, pipeline, search

web/                     # Next.js marketing (/) + dashboard (/dashboard)
```

## Gotchas

- **Use `uv` always** — never pip. `uv run`, `uv pip install`.
- **SQLAlchemy `metadata` conflict** — models use `extra_metadata` as the Python attribute (DB column is still `metadata`). Pydantic schemas use `validation_alias="extra_metadata"`.
- **pgvector columns not in ORM** — `chunks.embedding` and `chunks.embedding_full` are added via Alembic migration, not SQLAlchemy model. Updated via raw SQL `text()`.
- **Two DB containers** — dev DB on port 5433 (`agentdrive-db`), test DB on port 5434 (`agentdrive-test-db`). Tests connect to 5434, local server uses 5433. Don't mix them up.
- **Alembic needs psycopg2** — `uv pip install psycopg2-binary` for sync driver. The async app uses asyncpg.
- **Code chunks use separate embedding space** — `voyage-code-3` vs `voyage-4`. Separate filtered HNSW indexes in the same `chunks` table.
- **Enrichment mocked in all tests** — conftest.py has an autouse fixture that no-ops `enrich_chunks`, `generate_table_aliases`, `embed_file_chunks`, and `embed_file_aliases`. Enrichment uses Google AI Studio (OpenAI-compatible API) with Gemini 2.5 Flash.

## External APIs

| Service | Purpose | Env Var |
|---------|---------|---------|
| Voyage AI | Embedding (voyage-4, voyage-code-3, voyage-4-lite) | `VOYAGE_API_KEY` |
| Cohere | Reranking (rerank-v3.5) | `COHERE_API_KEY` |
| Google AI Studio | Contextual enrichment (Gemini 2.5 Flash) | `ENRICHMENT_API_KEY` |
| GCP/GCS | File storage | `gcloud auth application-default login` |
| GCP Document AI | PDF parsing/OCR | `DOCAI_PROCESSOR_ID`, `GCP_PROJECT_ID` |

## Git Worktrees

- **Worktree directory:** `.claude/worktrees/` — always use this location for feature branches
- **Branch naming:** `feat/<feature-name>` or `fix/<feature-name>`

## Testing

- Tests require pgvector Docker container on port 5434
- External APIs (Voyage, Cohere, Google AI Studio, GCS) are mocked in all tests
- `conftest.py` drops and recreates all tables per test for isolation
- Integration tests in `tests/api/test_files.py` use real DB
