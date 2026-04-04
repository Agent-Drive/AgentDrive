import math
import uuid
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from agentdrive.search.vector import SearchResult

def bm25_score(tf: int, df: int, dl: int, avgdl: float, n_docs: int, k1: float = 1.2, b: float = 0.75) -> float:
    if tf == 0:
        return 0.0
    idf = math.log((n_docs - df + 0.5) / (df + 0.5) + 1)
    tf_norm = (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * (dl / avgdl)))
    return idf * tf_norm

async def bm25_search(
    query: str,
    session: AsyncSession,
    tenant_id: uuid.UUID,
    top_k: int = 50,
    kb_id: uuid.UUID | None = None,
) -> list[SearchResult]:
    where_clauses = [
        "f.tenant_id = :tenant_id",
        "f.status = 'ready'",
        "to_tsvector('english', c.content) @@ plainto_tsquery('english', :query)",
    ]
    params: dict = {"tenant_id": str(tenant_id), "query": query, "top_k": top_k}

    if kb_id:
        where_clauses.append("EXISTS (SELECT 1 FROM knowledge_base_files kbf WHERE kbf.file_id = f.id AND kbf.knowledge_base_id = :kb_id)")
        params["kb_id"] = str(kb_id)

    where = " AND ".join(where_clauses)

    sql = text(f"""
        SELECT c.id, c.file_id, c.content, c.context_prefix, c.token_count,
               c.content_type, c.metadata, c.parent_chunk_id,
               ts_rank(to_tsvector('english', c.content), plainto_tsquery('english', :query)) AS rank
        FROM chunks c
        JOIN files f ON c.file_id = f.id
        WHERE {where}
        ORDER BY rank DESC
        LIMIT :top_k
    """)

    result = await session.execute(sql, params)
    rows = result.fetchall()

    return [
        SearchResult(
            chunk_id=row.id, file_id=row.file_id, content=row.content,
            context_prefix=row.context_prefix, token_count=row.token_count,
            content_type=row.content_type, score=float(row.rank),
            metadata=row.metadata or {}, parent_chunk_id=row.parent_chunk_id,
        )
        for row in rows
    ]


async def article_bm25_search(
    query: str,
    session: AsyncSession,
    kb_id: uuid.UUID,
    top_k: int = 50,
) -> list[SearchResult]:
    sql = text("""
        SELECT a.id, a.title, a.content, a.article_type, a.category,
               a.token_count, a.knowledge_base_id,
               ts_rank(to_tsvector('english', a.content), plainto_tsquery('english', :query)) AS rank
        FROM articles a
        WHERE a.knowledge_base_id = :kb_id AND a.status = 'published'
          AND to_tsvector('english', a.content) @@ plainto_tsquery('english', :query)
        ORDER BY rank DESC
        LIMIT :top_k
    """)
    result = await session.execute(
        sql, {"query": query, "kb_id": str(kb_id), "top_k": top_k},
    )
    return [
        SearchResult(
            chunk_id=row.id,
            file_id=row.knowledge_base_id,
            content=row.content,
            context_prefix=row.title,
            token_count=row.token_count,
            content_type=row.article_type,
            score=float(row.rank),
            metadata={"result_type": "article", "category": row.category, "title": row.title},
        )
        for row in result.fetchall()
    ]
