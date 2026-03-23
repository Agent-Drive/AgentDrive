import pytest
import pytest_asyncio
from agentdrive.models.api_key import ApiKey
from agentdrive.models.tenant import Tenant
from agentdrive.services.auth import hash_api_key, parse_key_prefix

TEST_API_KEY = "sk-ad-coltest1keyforunittestingcollections"

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
async def test_create_collection(authed_client):
    client, tenant = authed_client
    response = await client.post("/v1/collections", json={"name": "my-docs", "description": "Test collection"})
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "my-docs"
    assert data["description"] == "Test collection"
    assert "id" in data

@pytest.mark.asyncio
async def test_create_duplicate_collection_fails(authed_client):
    client, tenant = authed_client
    await client.post("/v1/collections", json={"name": "unique-name"})
    response = await client.post("/v1/collections", json={"name": "unique-name"})
    assert response.status_code == 409

@pytest.mark.asyncio
async def test_list_collections(authed_client):
    client, tenant = authed_client
    await client.post("/v1/collections", json={"name": "col-a"})
    await client.post("/v1/collections", json={"name": "col-b"})
    response = await client.get("/v1/collections")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 2

@pytest.mark.asyncio
async def test_delete_collection(authed_client):
    client, tenant = authed_client
    create = await client.post("/v1/collections", json={"name": "to-delete"})
    col_id = create.json()["id"]
    response = await client.delete(f"/v1/collections/{col_id}")
    assert response.status_code == 204
