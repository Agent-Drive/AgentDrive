import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from agentdrive.models.api_key import ApiKey
from agentdrive.models.tenant import Tenant
from agentdrive.services.auth import hash_api_key, parse_key_prefix

TEST_API_KEY = "sk-ad-testkey1234567890abcdefghijkl"


@pytest.fixture(autouse=True)
def mock_ingest(monkeypatch):
    """Prevent enqueue from starting real ingestion during tests."""
    monkeypatch.setattr("agentdrive.routers.files.enqueue", lambda file_id: None)


@pytest_asyncio.fixture
async def authed_client(client, db_session):
    tenant = Tenant(name="Test")
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
    client.headers["Authorization"] = f"Bearer {TEST_API_KEY}"
    return client, tenant


@pytest.mark.asyncio
@patch("agentdrive.routers.knowledge_bases._get_engine")
async def test_kb_search_endpoint(mock_get_engine, authed_client, db_session):
    client, tenant = authed_client
    from agentdrive.knowledge.models import KnowledgeBase
    from agentdrive.models.types import KBStatus

    kb = KnowledgeBase(tenant_id=tenant.id, name="Test KB", status=KBStatus.ACTIVE)
    db_session.add(kb)
    await db_session.commit()
    await db_session.refresh(kb)

    mock_engine = MagicMock()
    mock_engine.search_kb = AsyncMock(return_value={
        "results": [],
        "query_tokens": 5,
        "search_time_ms": 42,
    })
    mock_get_engine.return_value = mock_engine

    resp = await client.post(
        f"/v1/knowledge-bases/{kb.id}/search",
        json={"query": "alignment", "top_k": 5},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["search_time_ms"] == 42
    assert data["results"] == []


@pytest.mark.asyncio
async def test_kb_search_not_found(authed_client):
    client, tenant = authed_client
    resp = await client.post(
        f"/v1/knowledge-bases/{uuid.uuid4()}/search",
        json={"query": "test"},
    )
    assert resp.status_code == 404
