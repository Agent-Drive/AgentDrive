import uuid
from unittest.mock import MagicMock, patch
import pytest
import pytest_asyncio
from agentdrive.models.api_key import ApiKey
from agentdrive.models.tenant import Tenant
from agentdrive.services.auth import hash_api_key, parse_key_prefix

TEST_API_KEY = "sk-ad-filetest1keyforunittestingfiles"


@pytest.fixture(autouse=True)
def mock_ingest(monkeypatch):
    """Prevent enqueue from starting real ingestion during tests."""
    monkeypatch.setattr("agentdrive.routers.files.enqueue", lambda file_id: None)


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


@pytest.mark.asyncio
@patch("agentdrive.routers.files.StorageService")
async def test_upload_file(mock_storage_cls, authed_client):
    client, tenant = authed_client
    mock_storage = MagicMock()
    mock_storage.upload.return_value = "tenants/abc/files/def/test.pdf"
    mock_storage_cls.return_value = mock_storage
    response = await client.post(
        "/v1/files",
        files={"file": ("test.pdf", b"fake pdf content", "application/pdf")},
    )
    assert response.status_code == 202
    data = response.json()
    assert data["filename"] == "test.pdf"
    assert data["content_type"] == "pdf"
    assert data["status"] == "pending"
    assert "id" in data


@pytest.mark.asyncio
@patch("agentdrive.routers.files.StorageService")
async def test_get_file_status(mock_storage_cls, authed_client):
    client, tenant = authed_client
    mock_storage = MagicMock()
    mock_storage.upload.return_value = "path"
    mock_storage_cls.return_value = mock_storage
    upload = await client.post(
        "/v1/files",
        files={"file": ("test.txt", b"hello", "text/plain")},
    )
    file_id = upload.json()["id"]
    response = await client.get(f"/v1/files/{file_id}")
    assert response.status_code == 200
    assert response.json()["status"] == "pending"


@pytest.mark.asyncio
@patch("agentdrive.routers.files.StorageService")
async def test_list_files(mock_storage_cls, authed_client):
    client, tenant = authed_client
    mock_storage = MagicMock()
    mock_storage.upload.return_value = "path"
    mock_storage_cls.return_value = mock_storage
    await client.post("/v1/files", files={"file": ("a.txt", b"a", "text/plain")})
    await client.post("/v1/files", files={"file": ("b.txt", b"b", "text/plain")})
    response = await client.get("/v1/files")
    assert response.status_code == 200
    assert response.json()["total"] >= 2


@pytest.mark.asyncio
@patch("agentdrive.routers.files.StorageService")
async def test_delete_file(mock_storage_cls, authed_client):
    client, tenant = authed_client
    mock_storage = MagicMock()
    mock_storage.upload.return_value = "path"
    mock_storage_cls.return_value = mock_storage
    upload = await client.post("/v1/files", files={"file": ("del.txt", b"x", "text/plain")})
    file_id = upload.json()["id"]
    response = await client.delete(f"/v1/files/{file_id}")
    assert response.status_code == 204
    mock_storage.delete.assert_called_once()


@pytest.mark.asyncio
@patch("agentdrive.routers.files.StorageService")
async def test_get_file_includes_updated_at(mock_storage_cls, authed_client):
    client, tenant = authed_client
    mock_storage = MagicMock()
    mock_storage.upload.return_value = "path"
    mock_storage_cls.return_value = mock_storage
    upload = await client.post(
        "/v1/files",
        files={"file": ("test.txt", b"hello", "text/plain")},
    )
    file_id = upload.json()["id"]
    response = await client.get(f"/v1/files/{file_id}")
    assert response.status_code == 200
    data = response.json()
    assert "updated_at" in data
    assert data["updated_at"] is not None



@pytest.mark.asyncio
@patch("agentdrive.routers.files.StorageService")
async def test_download_file(mock_storage_cls, authed_client):
    client, tenant = authed_client
    file_content = b"hello world file content"
    mock_storage = MagicMock()
    mock_storage.upload.return_value = "fake/path"
    mock_storage.download_stream.return_value = iter([file_content])
    mock_storage_cls.return_value = mock_storage

    resp = await client.post(
        "/v1/files",
        files={"file": ("test.txt", file_content, "text/plain")},
    )
    file_id = resp.json()["id"]

    dl_resp = await client.get(f"/v1/files/{file_id}/download")
    assert dl_resp.status_code == 200
    assert dl_resp.content == file_content
    assert "attachment" in dl_resp.headers.get("content-disposition", "")
    assert "test.txt" in dl_resp.headers.get("content-disposition", "")


@pytest.mark.asyncio
@patch("agentdrive.routers.files.StorageService")
async def test_download_file_blob_missing(mock_storage_cls, authed_client):
    client, tenant = authed_client
    mock_storage = MagicMock()
    mock_storage.upload.return_value = "fake/path"
    mock_storage.download_stream.side_effect = FileNotFoundError("gone")
    mock_storage_cls.return_value = mock_storage

    resp = await client.post(
        "/v1/files",
        files={"file": ("test.txt", b"content", "text/plain")},
    )
    file_id = resp.json()["id"]

    dl_resp = await client.get(f"/v1/files/{file_id}/download")
    assert dl_resp.status_code == 502


@pytest.mark.asyncio
async def test_download_file_not_found(authed_client):
    client, tenant = authed_client
    resp = await client.get(f"/v1/files/{uuid.uuid4()}/download")
    assert resp.status_code == 404
