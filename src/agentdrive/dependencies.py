from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from agentdrive.db.session import get_session
from agentdrive.models.api_key import ApiKey
from agentdrive.models.tenant import Tenant
from agentdrive.services.auth import parse_key_prefix, verify_api_key

security = HTTPBearer()


async def get_current_tenant(
    credentials: HTTPAuthorizationCredentials = Security(security),
    session: AsyncSession = Depends(get_session),
) -> Tenant:
    api_key = credentials.credentials
    prefix = parse_key_prefix(api_key)

    if prefix is not None:
        result = await session.execute(
            select(ApiKey)
            .where(ApiKey.key_prefix == prefix, ApiKey.revoked_at.is_(None))
            .filter((ApiKey.expires_at.is_(None)) | (ApiKey.expires_at > datetime.now(timezone.utc)))
        )
        candidates = result.scalars().all()
        for candidate in candidates:
            if verify_api_key(api_key, candidate.key_hash):
                await session.execute(
                    update(ApiKey).where(ApiKey.id == candidate.id).values(last_used=datetime.now(timezone.utc))
                )
                await session.commit()
                tenant_result = await session.execute(select(Tenant).where(Tenant.id == candidate.tenant_id))
                tenant = tenant_result.scalar_one_or_none()
                if tenant:
                    return tenant
    else:
        result = await session.execute(
            select(ApiKey).where(ApiKey.key_prefix == "legacy__", ApiKey.revoked_at.is_(None))
        )
        legacy_keys = result.scalars().all()
        for candidate in legacy_keys:
            if verify_api_key(api_key, candidate.key_hash):
                await session.execute(
                    update(ApiKey).where(ApiKey.id == candidate.id).values(last_used=datetime.now(timezone.utc))
                )
                await session.commit()
                tenant_result = await session.execute(select(Tenant).where(Tenant.id == candidate.tenant_id))
                tenant = tenant_result.scalar_one_or_none()
                if tenant:
                    return tenant

    raise HTTPException(status_code=401, detail="Invalid API key")
