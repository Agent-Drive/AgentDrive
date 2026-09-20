"""Hosted MCP HTTP + OAuth tests.

Manual smoke (Claude Code or Cursor):
1. uv run uvicorn agentdrive.api.app:app --port 8080
2. Add MCP URL http://localhost:8080/mcp
3. Complete WorkOS login once
4. start_upload a small file, PUT to the signed URL, complete_upload
5. Confirm pending → processing.
"""

import base64
import hashlib
import json
import secrets
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import parse_qs, urlparse

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from agentdrive.api.auth.service import hash_api_key, parse_key_prefix
from agentdrive.core.data.models.api_key import ApiKey
from agentdrive.core.data.models.file import File as FileModel
from agentdrive.core.data.models.tenant import Tenant
from agentdrive.core.data.models.types import FileStatus

TEST_API_KEY = "sk-ad-hostedmcptestkey1234567890abcd"
REDIRECT_URI = "http://127.0.0.1:3456/callback"


def _pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    return verifier, challenge


class _FakeUser:
    id = "user_hosted_mcp"
    email = "mcp@example.com"
    first_name = "Mcp"
    last_name = "User"


class _FakeAuth:
    user = _FakeUser()


@pytest.fixture(autouse=True)
def mock_ingest(monkeypatch):
    monkeypatch.setattr("agentdrive.core.files.enqueue", lambda file_id: None)


@pytest_asyncio.fixture
async def mcp_client(db_session_factory):
    from agentdrive.api.app import create_app
    from agentdrive.api.mcp.deps import set_session_factory
    from agentdrive.core.data.session import get_session

    app = create_app()

    async def override_session():
        async with db_session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    set_session_factory(db_session_factory)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c, app
    set_session_factory(None)


@pytest_asyncio.fixture
async def seeded_tenant(db_session):
    tenant = Tenant(name="Hosted MCP Tenant")
    db_session.add(tenant)
    await db_session.flush()
    prefix = parse_key_prefix(TEST_API_KEY)
    db_session.add(
        ApiKey(
            tenant_id=tenant.id,
            key_prefix=prefix,
            key_hash=hash_api_key(TEST_API_KEY),
            name="test",
        )
    )
    await db_session.commit()
    await db_session.refresh(tenant)
    return tenant


