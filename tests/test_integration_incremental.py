"""Integration tests for the incremental ingest pipeline.

These tests exercise the full four-phase pipeline end-to-end using a real
test DB, with StorageService and ChunkerRegistry mocked to avoid I/O.
Enrichment/embedding are no-oped by the autouse fixture in conftest.py.
"""
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select

from agentdrive.chunking.base import ChunkResult, ParentChildChunks
from agentdrive.models.chunk import Chunk, ParentChunk
from agentdrive.models.file import File
from agentdrive.models.file_batch import FileBatch
from agentdrive.models.file_summary import FileSummary
from agentdrive.models.tenant import Tenant
from agentdrive.models.types import BatchStatus, FileStatus
from agentdrive.services.ingest import process_file


def _make_single_chunk_group() -> list[ParentChildChunks]:
    """Return one parent with one child — minimal valid chunk output."""
    return [
        ParentChildChunks(
            parent=ChunkResult(
                content="Parent section content",
                context_prefix="",
                token_count=3,
                content_type="text",
            ),
            children=[
                ChunkResult(
                    content="Child chunk content",
                    context_prefix="",
                    token_count=3,
                    content_type="text",
                ),
            ],
        )
    ]


@pytest_asyncio.fixture
async def tenant(db_session):
    t = Tenant(name="Integration Test Tenant")
    db_session.add(t)
    await db_session.commit()
    await db_session.refresh(t)
    return t


@pytest_asyncio.fixture
async def pending_file(db_session, tenant):
    f = File(
        tenant_id=tenant.id,
        filename="doc.md",
        content_type="markdown",
        gcs_path="tenants/abc/files/def/doc.md",
        file_size=200,
        status=FileStatus.PENDING,
    )
    db_session.add(f)
    await db_session.commit()
    await db_session.refresh(f)
    return f


@pytest.mark.asyncio
@patch("agentdrive.services.ingest.generate_table_aliases", new_callable=AsyncMock)
@patch("agentdrive.services.ingest.enrich_chunks_with_summaries", new_callable=AsyncMock)
@patch("agentdrive.services.ingest.generate_document_summary", new_callable=AsyncMock)
@patch("agentdrive.services.ingest.embed_file_aliases", new_callable=AsyncMock)
@patch("agentdrive.services.ingest.embed_file_chunks", new_callable=AsyncMock)
@patch("agentdrive.services.ingest.StorageService")
@patch("agentdrive.services.ingest.registry")
async def test_full_pipeline_small_doc(
    mock_registry,
    mock_storage_cls,
    mock_embed_chunks,
    mock_embed_aliases,
    mock_gen_summary,
    mock_enrich,
    mock_aliases,
    pending_file,
    db_session,
):
    """Full pipeline with one chunk group: file ends READY, batch COMPLETED, summary present."""
    mock_storage = MagicMock()
    mock_storage.download_to_tempfile.return_value = Path("/tmp/fake.md")
    mock_storage_cls.return_value = mock_storage

    mock_registry.chunk_file.return_value = _make_single_chunk_group()

    mock_gen_summary.return_value = {"document_summary": "Test summary.", "section_summaries": []}
    mock_enrich.side_effect = lambda groups, **kwargs: groups
    mock_aliases.return_value = []
    mock_embed_chunks.return_value = 0
    mock_embed_aliases.return_value = 0

    await process_file(pending_file.id, db_session)

    await db_session.refresh(pending_file)

    # File-level assertions
    assert pending_file.status == FileStatus.READY
    assert pending_file.total_batches == 1
    assert pending_file.current_phase is None

    # Exactly 1 Chunk in DB with correct content
    chunk_result = await db_session.execute(
        select(Chunk).where(Chunk.file_id == pending_file.id)
    )
    chunks = chunk_result.scalars().all()
    assert len(chunks) == 1
    assert chunks[0].content == "Child chunk content"

    # Exactly 1 FileBatch with all statuses COMPLETED
    batch_result = await db_session.execute(
        select(FileBatch).where(FileBatch.file_id == pending_file.id)
    )
    batches = batch_result.scalars().all()
    assert len(batches) == 1
    batch = batches[0]
    assert batch.chunking_status == BatchStatus.COMPLETED
    assert batch.enrichment_status == BatchStatus.COMPLETED
    assert batch.embedding_status == BatchStatus.COMPLETED

    # Exactly 1 FileSummary
    summary_result = await db_session.execute(
        select(FileSummary).where(FileSummary.file_id == pending_file.id)
    )
    summary = summary_result.scalar_one_or_none()
    assert summary is not None


@pytest.mark.asyncio
@patch("agentdrive.services.ingest.generate_table_aliases", new_callable=AsyncMock)
@patch("agentdrive.services.ingest.enrich_chunks_with_summaries", new_callable=AsyncMock)
@patch("agentdrive.services.ingest.generate_document_summary", new_callable=AsyncMock)
@patch("agentdrive.services.ingest.embed_file_aliases", new_callable=AsyncMock)
@patch("agentdrive.services.ingest.embed_file_chunks", new_callable=AsyncMock)
@patch("agentdrive.services.ingest.StorageService")
@patch("agentdrive.services.ingest.registry")
async def test_full_pipeline_resume_after_failure(
    mock_registry,
    mock_storage_cls,
    mock_embed_chunks,
    mock_embed_aliases,
    mock_gen_summary,
    mock_enrich,
    mock_aliases,
    pending_file,
    db_session,
):
    """Resume a previously FAILED file: Phase 1 skipped, file ends READY."""
    # Simulate a previous run that completed chunking but failed afterward
    pending_file.status = FileStatus.FAILED
    pending_file.total_batches = 1
    await db_session.commit()

    # Pre-create the batch with chunking already COMPLETED
    batch = FileBatch(
        file_id=pending_file.id,
        batch_index=0,
        chunking_status=BatchStatus.COMPLETED,
        enrichment_status=BatchStatus.PENDING,
        embedding_status=BatchStatus.PENDING,
        chunk_count=1,
    )
    db_session.add(batch)

    # Pre-create the parent + child chunks that Phase 1 would have produced
    parent = ParentChunk(
        file_id=pending_file.id,
        content="Existing parent content",
        token_count=3,
    )
    db_session.add(parent)
    await db_session.flush()

    chunk = Chunk(
        file_id=pending_file.id,
        parent_chunk_id=parent.id,
        chunk_index=0,
        content="Existing child content",
        context_prefix="",
        token_count=3,
        content_type="text",
    )
    db_session.add(chunk)
    await db_session.commit()

    # Setup mocks for Phase 2+
    mock_gen_summary.return_value = {"document_summary": "Resumed summary.", "section_summaries": []}
    mock_enrich.side_effect = lambda groups, **kwargs: groups
    mock_aliases.return_value = []
    mock_embed_chunks.return_value = 0
    mock_embed_aliases.return_value = 0

    await process_file(pending_file.id, db_session)

    # Phase 1 must NOT have run — chunker should not be called
    mock_registry.chunk_file.assert_not_called()

    # File should complete successfully
    await db_session.refresh(pending_file)
    assert pending_file.status == FileStatus.READY
