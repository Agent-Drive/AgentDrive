import logging
import uuid
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from agentdrive.embedding.client import EmbeddingClient
from agentdrive.models.chunk import Chunk

logger = logging.getLogger(__name__)
BATCH_SIZE = 64


async def embed_file_chunks(file_id: uuid.UUID, session: AsyncSession) -> int:
    client = EmbeddingClient()
    result = await session.execute(
        select(Chunk).where(Chunk.file_id == file_id).order_by(Chunk.chunk_index)
    )
    chunks = result.scalars().all()
    if not chunks:
        return 0

    embedded_count = 0
    for i in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[i:i + BATCH_SIZE]
        texts = [f"{c.context_prefix}\n{c.content}" if c.context_prefix else c.content for c in batch]
        content_type = batch[0].content_type
        vectors_full = client.embed(texts, input_type="document", content_type=content_type)

        for chunk, vector in zip(batch, vectors_full):
            vector_256 = client.truncate(vector, 256)
            vec_256_str = "[" + ",".join(str(v) for v in vector_256) + "]"
            vec_full_str = "[" + ",".join(str(v) for v in vector) + "]"
            await session.execute(
                text(
                    "UPDATE chunks SET embedding = :emb, embedding_full = :emb_full"
                    " WHERE id = :chunk_id"
                ),
                {"emb": vec_256_str, "emb_full": vec_full_str, "chunk_id": chunk.id},
            )
            embedded_count += 1

    await session.commit()
    logger.info(f"Embedded {embedded_count} chunks for file {file_id}")
    return embedded_count
