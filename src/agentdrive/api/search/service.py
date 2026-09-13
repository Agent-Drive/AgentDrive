import time
import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentdrive.engine.pipeline.chunking.tokens import count_tokens
from agentdrive.engine.data.models.chunk import Chunk
from agentdrive.engine.data.models.file import File
from agentdrive.engine.data.models.tenant import Tenant
from agentdrive.api.search.schemas import SearchRequest, SearchResponse, SearchResultResponse
from agentdrive.engine.search.engine import SearchEngine

_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        _engine = SearchEngine()
    return _engine


async def search(session: AsyncSession, tenant: Tenant, body: SearchRequest) -> SearchResponse:
    start = time.monotonic()
    engine = _get_engine()
    results = await engine.search(
        query=body.query, session=session, tenant_id=tenant.id,
        top_k=body.top_k,
        content_types=body.content_types, include_parent=body.include_parent,
    )
    elapsed_ms = int((time.monotonic() - start) * 1000)
    return SearchResponse(
        results=[SearchResultResponse(**r) for r in results],
        query_tokens=count_tokens(body.query),
        search_time_ms=elapsed_ms,
    )


async def get_chunk(session: AsyncSession, tenant: Tenant, chunk_id: uuid.UUID) -> dict:
    result = await session.execute(
        select(Chunk).join(File).where(Chunk.id == chunk_id, File.tenant_id == tenant.id)
    )
    chunk = result.scalar_one_or_none()
    if not chunk:
        raise HTTPException(status_code=404, detail="Chunk not found")
    return {
        "chunk_id": str(chunk.id), "file_id": str(chunk.file_id),
        "content": chunk.content, "context_prefix": chunk.context_prefix,
        "token_count": chunk.token_count, "content_type": chunk.content_type,
    }
