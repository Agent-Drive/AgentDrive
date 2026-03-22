import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from agentdrive.embedding.client import EmbeddingClient
from agentdrive.models.chunk import ParentChunk
from agentdrive.search.bm25 import bm25_search
from agentdrive.search.fusion import reciprocal_rank_fusion
from agentdrive.search.rerank import rerank_results
from agentdrive.search.vector import vector_search


class SearchEngine:
    def __init__(self) -> None:
        self._embedding_client = EmbeddingClient()

    async def search(
        self,
        query: str,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        top_k: int = 5,
        collections: list[uuid.UUID] | None = None,
        content_types: list[str] | None = None,
        include_parent: bool = True,
    ) -> list[dict]:
        # Step 1: Embed query
        query_vector_full = self._embedding_client.embed_query(query)
        query_vector_256 = self._embedding_client.truncate(query_vector_full, 256)

        # Step 2: Parallel retrieval
        vector_results = await vector_search(
            query_vector_256, session, tenant_id, top_k=50,
            collections=collections, content_types=content_types,
        )
        bm25_results = await bm25_search(query, session, tenant_id, top_k=50, collections=collections)

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
