from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentdrive.db.session import get_session
from agentdrive.models.tenant import Tenant
from agentdrive.services.auth import verify_api_key

security = HTTPBearer()


async def get_current_tenant(
    credentials: HTTPAuthorizationCredentials = Security(security),
    session: AsyncSession = Depends(get_session),
) -> Tenant:
    api_key = credentials.credentials
    result = await session.execute(select(Tenant))
    tenants = result.scalars().all()
    for tenant in tenants:
        if verify_api_key(api_key, tenant.api_key_hash):
            return tenant
    raise HTTPException(status_code=401, detail="Invalid API key")
