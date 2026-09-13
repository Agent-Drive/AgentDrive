import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from agentdrive.engine.data.session import get_session
from agentdrive.api.dependencies import get_current_tenant
from agentdrive.engine.data.models.tenant import Tenant
from agentdrive.api.search import service
from agentdrive.api.search.schemas import SearchRequest, SearchResponse

router = APIRouter(prefix="/v1", tags=["search"])


@router.post("/search", response_model=SearchResponse)
async def search(
    body: SearchRequest,
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
):
    return await service.search(session, tenant, body)


@router.get("/chunks/{chunk_id}")
async def get_chunk(
    chunk_id: uuid.UUID,
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
):
    return await service.get_chunk(session, tenant, chunk_id)
