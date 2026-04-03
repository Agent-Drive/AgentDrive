"""E2E test: PDF upload → DocAI chunking → Baseten enrichment → Voyage embedding.

Requires real API keys in .env, gcloud auth, and dev DB on port 5433.

Run: uv run pytest tests/e2e/ -v
"""

import asyncio
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

PDF_PATH = Path(__file__).parent.parent.parent / "test_nexus_annual_report.pdf"
POLL_INTERVAL = 5
POLL_TIMEOUT = 180


@pytest.mark.asyncio
async def test_pdf_upload_enrichment_and_embedding(
    async_client: AsyncClient,
    api_key: str,
    db_session: AsyncSession,
):
    """Upload a PDF and verify the full pipeline: chunking, enrichment, and embedding."""
    assert PDF_PATH.exists(), f"Test PDF not found: {PDF_PATH}"

    # Upload
    with open(PDF_PATH, "rb") as f:
        response = await async_client.post(
            "/v1/files",
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": ("test_nexus_annual_report.pdf", f, "application/pdf")},
        )
    assert response.status_code == 202, f"Upload failed: {response.text}"
    file_id = response.json()["id"]

    # Poll until ready or failed
    elapsed = 0
    status = "pending"
    while elapsed < POLL_TIMEOUT:
        await asyncio.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL
        resp = await async_client.get(
            f"/v1/files/{file_id}",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        status = resp.json()["status"]
        if status in ("ready", "failed"):
            break

    assert status == "ready", f"Pipeline did not complete within {POLL_TIMEOUT}s. Final status: {status}"

    # Query chunks with a fresh DB connection to see committed data from ingestion worker
    from sqlalchemy.ext.asyncio import create_async_engine as _create_engine
    from sqlalchemy.orm import sessionmaker as _sessionmaker
    from agentdrive.config import settings as _settings

    fresh_engine = _create_engine(_settings.database_url)
    fresh_session_cls = _sessionmaker(fresh_engine, class_=AsyncSession, expire_on_commit=False)
    async with fresh_session_cls() as fresh_session:
        # Note: embedding is a pgvector halfvec column — use IS NOT NULL instead of selecting raw value
        result = await fresh_session.execute(
            text("""
                SELECT content, context_prefix, content_type,
                       embedding IS NOT NULL as has_embedding
                FROM chunks WHERE file_id = :fid ORDER BY chunk_index
            """),
            {"fid": file_id},
        )
        chunks = result.fetchall()
    await fresh_engine.dispose()

    # Basic assertions
    assert len(chunks) > 0, "No chunks created"

    # All chunks have content
    for i, chunk in enumerate(chunks):
        assert chunk[0] and len(chunk[0]) > 0, f"Chunk {i} has empty content"

    # Parent chunks (content_type='text') have context prefixes from enrichment
    text_chunks = [c for c in chunks if c[2] == "text"]
    assert len(text_chunks) > 0, "No text chunks found"
    enriched = [c for c in text_chunks if c[1] and len(c[1]) > 0]
    assert len(enriched) > 0, f"No chunks have context_prefix. Enrichment (Baseten/Gemma 4) may have failed."
    assert len(enriched) == len(text_chunks), (
        f"Only {len(enriched)}/{len(text_chunks)} text chunks have context_prefix"
    )

    # All chunks have embeddings
    embedded = [c for c in chunks if c[3] is True]
    assert len(embedded) > 0, f"No chunks have embeddings. Voyage AI may have failed."
    assert len(embedded) == len(chunks), (
        f"Only {len(embedded)}/{len(chunks)} chunks have embeddings"
    )
