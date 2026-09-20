import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from agentdrive.api.errors import raise_http
from agentdrive.api.search.schemas import SearchRequest, SearchResponse, SearchResultResponse
from agentdrive.core import search as core_search
from agentdrive.core.data.models.tenant import Tenant
from agentdrive.core.errors import CoreError


async def search(session: AsyncSession, tenant: Tenant, body: SearchRequest) -> SearchResponse:
    try:
        payload = await core_search.search(
            session,
            tenant.id,
            body.query,
            top_k=body.top_k,
            content_types=body.content_types,
            include_parent=body.include_parent,
        )
    except CoreError as exc:
        raise_http(exc)
    return SearchResponse(
        results=[SearchResultResponse(**r) for r in payload["results"]],
        query_tokens=payload["query_tokens"],
        search_time_ms=payload["search_time_ms"],
    )


async def get_chunk(session: AsyncSession, tenant: Tenant, chunk_id: uuid.UUID) -> dict:
    try:
        return await core_search.get_chunk(session, tenant, chunk_id)
    except CoreError as exc:
        raise_http(exc)
