import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from sqlalchemy import select

from agentdrive.chunking.base import ChunkResult, ParentChildChunks
from agentdrive.models.chunk import Chunk
from agentdrive.models.file import File
from agentdrive.models.file_batch import FileBatch
from agentdrive.models.tenant import Tenant
from agentdrive.models.types import BatchStatus, FileStatus
from agentdrive.services.ingest import process_file


@pytest.mark.asyncio
async def test_small_pdf_unchanged(db_session):
    """Regression test: small PDFs bypass Document AI batching and use direct chunking."""
    tenant = Tenant(name="test")
    db_session.add(tenant)
    await db_session.flush()
    file = File(
        tenant_id=tenant.id,
        filename="small.pdf",
        content_type="pdf",
        gcs_path="tenants/x/files/y/small.pdf",
        file_size=100,
    )
    db_session.add(file)
    await db_session.commit()

    # Mock the chunker to return a single parent-child group
    groups = [
        ParentChildChunks(
            parent=ChunkResult(
                content="Small PDF content",
                context_prefix="",
                token_count=5,
                content_type="text",
            ),
            children=[
                ChunkResult(
                    content="Child content",
                    context_prefix="",
                    token_count=3,
                    content_type="text",
                )
            ],
        )
    ]

    with patch("agentdrive.services.ingest.StorageService") as MockStorage, \
         patch("agentdrive.services.ingest.registry") as mock_registry:
        mock_storage = MagicMock()
        mock_storage.download_to_tempfile.return_value = Path("/tmp/fake.pdf")
        MockStorage.return_value = mock_storage
        mock_registry.chunk_file.return_value = groups

        await process_file(file.id, db_session)

    # Verify file is READY
    await db_session.refresh(file)
    assert file.status == FileStatus.READY

    # Verify chunks exist with batch_id
    chunks = (
        await db_session.execute(select(Chunk).where(Chunk.file_id == file.id))
    ).scalars().all()
    assert len(chunks) == 1
    assert chunks[0].batch_id is not None

    # Verify single batch exists
    batches = (
        await db_session.execute(select(FileBatch).where(FileBatch.file_id == file.id))
    ).scalars().all()
    assert len(batches) == 1
    assert batches[0].embedding_status == BatchStatus.COMPLETED


@pytest.mark.asyncio
async def test_multiple_chunks_single_batch(db_session):
    """Integration test: multiple chunk groups from a PDF are assigned to same batch."""
    tenant = Tenant(name="test")
    db_session.add(tenant)
    await db_session.flush()
    file = File(
        tenant_id=tenant.id,
        filename="multi_chunk.pdf",
        content_type="pdf",
        gcs_path="tenants/x/files/y/multi_chunk.pdf",
        file_size=50000,  # 50KB
    )
    db_session.add(file)
    await db_session.commit()

    # Mock the chunker to return two parent-child groups (from same PDF)
    groups = [
        ParentChildChunks(
            parent=ChunkResult(
                content="Content 1",
                context_prefix="",
                token_count=100,
                content_type="text",
            ),
            children=[
                ChunkResult(
                    content="Child 1",
                    context_prefix="",
                    token_count=50,
                    content_type="text",
                )
            ],
        ),
        ParentChildChunks(
            parent=ChunkResult(
                content="Content 2",
                context_prefix="",
                token_count=100,
                content_type="text",
            ),
            children=[
                ChunkResult(
                    content="Child 2",
                    context_prefix="",
                    token_count=50,
                    content_type="text",
                )
            ],
        ),
    ]

    with patch("agentdrive.services.ingest.StorageService") as MockStorage, \
         patch("agentdrive.services.ingest.registry") as mock_registry:
        mock_storage = MagicMock()
        mock_storage.download_to_tempfile.return_value = Path("/tmp/fake.pdf")
        MockStorage.return_value = mock_storage
        mock_registry.chunk_file.return_value = groups

        await process_file(file.id, db_session)

    # Verify file is READY
    await db_session.refresh(file)
    assert file.status == FileStatus.READY

    # Verify two chunks exist
    chunks = (
        await db_session.execute(select(Chunk).where(Chunk.file_id == file.id))
    ).scalars().all()
    assert len(chunks) == 2

    # Verify both chunks have same batch_id (single batch)
    batch_ids = {chunk.batch_id for chunk in chunks}
    assert len(batch_ids) == 1  # Both chunks in same batch

    # Verify single batch exists
    batches = (
        await db_session.execute(select(FileBatch).where(FileBatch.file_id == file.id))
    ).scalars().all()
    assert len(batches) == 1
    assert batches[0].chunk_count == 2
    assert batches[0].embedding_status == BatchStatus.COMPLETED
