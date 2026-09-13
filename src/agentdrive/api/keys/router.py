import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from agentdrive.engine.data.session import get_session
from agentdrive.api.dependencies import get_current_tenant
from agentdrive.engine.data.models.tenant import Tenant
from agentdrive.api.keys import service
from agentdrive.api.keys.schemas import (
    ApiKeyCreate,
    ApiKeyCreateResponse,
    ApiKeyListResponse,
)

router = APIRouter(prefix="/v1/api-keys", tags=["api-keys"])


@router.post("", status_code=201, response_model=ApiKeyCreateResponse)
async def create_api_key(
    body: ApiKeyCreate,
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
):
    return await service.create_api_key(session, tenant, body)


@router.get("", response_model=ApiKeyListResponse)
async def list_api_keys(
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
):
    return await service.list_api_keys(session, tenant)


@router.delete("/{key_id}", status_code=204)
async def revoke_api_key(
    key_id: uuid.UUID,
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
):
    return await service.revoke_api_key(session, tenant, key_id)
