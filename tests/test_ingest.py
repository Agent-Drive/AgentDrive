from unittest.mock import MagicMock, patch
import pytest
import pytest_asyncio
from agentdrive.models.file import File
from agentdrive.models.tenant import Tenant
from agentdrive.models.types import FileStatus
from agentdrive.services.auth import hash_api_key
from agentdrive.services.ingest import process_file


@pytest_asyncio.fixture
async def test_file(db_session):
    tenant = Tenant(name="Test", api_key_hash=hash_api_key("sk-test"))
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
@patch("agentdrive.services.ingest.StorageService")
async def test_process_file_success(mock_storage_cls, test_file, db_session):
    mock_storage = MagicMock()
    mock_storage.download.return_value = b"# Hello\n\n## Section\n\nContent here."
    mock_storage_cls.return_value = mock_storage
    await process_file(test_file.id, db_session)
    await db_session.refresh(test_file)
    assert test_file.status == FileStatus.READY


@pytest.mark.asyncio
@patch("agentdrive.services.ingest.StorageService")
async def test_process_file_creates_chunks(mock_storage_cls, test_file, db_session):
    mock_storage = MagicMock()
    mock_storage.download.return_value = b"# Doc\n\n## Part A\n\nFirst section.\n\n## Part B\n\nSecond section."
    mock_storage_cls.return_value = mock_storage
    await process_file(test_file.id, db_session)
    from sqlalchemy import select
    from agentdrive.models.chunk import Chunk
    result = await db_session.execute(select(Chunk).where(Chunk.file_id == test_file.id))
    chunks = result.scalars().all()
    assert len(chunks) > 0


@pytest.mark.asyncio
@patch("agentdrive.services.ingest.StorageService")
async def test_process_file_failure_sets_status(mock_storage_cls, test_file, db_session):
    mock_storage = MagicMock()
    mock_storage.download.side_effect = Exception("GCS error")
    mock_storage_cls.return_value = mock_storage
    await process_file(test_file.id, db_session)
    await db_session.refresh(test_file)
    assert test_file.status == FileStatus.FAILED
