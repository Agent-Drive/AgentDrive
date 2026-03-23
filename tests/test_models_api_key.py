import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentdrive.models.api_key import ApiKey
from agentdrive.models.tenant import Tenant


@pytest.mark.asyncio
async def test_create_api_key(db_session: AsyncSession):
    tenant = Tenant(name="Test Tenant")
    db_session.add(tenant)
    await db_session.flush()

    api_key = ApiKey(
        tenant_id=tenant.id,
        key_prefix="abc12345",
        key_hash="$2b$12$fakehashvalue",
        name="production",
    )
    db_session.add(api_key)
    await db_session.flush()

    result = await db_session.execute(select(ApiKey).where(ApiKey.tenant_id == tenant.id))
    keys = result.scalars().all()
    assert len(keys) == 1
    assert keys[0].key_prefix == "abc12345"
    assert keys[0].name == "production"
    assert keys[0].revoked_at is None
    assert keys[0].expires_at is None


@pytest.mark.asyncio
async def test_tenant_has_api_keys_relationship(db_session: AsyncSession):
    tenant = Tenant(name="Test Tenant")
    db_session.add(tenant)
    await db_session.flush()

    key1 = ApiKey(tenant_id=tenant.id, key_prefix="key1pre1", key_hash="hash1", name="dev")
    key2 = ApiKey(tenant_id=tenant.id, key_prefix="key2pre2", key_hash="hash2", name="prod")
    db_session.add_all([key1, key2])
    await db_session.flush()

    await db_session.refresh(tenant, ["api_keys"])
    assert len(tenant.api_keys) == 2
