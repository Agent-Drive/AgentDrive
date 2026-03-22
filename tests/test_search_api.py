from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import pytest_asyncio
from agentdrive.models.tenant import Tenant
from agentdrive.services.auth import hash_api_key

TEST_API_KEY = "sk-test-key-search"


@pytest_asyncio.fixture
async def authed_client(client, db_session):
    tenant = Tenant(name="Test", api_key_hash=hash_api_key(TEST_API_KEY))
    db_session.add(tenant)
    await db_session.commit()
    client.headers["Authorization"] = f"Bearer {TEST_API_KEY}"
    return client


@pytest.mark.asyncio
@patch("agentdrive.routers.search._get_engine")
async def test_search_endpoint(mock_get_engine, authed_client):
    mock_engine = MagicMock()
    mock_engine.search = AsyncMock(return_value=[
        {"chunk_id": "abc", "content": "test content", "token_count": 10,
         "score": 0.9, "content_type": "text", "provenance": {"file_id": "def"}}
    ])
    mock_get_engine.return_value = mock_engine
    response = await authed_client.post("/v1/search", json={"query": "test query"})
    assert response.status_code == 200
    data = response.json()
    assert len(data["results"]) == 1
    assert "search_time_ms" in data
    assert "query_tokens" in data


@pytest.mark.asyncio
async def test_search_requires_auth(client):
    response = await client.post("/v1/search", json={"query": "test"})
    assert response.status_code in (401, 403)
