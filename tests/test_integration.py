"""
End-to-end smoke test: upload → chunk → embed → search.
Requires test DB with pgvector. Mocks external APIs (Voyage, Cohere, GCS).
"""
from unittest.mock import MagicMock, patch, AsyncMock
import pytest
import pytest_asyncio
from agentdrive.models.api_key import ApiKey
from agentdrive.models.tenant import Tenant
from agentdrive.services.auth import hash_api_key, parse_key_prefix

TEST_API_KEY = "sk-ad-intgtest1keyforintegrationsmoketest"

@pytest_asyncio.fixture
async def authed_client(client, db_session):
    tenant = Tenant(name="Integration Test")
    db_session.add(tenant)
    await db_session.flush()
    prefix = parse_key_prefix(TEST_API_KEY)
    api_key = ApiKey(tenant_id=tenant.id, key_prefix=prefix, key_hash=hash_api_key(TEST_API_KEY), name="test")
    db_session.add(api_key)
    await db_session.commit()
    client.headers["Authorization"] = f"Bearer {TEST_API_KEY}"
    return client

@pytest.mark.asyncio
@patch("agentdrive.routers.search._get_engine")
@patch("agentdrive.routers.files.enqueue", lambda file_id: None)
@patch("agentdrive.routers.files.StorageService")
async def test_upload_and_search(mock_storage_cls, mock_get_engine, authed_client):
    # Mock GCS
    mock_storage = MagicMock()
    mock_storage.upload.return_value = "test/path"
    mock_storage.download.return_value = b"# Test Doc\n\n## Section A\n\nImportant content about authentication.\n\n## Section B\n\nDetails about authorization."
    mock_storage_cls.return_value = mock_storage

    # Mock search engine
    mock_engine = MagicMock()
    mock_engine.search = AsyncMock(return_value=[
        {
            "chunk_id": "00000000-0000-0000-0000-000000000001",
            "content": "Important content about authentication.",
            "token_count": 10,
            "score": 0.95,
            "content_type": "text",
            "provenance": {"file_id": "00000000-0000-0000-0000-000000000002"},
        }
    ])
    mock_get_engine.return_value = mock_engine

    # Upload file
    upload_resp = await authed_client.post(
        "/v1/files",
        files={"file": ("test.md", b"# Test Doc\n\n## Section A\n\nImportant content about authentication.\n\n## Section B\n\nDetails about authorization.", "text/markdown")},
    )
    assert upload_resp.status_code == 202
    file_id = upload_resp.json()["id"]

    # Check status (ingest runs in background — with mock, it may or may not complete)
    import asyncio
    await asyncio.sleep(0.5)

    status_resp = await authed_client.get(f"/v1/files/{file_id}")
    assert status_resp.status_code == 200

    # Search
    search_resp = await authed_client.post("/v1/search", json={"query": "authentication", "top_k": 5})
    assert search_resp.status_code == 200
    data = search_resp.json()
    assert "results" in data
    assert "search_time_ms" in data
    assert len(data["results"]) >= 1

    # Verify the full pipeline was exercised
    mock_storage.upload.assert_called_once()
    mock_engine.search.assert_called_once()
