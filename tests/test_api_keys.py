import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from agentdrive.models.api_key import ApiKey
from agentdrive.models.tenant import Tenant
from agentdrive.services.auth import hash_api_key, parse_key_prefix

TEST_API_KEY = "sk-ad-testpre1restofthekeythatislongenough"


@pytest_asyncio.fixture
async def authed_client(client, db_session: AsyncSession):
    tenant = Tenant(name="Test Tenant", api_key_hash="unused")
    db_session.add(tenant)
    await db_session.flush()
    prefix = parse_key_prefix(TEST_API_KEY)
    api_key = ApiKey(tenant_id=tenant.id, key_prefix=prefix, key_hash=hash_api_key(TEST_API_KEY), name="test")
    db_session.add(api_key)
    await db_session.commit()
    client.headers["Authorization"] = f"Bearer {TEST_API_KEY}"
    return client


@pytest.mark.asyncio
async def test_create_api_key(authed_client):
    response = await authed_client.post("/v1/api-keys", json={"name": "ci-key"})
    assert response.status_code == 201
    data = response.json()
    assert data["key"].startswith("sk-ad-")
    assert data["name"] == "ci-key"
    assert data["key_prefix"] == data["key"][len("sk-ad-"):len("sk-ad-") + 8]
    assert "id" in data


@pytest.mark.asyncio
async def test_list_api_keys(authed_client):
    await authed_client.post("/v1/api-keys", json={"name": "key-1"})
    await authed_client.post("/v1/api-keys", json={"name": "key-2"})
    response = await authed_client.get("/v1/api-keys")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 2
    for key in data["api_keys"]:
        assert "key" not in key  # never expose full key in list
        assert "key_prefix" in key


@pytest.mark.asyncio
async def test_revoke_api_key(authed_client):
    create_resp = await authed_client.post("/v1/api-keys", json={"name": "to-revoke"})
    key_id = create_resp.json()["id"]
    delete_resp = await authed_client.delete(f"/v1/api-keys/{key_id}")
    assert delete_resp.status_code == 204

    # verify key shows as revoked in list
    list_resp = await authed_client.get("/v1/api-keys")
    revoked = [k for k in list_resp.json()["api_keys"] if k["id"] == key_id]
    assert len(revoked) == 1
    assert revoked[0]["revoked_at"] is not None


@pytest.mark.asyncio
async def test_revoke_nonexistent_key(authed_client):
    response = await authed_client.delete("/v1/api-keys/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_key_requires_auth(client):
    response = await client.post("/v1/api-keys", json={"name": "nope"})
    assert response.status_code in (401, 403)
