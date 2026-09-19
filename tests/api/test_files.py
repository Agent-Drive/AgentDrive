import uuid
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio

from agentdrive.api.auth.service import hash_api_key, parse_key_prefix
from agentdrive.engine.data.models.api_key import ApiKey
from agentdrive.engine.data.models.file import File as FileModel
from agentdrive.engine.data.models.tenant import Tenant

TEST_API_KEY = "sk-ad-filetest1keyforunittestingfiles"


@pytest.fixture(autouse=True)
def mock_ingest(monkeypatch):
    """Prevent enqueue from starting real ingestion during tests."""
    monkeypatch.setattr("agentdrive.api.files.service.enqueue", lambda file_id: None)


@pytest_asyncio.fixture
async def authed_client(client, db_session):
    tenant = Tenant(name="Test Tenant")
    db_session.add(tenant)
    await db_session.flush()
    prefix = parse_key_prefix(TEST_API_KEY)
    api_key = ApiKey(tenant_id=tenant.id, key_prefix=prefix, key_hash=hash_api_key(TEST_API_KEY), name="test")
    db_session.add(api_key)
    await db_session.commit()
    await db_session.refresh(tenant)
    client.headers["Authorization"] = f"Bearer {TEST_API_KEY}"
    return client, tenant


async def _seed_file(db_session, tenant, filename="test.txt", content_type="text", file_size=5):
    record = FileModel(
        tenant_id=tenant.id,
        filename=filename,
        content_type=content_type,
        gcs_path=f"tenants/{tenant.id}/files/{uuid.uuid4()}/{filename}",
        file_size=file_size,
        status="pending",
    )
    db_session.add(record)
    await db_session.commit()
    await db_session.refresh(record)
    return record


@pytest.mark.asyncio
async def test_multipart_upload_rejected(authed_client):
    client, _tenant = authed_client
    response = await client.post(
        "/v1/files",
        files={"file": ("test.pdf", b"fake pdf content", "application/pdf")},
    )
    assert response.status_code == 405


@pytest.mark.asyncio
async def test_get_file_status(authed_client, db_session):
    client, tenant = authed_client
    record = await _seed_file(db_session, tenant)
    response = await client.get(f"/v1/files/{record.id}")
    assert response.status_code == 200
    assert response.json()["status"] == "pending"


@pytest.mark.asyncio
async def test_list_files(authed_client, db_session):
    client, tenant = authed_client
    await _seed_file(db_session, tenant, filename="a.txt")
    await _seed_file(db_session, tenant, filename="b.txt")
    response = await client.get("/v1/files")
    assert response.status_code == 200
    assert response.json()["total"] >= 2


@pytest.mark.asyncio
@patch("agentdrive.api.files.service.StorageService")
async def test_delete_file(mock_storage_cls, authed_client, db_session):
    client, tenant = authed_client
    mock_storage = MagicMock()
    mock_storage_cls.return_value = mock_storage
    record = await _seed_file(db_session, tenant, filename="del.txt")
    response = await client.delete(f"/v1/files/{record.id}")
    assert response.status_code == 204
    mock_storage.delete.assert_called_once()


@pytest.mark.asyncio
async def test_get_file_includes_updated_at(authed_client, db_session):
    client, tenant = authed_client
    record = await _seed_file(db_session, tenant)
    response = await client.get(f"/v1/files/{record.id}")
    assert response.status_code == 200
    data = response.json()
    assert "updated_at" in data
    assert data["updated_at"] is not None


@pytest.mark.asyncio
@patch("agentdrive.api.files.service.StorageService")
async def test_download_file(mock_storage_cls, authed_client, db_session):
    client, tenant = authed_client
    file_content = b"hello world file content"
    mock_storage = MagicMock()
    mock_storage.download_stream.return_value = iter([file_content])
    mock_storage_cls.return_value = mock_storage

    record = await _seed_file(
        db_session, tenant, filename="test.txt", file_size=len(file_content)
    )

    dl_resp = await client.get(f"/v1/files/{record.id}/download")
    assert dl_resp.status_code == 200
    assert dl_resp.content == file_content
    assert "attachment" in dl_resp.headers.get("content-disposition", "")
    assert "test.txt" in dl_resp.headers.get("content-disposition", "")


@pytest.mark.asyncio
@patch("agentdrive.api.files.service.StorageService")
async def test_download_file_blob_missing(mock_storage_cls, authed_client, db_session):
    client, tenant = authed_client
    mock_storage = MagicMock()
    mock_storage.download_stream.side_effect = FileNotFoundError("gone")
    mock_storage_cls.return_value = mock_storage

    record = await _seed_file(db_session, tenant)

    dl_resp = await client.get(f"/v1/files/{record.id}/download")
    assert dl_resp.status_code == 502


@pytest.mark.asyncio
async def test_download_file_not_found(authed_client):
    client, _tenant = authed_client
    resp = await client.get(f"/v1/files/{uuid.uuid4()}/download")
    assert resp.status_code == 404
