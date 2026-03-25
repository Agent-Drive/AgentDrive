"""Tests for the ingest pipeline (updated for four-phase architecture)."""
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select

from agentdrive.chunking.base import ChunkResult, ParentChildChunks
from agentdrive.models.chunk import Chunk
from agentdrive.models.file import File
from agentdrive.models.tenant import Tenant
from agentdrive.models.types import FileStatus
from agentdrive.services.ingest import process_file


def _make_groups(content: str = "# Hello\n\n## Section\n\nContent here.") -> list[ParentChildChunks]:
    return [
        ParentChildChunks(
            parent=ChunkResult(content=content, context_prefix="", token_count=10, content_type="text"),
            children=[
                ChunkResult(content="Content here.", context_prefix="Section", token_count=3, content_type="text"),
            ],
        )
    ]


@pytest_asyncio.fixture
async def test_file(db_session):
    tenant = Tenant(name="Test")
    db_session.add(tenant)
    await db_session.commit()
    await db_session.refresh(tenant)
    file = File(
        tenant_id=tenant.id, filename="test.md", content_type="markdown",
        gcs_path="tenants/abc/files/def/test.md", file_size=100, status=FileStatus.PENDING,
    )
    db_session.add(file)
    await db_session.commit()
    await db_session.refresh(file)
    return file


@pytest.mark.asyncio
@patch("agentdrive.services.ingest.generate_table_aliases", new_callable=AsyncMock)
@patch("agentdrive.services.ingest.enrich_chunks_with_summaries", new_callable=AsyncMock)
@patch("agentdrive.services.ingest.generate_document_summary", new_callable=AsyncMock)
@patch("agentdrive.services.ingest.embed_file_aliases", new_callable=AsyncMock)
@patch("agentdrive.services.ingest.embed_file_chunks", new_callable=AsyncMock)
@patch("agentdrive.services.ingest.StorageService")
@patch("agentdrive.services.ingest.registry")
async def test_process_file_success(
    mock_registry, mock_storage_cls, mock_embed_chunks, mock_embed_aliases,
    mock_gen_summary, mock_enrich, mock_aliases, test_file, db_session,
):
    mock_storage = MagicMock()
    mock_storage.download_to_tempfile.return_value = Path("/tmp/fake.md")
    mock_storage_cls.return_value = mock_storage
    mock_registry.chunk_file.return_value = _make_groups()
    mock_gen_summary.return_value = {"document_summary": "", "section_summaries": []}
    mock_enrich.side_effect = lambda groups, **kwargs: groups
    mock_aliases.return_value = []
    mock_embed_chunks.return_value = 0
    mock_embed_aliases.return_value = 0

    await process_file(test_file.id, db_session)
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
async def test_process_file_creates_chunks(
    mock_registry, mock_storage_cls, mock_embed_chunks, mock_embed_aliases,
    mock_gen_summary, mock_enrich, mock_aliases, test_file, db_session,
):
    mock_storage = MagicMock()
    mock_storage.download_to_tempfile.return_value = Path("/tmp/fake.md")
    mock_storage_cls.return_value = mock_storage
    mock_registry.chunk_file.return_value = _make_groups("# Doc\n\n## Part A\n\nFirst.\n\n## Part B\n\nSecond.")
    mock_gen_summary.return_value = {"document_summary": "", "section_summaries": []}
    mock_enrich.side_effect = lambda groups, **kwargs: groups
    mock_aliases.return_value = []
    mock_embed_chunks.return_value = 0
    mock_embed_aliases.return_value = 0

    await process_file(test_file.id, db_session)
    result = await db_session.execute(select(Chunk).where(Chunk.file_id == test_file.id))
    chunks = result.scalars().all()
    assert len(chunks) > 0


@pytest.mark.asyncio
@patch("agentdrive.services.ingest.StorageService")
@patch("agentdrive.services.ingest.registry")
async def test_process_file_failure_sets_status(mock_registry, mock_storage_cls, test_file, db_session):
    mock_storage = MagicMock()
    mock_storage.download_to_tempfile.side_effect = Exception("GCS error")
    mock_storage_cls.return_value = mock_storage

    await process_file(test_file.id, db_session)
    await db_session.refresh(test_file)
    assert test_file.status == FileStatus.FAILED


@pytest.mark.asyncio
@patch("agentdrive.services.ingest.generate_table_aliases", new_callable=AsyncMock)
@patch("agentdrive.services.ingest.enrich_chunks_with_summaries", new_callable=AsyncMock)
@patch("agentdrive.services.ingest.generate_document_summary", new_callable=AsyncMock)
@patch("agentdrive.services.ingest.embed_file_chunks", new_callable=AsyncMock)
@patch("agentdrive.services.ingest.embed_file_aliases", new_callable=AsyncMock)
@patch("agentdrive.services.ingest.StorageService")
@patch("agentdrive.services.ingest.registry")
async def test_process_file_calls_enrichment(
    mock_registry, mock_storage_cls, mock_embed_aliases, mock_embed_chunks,
    mock_gen_summary, mock_enrich, mock_aliases, test_file, db_session,
):
    mock_storage = MagicMock()
    mock_storage.download_to_tempfile.return_value = Path("/tmp/fake.md")
    mock_storage_cls.return_value = mock_storage
    mock_registry.chunk_file.return_value = _make_groups()
    mock_gen_summary.return_value = {"document_summary": "Summary.", "section_summaries": []}
    mock_enrich.side_effect = lambda groups, **kwargs: groups
    mock_aliases.return_value = []
    mock_embed_chunks.return_value = 0
    mock_embed_aliases.return_value = 0

    await process_file(test_file.id, db_session)

    mock_gen_summary.assert_called_once()
    mock_enrich.assert_called_once()
    mock_aliases.assert_called_once()
