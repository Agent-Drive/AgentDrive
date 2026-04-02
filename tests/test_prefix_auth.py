import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from agentdrive.models.api_key import ApiKey
from agentdrive.models.tenant import Tenant
from agentdrive.services.auth import generate_api_key, hash_api_key

NEW_FORMAT_KEY = None
LEGACY_KEY = "old-style-key-no-prefix"


@pytest_asyncio.fixture
async def tenant_with_new_key(db_session: AsyncSession):
    tenant = Tenant(name="New Format Tenant")
    db_session.add(tenant)
    await db_session.flush()
    raw_key, prefix, key_hash = generate_api_key()
    api_key = ApiKey(tenant_id=tenant.id, key_prefix=prefix, key_hash=key_hash, name="test")
    db_session.add(api_key)
    await db_session.commit()
    return tenant, raw_key


@pytest_asyncio.fixture
async def tenant_with_legacy_key(db_session: AsyncSession):
    tenant = Tenant(name="Legacy Tenant")
    db_session.add(tenant)
    await db_session.flush()
    api_key = ApiKey(tenant_id=tenant.id, key_prefix="legacy__", key_hash=hash_api_key(LEGACY_KEY), name="migrated")
    db_session.add(api_key)
    await db_session.commit()
    return tenant


@pytest.mark.asyncio
async def test_auth_with_new_format_key(client, tenant_with_new_key):
    tenant, raw_key = tenant_with_new_key
    response = await client.get("/v1/files", headers={"Authorization": f"Bearer {raw_key}"})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_auth_with_legacy_key(client, tenant_with_legacy_key):
    response = await client.get("/v1/files", headers={"Authorization": f"Bearer {LEGACY_KEY}"})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_auth_with_revoked_key(client, db_session: AsyncSession, tenant_with_new_key):
    tenant, raw_key = tenant_with_new_key
    from datetime import datetime, timezone
    from sqlalchemy import update
    from agentdrive.models.api_key import ApiKey as AK
    await db_session.execute(update(AK).where(AK.tenant_id == tenant.id).values(revoked_at=datetime.now(timezone.utc)))
    await db_session.commit()
    response = await client.get("/v1/files", headers={"Authorization": f"Bearer {raw_key}"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_auth_with_invalid_key(client):
    response = await client.get("/v1/files", headers={"Authorization": "Bearer sk-ad-totally-fake-key-abc123"})
    assert response.status_code == 401
