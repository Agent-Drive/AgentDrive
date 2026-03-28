"""Tests for the four-phase incremental ingest pipeline."""
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

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


def _make_chunk_groups() -> list[ParentChildChunks]:
    """Create a minimal set of chunk groups for testing."""
    return [
        ParentChildChunks(
            parent=ChunkResult(
                content="Parent content section one",
                context_prefix="Section 1",
                token_count=5,
                content_type="text",
            ),
            children=[
                ChunkResult(
                    content="Child content A",
                    context_prefix="Section 1",
                    token_count=3,
                    content_type="text",
                ),
                ChunkResult(
                    content="Child content B",
                    context_prefix="Section 1",
                    token_count=3,
                    content_type="text",
                ),
            ],
        ),
    ]


@pytest_asyncio.fixture
async def tenant(db_session):
    t = Tenant(name="Test Tenant")
    db_session.add(t)
    await db_session.commit()
    await db_session.refresh(t)
    return t


@pytest_asyncio.fixture
async def test_file(db_session, tenant):
    f = File(
        tenant_id=tenant.id,
        filename="test.md",
        content_type="markdown",
        gcs_path="tenants/abc/files/def/test.md",
        file_size=100,
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
async def test_full_pipeline_creates_batches_and_ready(
    mock_registry,
    mock_storage_cls,
    mock_embed_chunks,
    mock_embed_aliases,
    mock_gen_summary,
    mock_enrich,
    mock_aliases,
    test_file,
    db_session,
):
    """Full pipeline with mocked externals: file ends READY with 1 batch, all COMPLETED."""
    # Setup storage mock
    mock_storage = MagicMock()
    mock_storage.download_to_tempfile.return_value = Path("/tmp/fake.md")
    mock_storage_cls.return_value = mock_storage

    # Setup chunker mock
    mock_registry.chunk_file.return_value = _make_chunk_groups()

    # Setup enrichment mocks
    mock_gen_summary.return_value = {
        "document_summary": "A test document.",
        "section_summaries": [{"heading": "S1", "summary": "First section."}],
    }
    mock_enrich.side_effect = lambda groups, **kwargs: groups
    mock_aliases.return_value = []
    mock_embed_chunks.return_value = 0
    mock_embed_aliases.return_value = 0

    await process_file(test_file.id, db_session)

    # Verify file status
    await db_session.refresh(test_file)
    assert test_file.status == FileStatus.READY

    # Verify exactly 1 batch with all statuses COMPLETED
    result = await db_session.execute(
        select(FileBatch).where(FileBatch.file_id == test_file.id)
    )
    batches = result.scalars().all()
    assert len(batches) == 1
    batch = batches[0]
    assert batch.chunking_status == BatchStatus.COMPLETED
    assert batch.enrichment_status == BatchStatus.COMPLETED
    assert batch.embedding_status == BatchStatus.COMPLETED
    assert batch.chunk_count == 2

    # Verify summary exists
    result = await db_session.execute(
        select(FileSummary).where(FileSummary.file_id == test_file.id)
    )
    summary = result.scalar_one_or_none()
    assert summary is not None
    assert summary.document_summary == "A test document."


@pytest.mark.asyncio
@patch("agentdrive.services.ingest.generate_table_aliases", new_callable=AsyncMock)
@patch("agentdrive.services.ingest.enrich_chunks_with_summaries", new_callable=AsyncMock)
@patch("agentdrive.services.ingest.generate_document_summary", new_callable=AsyncMock)
@patch("agentdrive.services.ingest.embed_file_aliases", new_callable=AsyncMock)
@patch("agentdrive.services.ingest.embed_file_chunks", new_callable=AsyncMock)
@patch("agentdrive.services.ingest.StorageService")
@patch("agentdrive.services.ingest.registry")
async def test_resume_from_phase2_skips_chunking(
    mock_registry,
    mock_storage_cls,
    mock_embed_chunks,
    mock_embed_aliases,
    mock_gen_summary,
    mock_enrich,
    mock_aliases,
    test_file,
    db_session,
):
    """Pre-create batch+chunks, verify Phase 1 skipped, Phase 2+ runs."""
    # Pre-create batch with COMPLETED chunking
    batch = FileBatch(
        file_id=test_file.id,
        batch_index=0,
        chunking_status=BatchStatus.COMPLETED,
        enrichment_status=BatchStatus.PENDING,
        embedding_status=BatchStatus.PENDING,
        chunk_count=1,
    )
    db_session.add(batch)

    await db_session.flush()

    # Pre-create a parent chunk and child chunk with batch_id
    parent = ParentChunk(
        file_id=test_file.id,
        batch_id=batch.id,
        content="Existing parent content",
        token_count=4,
    )
    db_session.add(parent)
    await db_session.flush()

    chunk = Chunk(
        file_id=test_file.id,
        parent_chunk_id=parent.id,
        batch_id=batch.id,
        chunk_index=0,
        content="Existing child content",
        context_prefix="",
        token_count=3,
        content_type="text",
    )
    db_session.add(chunk)
    await db_session.commit()

    # Setup mocks for Phase 2+
    mock_gen_summary.return_value = {
        "document_summary": "Summary.",
        "section_summaries": [],
    }
    mock_enrich.side_effect = lambda groups, **kwargs: groups
    mock_aliases.return_value = []
    mock_embed_chunks.return_value = 0
    mock_embed_aliases.return_value = 0

    await process_file(test_file.id, db_session)

    # Phase 1 should NOT have been called (chunk_file not invoked)
    mock_registry.chunk_file.assert_not_called()

    # File should be READY
    await db_session.refresh(test_file)
    assert test_file.status == FileStatus.READY


@pytest.mark.asyncio
@patch("agentdrive.services.ingest.generate_table_aliases", new_callable=AsyncMock)
@patch("agentdrive.services.ingest.enrich_chunks_with_summaries", new_callable=AsyncMock)
@patch("agentdrive.services.ingest.generate_document_summary", new_callable=AsyncMock)
@patch("agentdrive.services.ingest.embed_file_aliases", new_callable=AsyncMock)
@patch("agentdrive.services.ingest.embed_file_chunks", new_callable=AsyncMock)
@patch("agentdrive.services.ingest.StorageService")
@patch("agentdrive.services.ingest.registry")
async def test_zero_chunks_marks_failed(
    mock_registry,
    mock_storage_cls,
    mock_embed_chunks,
    mock_embed_aliases,
    mock_gen_summary,
    mock_enrich,
    mock_aliases,
    test_file,
    db_session,
):
    """Chunker returns empty list: file marked FAILED, Phase 2 not called."""
    mock_storage = MagicMock()
    mock_storage.download_to_tempfile.return_value = Path("/tmp/fake.md")
    mock_storage_cls.return_value = mock_storage

    # Chunker returns empty
    mock_registry.chunk_file.return_value = []

    await process_file(test_file.id, db_session)

    # File should be FAILED
    await db_session.refresh(test_file)
    assert test_file.status == FileStatus.FAILED

    # Phase 2 should NOT have been called
    mock_gen_summary.assert_not_called()
    mock_enrich.assert_not_called()
