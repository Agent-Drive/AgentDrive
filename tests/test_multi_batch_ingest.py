"""Tests for multi-batch ingest pipeline: batch_id on chunks, per-batch enrichment, resume."""
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


def _make_chunk_groups() -> list[ParentChildChunks]:
    return [
        ParentChildChunks(
            parent=ChunkResult(
                content="Parent content",
                context_prefix="",
                token_count=3,
                content_type="text",
            ),
            children=[
                ChunkResult(
                    content="Child A",
                    context_prefix="",
                    token_count=2,
                    content_type="text",
                ),
                ChunkResult(
                    content="Child B",
                    context_prefix="",
                    token_count=2,
                    content_type="text",
                ),
            ],
        ),
    ]


@pytest_asyncio.fixture
async def tenant(db_session):
    t = Tenant(name="Multi-Batch Test Tenant")
    db_session.add(t)
    await db_session.commit()
    await db_session.refresh(t)
    return t


@pytest_asyncio.fixture
async def test_file(db_session, tenant):
    f = File(
        tenant_id=tenant.id,
        filename="multi.md",
        content_type="markdown",
        gcs_path="tenants/abc/files/def/multi.md",
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
async def test_phase1_sets_batch_id(
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
    """All chunks and parent_chunks created in Phase 1 have batch_id set."""
    mock_storage = MagicMock()
    mock_storage.download_to_tempfile.return_value = Path("/tmp/fake.md")
    mock_storage_cls.return_value = mock_storage

    mock_registry.chunk_file.return_value = _make_chunk_groups()
    mock_gen_summary.return_value = {"document_summary": "", "section_summaries": []}
    mock_enrich.side_effect = lambda groups, **kwargs: groups
    mock_aliases.return_value = []
    mock_embed_chunks.return_value = 0
    mock_embed_aliases.return_value = 0

    await process_file(test_file.id, db_session)

    # Get the batch
    batch_result = await db_session.execute(
        select(FileBatch).where(FileBatch.file_id == test_file.id)
    )
    batches = batch_result.scalars().all()
    assert len(batches) == 1
    batch = batches[0]

    # All parent_chunks must have batch_id
    parent_result = await db_session.execute(
        select(ParentChunk).where(ParentChunk.file_id == test_file.id)
    )
    parents = parent_result.scalars().all()
    assert len(parents) > 0
    for p in parents:
        assert p.batch_id == batch.id, f"ParentChunk {p.id} missing batch_id"

    # All chunks must have batch_id
    chunk_result = await db_session.execute(
        select(Chunk).where(Chunk.file_id == test_file.id)
    )
    chunks = chunk_result.scalars().all()
    assert len(chunks) == 2
    for c in chunks:
        assert c.batch_id == batch.id, f"Chunk {c.id} missing batch_id"


@pytest.mark.asyncio
@patch("agentdrive.services.ingest.generate_table_aliases", new_callable=AsyncMock)
@patch("agentdrive.services.ingest.enrich_chunks_with_summaries", new_callable=AsyncMock)
@patch("agentdrive.services.ingest.generate_document_summary", new_callable=AsyncMock)
@patch("agentdrive.services.ingest.embed_file_aliases", new_callable=AsyncMock)
@patch("agentdrive.services.ingest.embed_file_chunks", new_callable=AsyncMock)
async def test_per_batch_enrichment_skips_completed(
    mock_embed_chunks,
    mock_embed_aliases,
    mock_gen_summary,
    mock_enrich,
    mock_aliases,
    test_file,
    db_session,
):
    """With 2 batches, batch1 already enriched, only batch2's chunks get enriched."""
    # Create batch 1 — fully through enrichment
    batch1 = FileBatch(
        file_id=test_file.id,
        batch_index=0,
        chunking_status=BatchStatus.COMPLETED,
        enrichment_status=BatchStatus.COMPLETED,
        embedding_status=BatchStatus.PENDING,
        chunk_count=1,
    )
    db_session.add(batch1)
    await db_session.flush()

    parent1 = ParentChunk(
        file_id=test_file.id,
        batch_id=batch1.id,
        content="Batch1 parent",
        token_count=2,
    )
    db_session.add(parent1)
    await db_session.flush()

    chunk1 = Chunk(
        file_id=test_file.id,
        parent_chunk_id=parent1.id,
        batch_id=batch1.id,
        chunk_index=0,
        content="Batch1 child",
        context_prefix="already-enriched",
        token_count=2,
        content_type="text",
    )
    db_session.add(chunk1)

    # Create batch 2 — chunking done, enrichment pending
    batch2 = FileBatch(
        file_id=test_file.id,
        batch_index=1,
        chunking_status=BatchStatus.COMPLETED,
        enrichment_status=BatchStatus.PENDING,
        embedding_status=BatchStatus.PENDING,
        chunk_count=1,
    )
    db_session.add(batch2)
    await db_session.flush()

    parent2 = ParentChunk(
        file_id=test_file.id,
        batch_id=batch2.id,
        content="Batch2 parent",
        token_count=2,
    )
    db_session.add(parent2)
    await db_session.flush()

    chunk2 = Chunk(
        file_id=test_file.id,
        parent_chunk_id=parent2.id,
        batch_id=batch2.id,
        chunk_index=1,
        content="Batch2 child",
        context_prefix="",
        token_count=2,
        content_type="text",
    )
    db_session.add(chunk2)

    # Create a summary (Phase 2 already done)
    summary = FileSummary(
        file_id=test_file.id,
        document_summary="Test doc summary.",
        section_summaries=[],
    )
    db_session.add(summary)
    await db_session.commit()

    # Setup mocks
    mock_gen_summary.return_value = {"document_summary": "Test doc summary.", "section_summaries": []}

    def _enrich_passthrough(groups, **kwargs):
        """Mark enrichment by setting context_prefix on children."""
        for g in groups:
            for child in g.children:
                child.context_prefix = "enriched-by-phase3"
        return groups

    mock_enrich.side_effect = _enrich_passthrough
    mock_aliases.return_value = []
    mock_embed_chunks.return_value = 0
    mock_embed_aliases.return_value = 0

    await process_file(test_file.id, db_session)

    # Refresh chunks from DB
    await db_session.refresh(chunk1)
    await db_session.refresh(chunk2)

    # Batch1's chunk should NOT have been re-enriched (still has original prefix)
    assert chunk1.context_prefix == "already-enriched"

    # Batch2's chunk SHOULD have been enriched
    assert chunk2.context_prefix == "enriched-by-phase3"

    # enrich_chunks_with_summaries should be called exactly once (for batch2 only)
    assert mock_enrich.call_count == 1


@pytest.mark.asyncio
@patch("agentdrive.services.ingest.generate_table_aliases", new_callable=AsyncMock)
@patch("agentdrive.services.ingest.enrich_chunks_with_summaries", new_callable=AsyncMock)
@patch("agentdrive.services.ingest.generate_document_summary", new_callable=AsyncMock)
@patch("agentdrive.services.ingest.embed_file_aliases", new_callable=AsyncMock)
@patch("agentdrive.services.ingest.embed_file_chunks", new_callable=AsyncMock)
async def test_resume_multi_batch_after_failure(
    mock_embed_chunks,
    mock_embed_aliases,
    mock_gen_summary,
    mock_enrich,
    mock_aliases,
    test_file,
    db_session,
):
    """Resume: batch1 fully done, batch2 pending enrichment. Only batch2 gets enriched+embedded."""
    # Batch 1 — fully completed (chunking, enrichment, embedding)
    batch1 = FileBatch(
        file_id=test_file.id,
        batch_index=0,
        chunking_status=BatchStatus.COMPLETED,
        enrichment_status=BatchStatus.COMPLETED,
        embedding_status=BatchStatus.COMPLETED,
        chunk_count=1,
    )
    db_session.add(batch1)
    await db_session.flush()

    parent1 = ParentChunk(
        file_id=test_file.id,
        batch_id=batch1.id,
        content="Batch1 parent done",
        token_count=3,
    )
    db_session.add(parent1)
    await db_session.flush()

    chunk1 = Chunk(
        file_id=test_file.id,
        parent_chunk_id=parent1.id,
        batch_id=batch1.id,
        chunk_index=0,
        content="Batch1 child done",
        context_prefix="done-context",
        token_count=3,
        content_type="text",
    )
    db_session.add(chunk1)

    # Batch 2 — chunking done, enrichment/embedding pending
    batch2 = FileBatch(
        file_id=test_file.id,
        batch_index=1,
        chunking_status=BatchStatus.COMPLETED,
        enrichment_status=BatchStatus.PENDING,
        embedding_status=BatchStatus.PENDING,
        chunk_count=1,
    )
    db_session.add(batch2)
    await db_session.flush()

    parent2 = ParentChunk(
        file_id=test_file.id,
        batch_id=batch2.id,
        content="Batch2 parent pending",
        token_count=3,
    )
    db_session.add(parent2)
    await db_session.flush()

    chunk2 = Chunk(
        file_id=test_file.id,
        parent_chunk_id=parent2.id,
        batch_id=batch2.id,
        chunk_index=1,
        content="Batch2 child pending",
        context_prefix="",
        token_count=3,
        content_type="text",
    )
    db_session.add(chunk2)

    # Summary already exists
    summary = FileSummary(
        file_id=test_file.id,
        document_summary="Multi-batch resume test.",
        section_summaries=[],
    )
    db_session.add(summary)

    test_file.total_batches = 2
    test_file.completed_batches = 1
    test_file.status = FileStatus.FAILED
    await db_session.commit()

    # Setup mocks
    mock_gen_summary.return_value = {"document_summary": "Multi-batch resume test.", "section_summaries": []}
    mock_enrich.side_effect = lambda groups, **kwargs: groups
    mock_aliases.return_value = []
    mock_embed_chunks.return_value = 0
    mock_embed_aliases.return_value = 0

    await process_file(test_file.id, db_session)

    await db_session.refresh(test_file)
    assert test_file.status == FileStatus.READY

    # Both batches should be fully completed
    await db_session.refresh(batch1)
    await db_session.refresh(batch2)

    assert batch1.enrichment_status == BatchStatus.COMPLETED
    assert batch1.embedding_status == BatchStatus.COMPLETED
    assert batch2.enrichment_status == BatchStatus.COMPLETED
    assert batch2.embedding_status == BatchStatus.COMPLETED

    # Enrichment should only have been called for batch2
    assert mock_enrich.call_count == 1

    # Embedding should only have been called for batch2
    assert mock_embed_chunks.call_count == 1
    assert mock_embed_aliases.call_count == 1

    # completed_batches should reflect both batches done
    assert test_file.completed_batches == 2