async def _register_client(client: AsyncClient) -> str:
    response = await client.post(
        "/register",
        json={
            "client_name": "test-client",
            "redirect_uris": [REDIRECT_URI],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["client_id"]


async def _oauth_login(client: AsyncClient, mock_workos) -> str:
    mock_workos.user_management.get_authorization_url.side_effect = (
        lambda *, redirect_uri, state=None, provider=None, **kwargs: (
            f"https://workos.test/authorize?state={state}&redirect_uri={redirect_uri}"
        )
    )
    mock_workos.user_management.authenticate_with_code.return_value = _FakeAuth()

    client_id = await _register_client(client)
    verifier, challenge = _pkce()
    authorize = await client.get(
        "/authorize",
        params={
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": REDIRECT_URI,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": "client-state",
        },
        follow_redirects=False,
    )
    assert authorize.status_code == 302
    workos_url = urlparse(authorize.headers["location"])
    login_id = parse_qs(workos_url.query)["state"][0]

    callback = await client.get(
        "/mcp/oauth/callback",
        params={"code": "workos-code", "state": login_id},
        follow_redirects=False,
    )
    assert callback.status_code == 302
    callback_qs = parse_qs(urlparse(callback.headers["location"]).query)
    assert callback_qs["state"] == ["client-state"]
    auth_code = callback_qs["code"][0]

    token = await client.post(
        "/token",
        data={
            "grant_type": "authorization_code",
            "code": auth_code,
            "redirect_uri": REDIRECT_URI,
            "client_id": client_id,
            "code_verifier": verifier,
        },
    )
    assert token.status_code == 200, token.text
    payload = token.json()
    assert payload["access_token"].startswith("sk-ad-")
    return payload["access_token"]


@pytest.mark.asyncio
async def test_oauth_metadata(client):
    response = await client.get("/.well-known/oauth-authorization-server")
    assert response.status_code == 200
    data = response.json()
    assert data["authorization_endpoint"].endswith("/authorize")
    assert data["token_endpoint"].endswith("/token")
    assert data["registration_endpoint"].endswith("/register")


@pytest.mark.asyncio
async def test_protected_resource_metadata(client):
    response = await client.get("/.well-known/oauth-protected-resource/mcp")
    assert response.status_code == 200
    data = response.json()
    assert data["resource"].rstrip("/").endswith("/mcp")


@pytest.mark.asyncio
async def test_mcp_requires_auth(mcp_client):
    client, _app = mcp_client
    response = await client.post(
        "/mcp",
        headers={"Accept": "application/json, text/event-stream", "Content-Type": "application/json"},
        json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
    )
    assert response.status_code == 401
    assert "www-authenticate" in response.headers


@pytest.mark.asyncio
@patch("agentdrive.api.mcp.oauth.auth_service.workos_client")
async def test_oauth_issues_api_key(mock_workos, client):
    access_token = await _oauth_login(client, mock_workos)
    files = await client.get("/v1/files", headers={"Authorization": f"Bearer {access_token}"})
    assert files.status_code == 200


@pytest.mark.asyncio
@patch("agentdrive.core.search._get_engine")
async def test_search_and_list_tools(mock_get_engine, db_session, seeded_tenant):
    from agentdrive.api.mcp import tools as mcp_tools

    mock_engine = MagicMock()
    mock_engine.search = AsyncMock(
        return_value=[
            {
                "chunk_id": "abc",
                "content": "hello",
                "token_count": 1,
                "score": 0.9,
                "content_type": "text",
                "provenance": {"file_id": "def"},
            }
        ]
    )
    mock_get_engine.return_value = mock_engine

    search_text = await mcp_tools.search(db_session, seeded_tenant, "hello", top_k=3)
    search_payload = json.loads(search_text)
    assert search_payload["results"][0]["content"] == "hello"

    listed = json.loads(await mcp_tools.list_files(db_session, seeded_tenant))
    assert listed["total"] == 0
    assert listed["files"] == []


@pytest.mark.asyncio
@patch("agentdrive.core.files.StorageService")
async def test_start_and_complete_upload(mock_storage_cls, db_session, seeded_tenant):
    from agentdrive.api.mcp import tools as mcp_tools

    mock_storage = MagicMock()
    mock_storage.generate_path.return_value = "tenants/abc/files/def/notes.txt"
    mock_storage.generate_signed_upload_url.return_value = "https://storage.example/upload"
    mock_storage.blob_exists.return_value = True
    mock_storage.get_blob_size.return_value = 12
    mock_storage_cls.return_value = mock_storage

    started = json.loads(
        await mcp_tools.start_upload(
            db_session,
            seeded_tenant,
            filename="notes.txt",
            file_size=12,
            mime_type="text/plain",
        )
    )
    assert started["upload_url"] == "https://storage.example/upload"
    assert "file_id" in started
    assert "PUT" in started["instructions"]

    completed = json.loads(await mcp_tools.complete_upload(db_session, seeded_tenant, started["file_id"]))
    assert completed["status"] == "pending"
    assert completed["file_size"] == 12


@pytest.mark.asyncio
@patch("agentdrive.core.files.StorageService")
async def test_download_returns_url(mock_storage_cls, db_session, seeded_tenant):
    from agentdrive.api.mcp import tools as mcp_tools

    file_id = uuid.uuid4()
    db_session.add(
        FileModel(
            id=file_id,
            tenant_id=seeded_tenant.id,
            filename="report.pdf",
            content_type="pdf",
            gcs_path=f"tenants/{seeded_tenant.id}/files/{file_id}/report.pdf",
            file_size=100,
            status=FileStatus.READY,
        )
    )
    await db_session.commit()

    mock_storage = MagicMock()
    mock_storage.blob_exists.return_value = True
    mock_storage.generate_signed_download_url.return_value = "https://storage.example/download"
    mock_storage_cls.return_value = mock_storage

    payload = json.loads(await mcp_tools.download_file(db_session, seeded_tenant, str(file_id)))
    assert payload["download_url"] == "https://storage.example/download"
    assert payload["filename"] == "report.pdf"
    assert "local_path" not in payload


@pytest.mark.asyncio
@patch("agentdrive.core.files.StorageService")
async def test_delete_and_status_tools(mock_storage_cls, db_session, seeded_tenant):
    from agentdrive.api.mcp import tools as mcp_tools

    file_id = uuid.uuid4()
    db_session.add(
        FileModel(
            id=file_id,
            tenant_id=seeded_tenant.id,
            filename="gone.txt",
            content_type="text",
            gcs_path=f"tenants/{seeded_tenant.id}/files/{file_id}/gone.txt",
            file_size=3,
            status=FileStatus.READY,
        )
    )
    await db_session.commit()
    mock_storage_cls.return_value = MagicMock()

    status = json.loads(await mcp_tools.get_file_status(db_session, seeded_tenant, str(file_id)))
    assert status["filename"] == "gone.txt"
    assert await mcp_tools.delete_file(db_session, seeded_tenant, str(file_id)) == "File deleted successfully."


@pytest.mark.asyncio
@patch("agentdrive.core.files.StorageService")
@patch("agentdrive.core.search._get_engine")
@patch("agentdrive.api.mcp.oauth.auth_service.workos_client")
async def test_oauth_token_drives_hosted_tools(
    mock_workos, mock_get_engine, mock_storage_cls, client, db_session
):
    from agentdrive.api.mcp import tools as mcp_tools
    from agentdrive.api.mcp.deps import mcp_session
    from agentdrive.api.dependencies import _tenant_from_api_key

    mock_engine = MagicMock()
    mock_engine.search = AsyncMock(return_value=[])
    mock_get_engine.return_value = mock_engine
    mock_storage = MagicMock()
    mock_storage.generate_path.return_value = "tenants/abc/files/def/a.txt"
    mock_storage.generate_signed_upload_url.return_value = "https://storage.example/put"
    mock_storage.blob_exists.return_value = True
    mock_storage.get_blob_size.return_value = 4
    mock_storage_cls.return_value = mock_storage

    access_token = await _oauth_login(client, mock_workos)
    async with mcp_session() as session:
        tenant = await _tenant_from_api_key(session, access_token)
        assert tenant is not None
        listed = json.loads(await mcp_tools.list_files(session, tenant))
        assert listed["total"] == 0
        searched = json.loads(await mcp_tools.search(session, tenant, "anything"))
        assert searched["results"] == []
        started = json.loads(
            await mcp_tools.start_upload(session, tenant, filename="a.txt", file_size=4, mime_type="text/plain")
        )
        completed = json.loads(await mcp_tools.complete_upload(session, tenant, started["file_id"]))
    assert completed["status"] == "pending"


@pytest.mark.asyncio
@patch("agentdrive.api.mcp.oauth.auth_service.workos_client")
async def test_mcp_initialize_with_oauth_token(mock_workos, mcp_client):
    client, app = mcp_client
    access_token = await _oauth_login(client, mock_workos)
    async with app.state.mcp.session_manager.run():
        response = await client.post(
            "/mcp",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
            },
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "hosted-mcp-test", "version": "0.0.1"},
                },
            },
        )
    assert response.status_code == 200
    assert "agent-drive" in response.text
