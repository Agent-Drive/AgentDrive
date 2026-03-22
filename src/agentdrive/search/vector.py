import uuid
from dataclasses import dataclass
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

@dataclass
class SearchResult:
    chunk_id: uuid.UUID
    file_id: uuid.UUID
    content: str
    context_prefix: str
    token_count: int
    content_type: str
    score: float
    metadata: dict
    parent_chunk_id: uuid.UUID | None = None

async def vector_search(
    query_embedding: list[float],
    session: AsyncSession,
    tenant_id: uuid.UUID,
    top_k: int = 50,
    collections: list[uuid.UUID] | None = None,
    content_types: list[str] | None = None,
) -> list[SearchResult]:
    embedding_str = "[" + ",".join(str(v) for v in query_embedding) + "]"

    where_clauses = ["f.tenant_id = :tenant_id"]
    params: dict = {"tenant_id": str(tenant_id), "embedding": embedding_str, "top_k": top_k}

    if collections:
        where_clauses.append("f.collection_id = ANY(:collections)")
        params["collections"] = [str(c) for c in collections]

    if content_types:
        where_clauses.append("c.content_type = ANY(:content_types)")
        params["content_types"] = content_types

    where = " AND ".join(where_clauses)

    query = text(f"""
        SELECT c.id, c.file_id, c.content, c.context_prefix, c.token_count,
               c.content_type, c.metadata, c.parent_chunk_id,
               c.embedding <=> CAST(:embedding AS halfvec(256)) AS distance
        FROM chunks c
        JOIN files f ON c.file_id = f.id
        WHERE {where} AND c.embedding IS NOT NULL
        ORDER BY distance
        LIMIT :top_k
    """)

    result = await session.execute(query, params)
    rows = result.fetchall()

    results = [
        SearchResult(
            chunk_id=row.id, file_id=row.file_id, content=row.content,
            context_prefix=row.context_prefix, token_count=row.token_count,
            content_type=row.content_type, score=1.0 - row.distance,
            metadata=row.metadata or {}, parent_chunk_id=row.parent_chunk_id,
        )
        for row in rows
    ]

    # Also search chunk aliases (synthetic questions for tables)
    alias_query = text(f"""
        SELECT c.id, c.file_id, c.content, c.context_prefix, c.token_count,
               c.content_type, c.metadata, c.parent_chunk_id,
               ca.embedding <=> CAST(:embedding AS halfvec(256)) AS distance
        FROM chunk_aliases ca
        JOIN chunks c ON ca.chunk_id = c.id
        JOIN files f ON c.file_id = f.id
        WHERE {where} AND ca.embedding IS NOT NULL
        ORDER BY distance
        LIMIT :top_k
    """)

    alias_result = await session.execute(alias_query, params)
    alias_rows = alias_result.fetchall()

    # Deduplicate — prefer better score from main query
    seen_ids = {r.chunk_id for r in results}
    for row in alias_rows:
        if row.id not in seen_ids:
            results.append(SearchResult(
                chunk_id=row.id, file_id=row.file_id, content=row.content,
                context_prefix=row.context_prefix, token_count=row.token_count,
                content_type=row.content_type, score=1.0 - row.distance,
                metadata=row.metadata or {}, parent_chunk_id=row.parent_chunk_id,
            ))
            seen_ids.add(row.id)

    # Re-sort by score and limit
    results.sort(key=lambda r: r.score, reverse=True)
    results = results[:top_k]

    return results
