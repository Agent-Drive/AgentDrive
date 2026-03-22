import time
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from agentdrive.chunking.tokens import count_tokens
from agentdrive.db.session import get_session
from agentdrive.dependencies import get_current_tenant
from agentdrive.models.chunk import Chunk
from agentdrive.models.file import File
from agentdrive.models.tenant import Tenant
from agentdrive.schemas.search import SearchRequest, SearchResponse, SearchResultResponse
from agentdrive.search.engine import SearchEngine

router = APIRouter(prefix="/v1", tags=["search"])
_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        _engine = SearchEngine()
    return _engine


@router.post("/search", response_model=SearchResponse)
async def search(
    body: SearchRequest,
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
):
    start = time.monotonic()
    engine = _get_engine()
    results = await engine.search(
        query=body.query, session=session, tenant_id=tenant.id,
        top_k=body.top_k, collections=body.collections,
        content_types=body.content_types, include_parent=body.include_parent,
    )
    elapsed_ms = int((time.monotonic() - start) * 1000)
    return SearchResponse(
        results=[SearchResultResponse(**r) for r in results],
        query_tokens=count_tokens(body.query),
        search_time_ms=elapsed_ms,
    )


@router.get("/chunks/{chunk_id}")
async def get_chunk(
    chunk_id: uuid.UUID,
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
):
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
