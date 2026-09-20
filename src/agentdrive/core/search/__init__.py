import time
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentdrive.core.data.models.chunk import Chunk
from agentdrive.core.data.models.file import File
from agentdrive.core.data.models.tenant import Tenant
from agentdrive.core.errors import ChunkNotFound
from agentdrive.core.pipeline.chunking.tokens import count_tokens
from agentdrive.core.search.engine import SearchEngine

__all__ = ["SearchEngine", "get_chunk", "search"]

_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        _engine = SearchEngine()
    return _engine


async def search(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    query: str,
    top_k: int = 5,
    content_types: list[str] | None = None,
    include_parent: bool = True,
) -> dict:
    start = time.monotonic()
    results = await _get_engine().search(
        query=query,
        session=session,
        tenant_id=tenant_id,
        top_k=top_k,
        content_types=content_types,
        include_parent=include_parent,
    )
    return {
        "results": results,
        "query_tokens": count_tokens(query),
        "search_time_ms": int((time.monotonic() - start) * 1000),
    }


async def get_chunk(session: AsyncSession, tenant: Tenant, chunk_id: uuid.UUID) -> dict:
    result = await session.execute(
        select(Chunk).join(File).where(Chunk.id == chunk_id, File.tenant_id == tenant.id)
    )
    chunk = result.scalar_one_or_none()
    if not chunk:
        raise ChunkNotFound()
    return {
        "chunk_id": str(chunk.id), "file_id": str(chunk.file_id),
        "content": chunk.content, "context_prefix": chunk.context_prefix,
        "token_count": chunk.token_count, "content_type": chunk.content_type,
    }
