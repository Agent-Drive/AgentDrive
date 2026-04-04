import uuid

import pytest
import pytest_asyncio

from agentdrive.models.api_key import ApiKey
from agentdrive.models.file import File as FileModel
from agentdrive.models.tenant import Tenant
from agentdrive.services.auth import hash_api_key, parse_key_prefix

TEST_API_KEY = "sk-ad-testkey1234567890abcdefghijkl"


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
async def test_create_kb(authed_client):
    client, tenant = authed_client
    response = await client.post(
        "/v1/knowledge-bases",
        json={"name": "My KB", "description": "A test knowledge base"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "My KB"
    assert data["description"] == "A test knowledge base"
    assert data["status"] == "active"
    assert data["file_count"] == 0
    assert data["article_count"] == 0
    assert "id" in data
    assert "created_at" in data
    assert "updated_at" in data


@pytest.mark.asyncio
async def test_create_duplicate_kb(authed_client):
    client, tenant = authed_client
    await client.post(
        "/v1/knowledge-bases",
        json={"name": "Dupe KB"},
    )
    response = await client.post(
        "/v1/knowledge-bases",
        json={"name": "Dupe KB"},
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_list_kbs(authed_client):
    client, tenant = authed_client
    await client.post("/v1/knowledge-bases", json={"name": "KB One"})
    await client.post("/v1/knowledge-bases", json={"name": "KB Two"})
    response = await client.get("/v1/knowledge-bases")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert len(data["knowledge_bases"]) == 2


@pytest.mark.asyncio
async def test_get_kb(authed_client):
    client, tenant = authed_client
    create_resp = await client.post(
        "/v1/knowledge-bases",
        json={"name": "Get Me"},
    )
    kb_id = create_resp.json()["id"]
    response = await client.get(f"/v1/knowledge-bases/{kb_id}")
    assert response.status_code == 200
    assert response.json()["name"] == "Get Me"


@pytest.mark.asyncio
async def test_get_kb_not_found(authed_client):
    client, tenant = authed_client
    response = await client.get(f"/v1/knowledge-bases/{uuid.uuid4()}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_kb(authed_client):
    client, tenant = authed_client
    create_resp = await client.post(
        "/v1/knowledge-bases",
        json={"name": "Delete Me"},
    )
    kb_id = create_resp.json()["id"]
    response = await client.delete(f"/v1/knowledge-bases/{kb_id}")
    assert response.status_code == 204
    # Confirm it's gone
    get_resp = await client.get(f"/v1/knowledge-bases/{kb_id}")
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_add_files_to_kb(authed_client, db_session):
    client, tenant = authed_client
    # Create a file record directly in DB
    file_record = FileModel(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        filename="test.pdf",
        content_type="pdf",
        gcs_path="fake/path",
        file_size=1024,
        status="ready",
    )
    db_session.add(file_record)
    await db_session.commit()

    # Create KB
    create_resp = await client.post(
        "/v1/knowledge-bases",
        json={"name": "Files KB"},
    )
    kb_id = create_resp.json()["id"]

    # Add file to KB
    response = await client.post(
        f"/v1/knowledge-bases/{kb_id}/files",
        json={"file_ids": [str(file_record.id)]},
    )
    assert response.status_code == 200
    assert response.json()["added"] == 1


@pytest.mark.asyncio
async def test_list_articles_empty(authed_client):
    client, tenant = authed_client
    create_resp = await client.post(
        "/v1/knowledge-bases",
        json={"name": "Empty Articles KB"},
    )
    kb_id = create_resp.json()["id"]
    response = await client.get(f"/v1/knowledge-bases/{kb_id}/articles")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["articles"] == []
