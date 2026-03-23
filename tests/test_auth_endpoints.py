from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentdrive.models.api_key import ApiKey
from agentdrive.models.tenant import Tenant


@pytest.mark.asyncio
async def test_exchange_creates_tenant(client, db_session: AsyncSession):
    mock_user = MagicMock()
    mock_user.id = "workos-user-123"
    mock_user.email = "test@example.com"
    mock_user.first_name = "Test"
    mock_user.last_name = "User"

    with patch("agentdrive.routers.auth.get_workos_user") as mock_get_user:
        mock_get_user.return_value = mock_user
        response = await client.post("/auth/exchange", json={"access_token": "fake-workos-access-token"})

    assert response.status_code == 200
    data = response.json()
    assert data["api_key"].startswith("sk-ad-")
    assert data["email"] == "test@example.com"
    assert "tenant_id" in data

    result = await db_session.execute(select(Tenant).where(Tenant.workos_user_id == "workos-user-123"))
    tenant = result.scalar_one()
    assert tenant.name == "Test User"


@pytest.mark.asyncio
async def test_exchange_existing_tenant(client, db_session: AsyncSession):
    tenant = Tenant(name="Existing User", api_key_hash="unused", workos_user_id="workos-user-456")
    db_session.add(tenant)
    await db_session.commit()
    await db_session.refresh(tenant)

    mock_user = MagicMock()
    mock_user.id = "workos-user-456"
    mock_user.email = "existing@example.com"
    mock_user.first_name = "Existing"
    mock_user.last_name = "User"

    with patch("agentdrive.routers.auth.get_workos_user") as mock_get_user:
        mock_get_user.return_value = mock_user
        response = await client.post("/auth/exchange", json={"access_token": "fake-workos-access-token"})

    assert response.status_code == 200
    data = response.json()
    assert data["tenant_id"] == str(tenant.id)


@pytest.mark.asyncio
async def test_exchange_invalid_token(client):
    with patch("agentdrive.routers.auth.get_workos_user") as mock_get_user:
        mock_get_user.return_value = None
        response = await client.post("/auth/exchange", json={"access_token": "invalid-token"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_exchange_auto_provision_disabled(client, db_session: AsyncSession):
    mock_user = MagicMock()
    mock_user.id = "workos-user-new"
    mock_user.email = "new@example.com"
    mock_user.first_name = "New"
    mock_user.last_name = "User"

    with patch("agentdrive.routers.auth.get_workos_user") as mock_get_user, \
         patch("agentdrive.routers.auth.settings") as mock_settings:
        mock_get_user.return_value = mock_user
        mock_settings.auto_provision_tenants = False
        mock_settings.workos_api_key = "fake"
        mock_settings.workos_client_id = "fake"
        response = await client.post("/auth/exchange", json={"access_token": "fake-workos-access-token"})
    assert response.status_code == 403
