import logging
import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from agentdrive.embedding.client import EmbeddingClient
from agentdrive.knowledge.models import Article

logger = logging.getLogger(__name__)


async def embed_articles(kb_id: uuid.UUID, session: AsyncSession) -> int:
    """Phase 5e: Embed all articles that need embedding."""
    result = await session.execute(
        select(Article).where(Article.knowledge_base_id == kb_id)
    )
    articles = result.scalars().all()
    if not articles:
        return 0

    client = EmbeddingClient()
    embedded = 0

    for article in articles:
        content = f"{article.title}\n\n{article.content}"
        try:
            vectors = client.embed([content], input_type="document")
            full_vector = vectors[0]
            vector_256 = client.truncate(full_vector, 256)

            vec_256_str = "[" + ",".join(str(v) for v in vector_256) + "]"
            vec_full_str = "[" + ",".join(str(v) for v in full_vector) + "]"

            await session.execute(
                text(
                    "UPDATE articles SET embedding = CAST(:vec256 AS halfvec(256)), "
                    "embedding_full = CAST(:vec_full AS halfvec(1024)) WHERE id = :id"
                ),
                {
                    "vec256": vec_256_str,
                    "vec_full": vec_full_str,
                    "id": str(article.id),
                },
            )
            embedded += 1
        except Exception as e:
            logger.warning(f"Failed to embed article {article.id}: {e}")

    await session.flush()
    return embedded
