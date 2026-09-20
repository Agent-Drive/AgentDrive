from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentdrive.core.data.models.api_key import ApiKey
from agentdrive.core.data.models.tenant import Tenant
from agentdrive.api.auth.service import generate_api_key


def _workos_user(user_id: str, email: str = "web@example.com", first="Web", last="User"):
    user = MagicMock()
    user.id = user_id
    user.email = email
    user.first_name = first
    user.last_name = last
    return user


@pytest.mark.asyncio
async def test_workos_token_existing_tenant_lists_files(client, db_session: AsyncSession):
    tenant = Tenant(name="Existing Web User", workos_user_id="workos-web-456")
    db_session.add(tenant)
    await db_session.commit()

    with patch("agentdrive.api.auth.service.get_workos_user") as mock_get_user:
        mock_get_user.return_value = _workos_user("workos-web-456")
        response = await client.get(
            "/v1/files",
            headers={"Authorization": "Bearer fake-workos-access-token"},
        )

    assert response.status_code == 200
    assert response.json()["files"] == []
    assert response.json()["total"] == 0


@pytest.mark.asyncio
async def test_workos_token_unknown_user_auto_provisions(client, db_session: AsyncSession):
    with patch("agentdrive.api.auth.service.get_workos_user") as mock_get_user:
        mock_get_user.return_value = _workos_user("workos-web-new")
        response = await client.get(
            "/v1/files",
            headers={"Authorization": "Bearer fake-workos-access-token"},
        )

    assert response.status_code == 200
    result = await db_session.execute(
        select(Tenant).where(Tenant.workos_user_id == "workos-web-new")
    )
    tenant = result.scalar_one()
    assert tenant.name == "Web User"


@pytest.mark.asyncio
async def test_workos_token_auto_provision_disabled(client, db_session: AsyncSession):
    with patch("agentdrive.api.auth.service.get_workos_user") as mock_get_user, \
         patch("agentdrive.api.auth.service.settings") as mock_settings:
        mock_get_user.return_value = _workos_user("workos-web-blocked")
        mock_settings.auto_provision_tenants = False
        response = await client.get(
            "/v1/files",
            headers={"Authorization": "Bearer fake-workos-access-token"},
        )

    assert response.status_code == 403
    result = await db_session.execute(
        select(Tenant).where(Tenant.workos_user_id == "workos-web-blocked")
    )
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_workos_token_invalid(client):
    with patch("agentdrive.api.auth.service.get_workos_user") as mock_get_user:
        mock_get_user.return_value = None
        response = await client.get(
            "/v1/files",
            headers={"Authorization": "Bearer not-a-valid-token"},
        )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_sk_ad_key_still_works_alongside_workos_path(client, db_session: AsyncSession):
    tenant = Tenant(name="Key Tenant")
    db_session.add(tenant)
    await db_session.flush()
    raw_key, prefix, key_hash = generate_api_key()
    db_session.add(ApiKey(tenant_id=tenant.id, key_prefix=prefix, key_hash=key_hash, name="test"))
    await db_session.commit()

    response = await client.get("/v1/files", headers={"Authorization": f"Bearer {raw_key}"})
    assert response.status_code == 200
