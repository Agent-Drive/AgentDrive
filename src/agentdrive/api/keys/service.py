import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentdrive.engine.data.models.api_key import ApiKey
from agentdrive.engine.data.models.tenant import Tenant
from agentdrive.api.keys.schemas import (
    ApiKeyCreate,
    ApiKeyCreateResponse,
    ApiKeyListResponse,
    ApiKeyResponse,
)
from agentdrive.api.auth.service import generate_api_key


async def create_api_key(
    session: AsyncSession, tenant: Tenant, body: ApiKeyCreate
) -> ApiKeyCreateResponse:
    raw_key, prefix, key_hash = generate_api_key()
    api_key = ApiKey(
        tenant_id=tenant.id,
        key_prefix=prefix,
        key_hash=key_hash,
        name=body.name,
        expires_at=body.expires_at,
    )
    session.add(api_key)
    await session.commit()
    await session.refresh(api_key)
    return ApiKeyCreateResponse(
        id=api_key.id,
        key=raw_key,
        key_prefix=prefix,
        name=api_key.name,
        created_at=api_key.created_at,
        expires_at=api_key.expires_at,
    )


async def list_api_keys(session: AsyncSession, tenant: Tenant) -> ApiKeyListResponse:
    result = await session.execute(
        select(ApiKey)
        .where(ApiKey.tenant_id == tenant.id)
        .order_by(ApiKey.created_at)
    )
    keys = result.scalars().all()
    return ApiKeyListResponse(
        api_keys=[ApiKeyResponse.model_validate(k) for k in keys],
        total=len(keys),
    )


async def revoke_api_key(session: AsyncSession, tenant: Tenant, key_id: uuid.UUID) -> None:
    result = await session.execute(
        select(ApiKey).where(ApiKey.id == key_id, ApiKey.tenant_id == tenant.id)
    )
    api_key = result.scalar_one_or_none()
    if not api_key:
        raise HTTPException(status_code=404, detail="API key not found")
    api_key.revoked_at = datetime.now(timezone.utc)
    await session.commit()
