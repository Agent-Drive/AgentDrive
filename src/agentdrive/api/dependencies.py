from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from agentdrive.engine.data.session import get_session
from agentdrive.engine.data.models.api_key import ApiKey
from agentdrive.engine.data.models.tenant import Tenant
from agentdrive.api.auth import service as auth_service
from agentdrive.api.auth.service import parse_key_prefix, verify_api_key

security = HTTPBearer()


async def _tenant_from_api_key(session: AsyncSession, api_key: str) -> Tenant | None:
    prefix = parse_key_prefix(api_key)

    if prefix is not None:
        result = await session.execute(
            select(ApiKey)
            .where(ApiKey.key_prefix == prefix, ApiKey.revoked_at.is_(None))
            .filter((ApiKey.expires_at.is_(None)) | (ApiKey.expires_at > datetime.now(timezone.utc)))
        )
        candidates = result.scalars().all()
    else:
        result = await session.execute(
            select(ApiKey).where(ApiKey.key_prefix == "legacy__", ApiKey.revoked_at.is_(None))
        )
        candidates = result.scalars().all()

    for candidate in candidates:
        if verify_api_key(api_key, candidate.key_hash):
            await session.execute(
                update(ApiKey).where(ApiKey.id == candidate.id).values(last_used=datetime.now(timezone.utc))
            )
            await session.commit()
            tenant_result = await session.execute(select(Tenant).where(Tenant.id == candidate.tenant_id))
            return tenant_result.scalar_one_or_none()
    return None


async def get_current_tenant(
    credentials: HTTPAuthorizationCredentials = Security(security),
    session: AsyncSession = Depends(get_session),
) -> Tenant:
    token = credentials.credentials
    tenant = await _tenant_from_api_key(session, token)
    if tenant:
        return tenant

    user = auth_service.get_workos_user(token)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid API key")

    tenant = await auth_service.get_or_create_tenant_for_workos_user(session, user)
    await session.commit()
    return tenant
