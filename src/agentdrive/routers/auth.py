from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentdrive.config import settings
from agentdrive.db.session import get_session
from agentdrive.models.api_key import ApiKey
from agentdrive.models.tenant import Tenant
from agentdrive.services.auth import generate_api_key

workos_client = None
if settings.workos_api_key and settings.workos_client_id:
    from workos import WorkOSClient

    workos_client = WorkOSClient(
        api_key=settings.workos_api_key,
        client_id=settings.workos_client_id,
    )


class ExchangeRequest(BaseModel):
    access_token: str


class ExchangeResponse(BaseModel):
    api_key: str
    email: str
    tenant_id: str


router = APIRouter(prefix="/auth", tags=["auth"])


def get_workos_user(access_token: str):
    """Decode WorkOS JWT access token, verify it, and return user. Returns None if invalid."""
    if not workos_client:
        return None
    try:
        import jwt

        payload = jwt.decode(access_token, options={"verify_signature": False})
        user_id = payload.get("sub")
        if not user_id:
            return None
        user = workos_client.user_management.get_user(user_id=user_id)
        return user
    except Exception:
        return None


@router.post("/exchange", response_model=ExchangeResponse)
async def exchange_token(
    body: ExchangeRequest,
    session: AsyncSession = Depends(get_session),
):
    """Exchange a WorkOS access token for an Agent Drive sk-ad- API key."""
    user = get_workos_user(body.access_token)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid or expired WorkOS token")

    result = await session.execute(
        select(Tenant).where(Tenant.workos_user_id == user.id)
    )
    tenant = result.scalar_one_or_none()

    if tenant is None:
        if not settings.auto_provision_tenants:
            raise HTTPException(status_code=403, detail="Auto-provisioning is disabled. Contact your admin.")
        name = f"{user.first_name or ''} {user.last_name or ''}".strip() or user.email
        tenant = Tenant(name=name, api_key_hash="unused", workos_user_id=user.id)
        session.add(tenant)
        await session.flush()

    raw_key, prefix, key_hash = generate_api_key()
    api_key = ApiKey(tenant_id=tenant.id, key_prefix=prefix, key_hash=key_hash, name="cli-login")
    session.add(api_key)
    await session.commit()

    return ExchangeResponse(api_key=raw_key, email=user.email, tenant_id=str(tenant.id))
