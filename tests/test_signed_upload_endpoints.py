import uuid
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select

from agentdrive.models.api_key import ApiKey
from agentdrive.models.file import File as FileModel
from agentdrive.models.tenant import Tenant
from agentdrive.models.types import FileStatus
from agentdrive.services.auth import hash_api_key, parse_key_prefix

TEST_API_KEY = "sk-ad-signeduploadtestkey1234567890ab"


@pytest.fixture(autouse=True)
def mock_ingest(monkeypatch):
    """Prevent enqueue from starting real ingestion during tests."""
    monkeypatch.setattr("agentdrive.routers.files.enqueue", lambda file_id: None)


@pytest_asyncio.fixture
async def authed_client(client, db_session):
    tenant = Tenant(name="Signed Upload Tenant")
    db_session.add(tenant)
    await db_session.flush()
    prefix = parse_key_prefix(TEST_API_KEY)
    api_key = ApiKey(
        tenant_id=tenant.id,
        key_prefix=prefix,
        key_hash=hash_api_key(TEST_API_KEY),
        name="test",
    )
    db_session.add(api_key)
    await db_session.commit()
    await db_session.refresh(tenant)
    client.headers["Authorization"] = f"Bearer {TEST_API_KEY}"
    return client, tenant


@pytest.mark.asyncio
@patch("agentdrive.routers.files.StorageService")
async def test_upload_url_creates_uploading_file(mock_storage_cls, authed_client, db_session):
    client, tenant = authed_client
    mock_storage = MagicMock()
    mock_storage.generate_path.return_value = "tenants/abc/files/def/big.pdf"
    mock_storage.generate_signed_upload_url.return_value = "https://storage.googleapis.com/signed-url"
    mock_storage_cls.return_value = mock_storage

    response = await client.post(
        "/v1/files/upload-url",
        json={
            "filename": "big.pdf",
            "content_type": "application/pdf",
            "file_size": 100_000_000,
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert "file_id" in data
    assert data["upload_url"] == "https://storage.googleapis.com/signed-url"
    assert "expires_at" in data

    # Verify DB record has UPLOADING status
    result = await db_session.execute(
        select(FileModel).where(FileModel.id == uuid.UUID(data["file_id"]))
    )
    file_record = result.scalar_one_or_none()
    assert file_record is not None
    assert file_record.status == FileStatus.UPLOADING


@pytest.mark.asyncio
@patch("agentdrive.routers.files.StorageService")
async def test_upload_url_rejects_oversized(mock_storage_cls, authed_client):
    client, tenant = authed_client
    mock_storage_cls.return_value = MagicMock()

    response = await client.post(
        "/v1/files/upload-url",
        json={
            "filename": "huge.bin",
            "content_type": "application/octet-stream",
            "file_size": 6 * 1024 * 1024 * 1024,  # 6GB > 5GB limit
        },
    )
    assert response.status_code == 413


@pytest.mark.asyncio
@patch("agentdrive.routers.files.enqueue")
@patch("agentdrive.routers.files.StorageService")
async def test_complete_upload_enqueues(mock_storage_cls, mock_enqueue, authed_client, db_session):
    client, tenant = authed_client

    # Pre-create an UPLOADING file in the DB
    file_id = uuid.uuid4()
    file_record = FileModel(
        id=file_id,
        tenant_id=tenant.id,
        filename="upload.pdf",
        content_type="application/pdf",
        gcs_path=f"tenants/{tenant.id}/files/{file_id}/upload.pdf",
        file_size=0,
        status=FileStatus.UPLOADING,
    )
    db_session.add(file_record)
    await db_session.commit()

    mock_storage = MagicMock()
    mock_storage.blob_exists.return_value = True
    mock_storage.get_blob_size.return_value = 50_000_000
    mock_storage_cls.return_value = mock_storage

    response = await client.post(f"/v1/files/{file_id}/complete")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "pending"
    assert data["file_size"] == 50_000_000

    mock_enqueue.assert_called_once_with(file_id)


@pytest.mark.asyncio
@patch("agentdrive.routers.files.StorageService")
async def test_complete_404_for_non_uploading(mock_storage_cls, authed_client):
    client, tenant = authed_client
    mock_storage_cls.return_value = MagicMock()

    random_id = uuid.uuid4()
    response = await client.post(f"/v1/files/{random_id}/complete")
    assert response.status_code == 404
