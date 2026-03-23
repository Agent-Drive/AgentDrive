from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import pytest_asyncio
from agentdrive.models.api_key import ApiKey
from agentdrive.models.tenant import Tenant
from agentdrive.services.auth import hash_api_key, parse_key_prefix

TEST_API_KEY = "sk-ad-filetest1keyforunittestingfiles"


@pytest.fixture(autouse=True)
def mock_ingest(monkeypatch):
    """Prevent the background ingest task from connecting to the production DB during tests."""
    monkeypatch.setattr("agentdrive.routers.files.process_file", AsyncMock())


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
