# E2E PDF Pipeline Test

**Date:** 2026-04-03
**Status:** Approved

## Goal

A pytest integration test that verifies the full PDF ingestion pipeline end-to-end: upload → DocAI chunking → Baseten/Gemma 4 enrichment → Voyage AI embedding. Uses real external APIs (no mocks).

## Structure

```
tests/e2e/
├── conftest.py          # DB session, async client, API key seeding. NO autouse mocks.
└── test_pdf_pipeline.py  # Single test: upload → poll → assert
```

## How to Run

```bash
# E2E tests only (requires real API keys in .env)
uv run pytest tests/e2e/ -v

# Normal tests (e2e excluded)
uv run pytest tests/ -v --ignore=tests/e2e
```

## conftest.py

Provides:
- `db_session` — async SQLAlchemy session to dev DB on port 5433
- `async_client` — `httpx.AsyncClient` mounted on the FastAPI app (no server process needed)
- `api_key` — seeds a test tenant + API key in the DB, yields the raw key, cleans up after

Uses the dev DB (`DATABASE_URL` from `.env`) since the test needs real GCS/DocAI access. Does NOT include autouse mocks — the whole point is hitting real APIs.

## test_pdf_pipeline.py

Single test function: `test_pdf_upload_enrichment_and_embedding`

### Flow

1. Upload `test_nexus_annual_report.pdf` via `POST /v1/files` with the seeded API key
2. Assert 202 response
3. Poll `GET /v1/files/{id}` every 5 seconds, max 120 seconds
4. Assert file status is `ready` (not `failed`)
5. Query `chunks` table directly via DB session for this file
6. Assert at least 1 chunk exists
7. Assert all chunks have non-empty `content`
8. Assert all parent chunks have non-empty `context_prefix` (enrichment worked)
9. Assert all chunks have non-null `embedding` column (embedding worked)

### Cleanup

After assertions (pass or fail), delete:
- Chunks for this file
- File batches for this file
- The file record itself
- The test API key and tenant

## Assertions

| What | Assertion | Proves |
|------|-----------|--------|
| Upload | 202 status | API accepts file |
| Polling | Status reaches `ready` within 120s | Full pipeline completes |
| Chunks | At least 1 chunk exists | DocAI chunking worked |
| Content | All chunks have non-empty `content` | Chunks have text |
| Context prefix | Parent chunks have non-empty `context_prefix` | Baseten/Gemma 4 enrichment worked |
| Embedding | Chunks have non-null `embedding` | Voyage AI embedding worked |

## Dependencies

- Real API keys in `.env`: `BASETEN_API_KEY`, `VOYAGE_API_KEY`, `DOCAI_PROCESSOR_ID`, `GCP_PROJECT_ID`
- `gcloud auth application-default login` for GCS + DocAI
- Dev DB running on port 5433
- Test PDF at repo root: `test_nexus_annual_report.pdf`

## Files Changed

| File | Change |
|------|--------|
| `tests/e2e/__init__.py` | New empty file |
| `tests/e2e/conftest.py` | New: DB session, async client, API key fixture |
| `tests/e2e/test_pdf_pipeline.py` | New: single e2e test |
