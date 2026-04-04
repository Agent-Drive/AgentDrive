import time
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from agentdrive.embedding.client import EmbeddingClient
from agentdrive.models.chunk import ParentChunk
from agentdrive.search.bm25 import article_bm25_search, bm25_search
from agentdrive.search.fusion import reciprocal_rank_fusion
from agentdrive.search.rerank import rerank_results
from agentdrive.search.vector import article_vector_search, vector_search


class SearchEngine:
    def __init__(self) -> None:
        self._embedding_client = EmbeddingClient()

    async def search(
        self,
        query: str,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        top_k: int = 5,
        content_types: list[str] | None = None,
        include_parent: bool = True,
    ) -> list[dict]:
        # Step 1: Embed query
        query_vector_full = self._embedding_client.embed_query(query)
        query_vector_256 = self._embedding_client.truncate(query_vector_full, 256)

        # Step 2: Parallel retrieval
        vector_results = await vector_search(
            query_vector_256, session, tenant_id, top_k=50,
            content_types=content_types,
        )
        bm25_results = await bm25_search(query, session, tenant_id, top_k=50)

        # Step 3: RRF
        fused = reciprocal_rank_fusion([vector_results, bm25_results], k=60, top_k=20)

        # Step 4: Rerank
        reranked = rerank_results(query, fused, top_k=top_k)

        # Step 5: Parent lookup
        results = []
        for r in reranked:
            entry = {
                "chunk_id": str(r.chunk_id),
                "content": r.content,
                "token_count": r.token_count,
                "score": r.score,
                "content_type": r.content_type,
                "provenance": {"file_id": str(r.file_id), **r.metadata},
            }
            if include_parent and r.parent_chunk_id:
                parent = await session.get(ParentChunk, r.parent_chunk_id)
                if parent:
                    entry["parent_content"] = parent.content
                    entry["parent_token_count"] = parent.token_count
            results.append(entry)

        return results

    async def search_kb(
        self,
        query: str,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        kb_id: uuid.UUID,
        top_k: int = 5,
        articles_only: bool = False,
        content_types: list[str] | None = None,
        include_parent: bool = True,
    ) -> dict:
        start = time.monotonic()

        query_vector_full = self._embedding_client.embed_query(query)
        query_vector_256 = self._embedding_client.truncate(query_vector_full, 256)

        # Always search articles
        result_lists: list[list] = []
        article_vec = await article_vector_search(query_vector_256, session, kb_id, top_k=50)
        article_bm25 = await article_bm25_search(query, session, kb_id, top_k=50)
        result_lists.extend([article_vec, article_bm25])

        # Optionally search chunks scoped to KB files
        if not articles_only:
            chunk_vec = await vector_search(
                query_vector_256, session, tenant_id, top_k=50,
                content_types=content_types, kb_id=kb_id,
            )
            chunk_bm25 = await bm25_search(query, session, tenant_id, top_k=50, kb_id=kb_id)
            result_lists.extend([chunk_vec, chunk_bm25])

        fused = reciprocal_rank_fusion(result_lists, k=60, top_k=20)
        reranked = rerank_results(query, fused, top_k=top_k)

        results = []
        for r in reranked:
            is_article = r.metadata.get("result_type") == "article"
            item: dict = {
                "result_type": "article" if is_article else "chunk",
                "id": str(r.chunk_id),
                "content": r.content,
                "score": r.score,
            }
            if is_article:
                item["title"] = r.metadata.get("title")
                item["article_type"] = r.content_type
                item["category"] = r.metadata.get("category")
            else:
                item["file_id"] = str(r.file_id)
                item["context_prefix"] = r.context_prefix
                item["content_type"] = r.content_type
                if include_parent and r.parent_chunk_id:
                    parent = await session.get(ParentChunk, r.parent_chunk_id)
                    if parent:
                        item["parent_content"] = parent.content
            results.append(item)

        elapsed_ms = int((time.monotonic() - start) * 1000)
        return {
            "results": results,
            "query_tokens": len(query.split()),
            "search_time_ms": elapsed_ms,
        }
