import logging
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from agentdrive.chunking.registry import ChunkerRegistry
from agentdrive.chunking.tokens import count_tokens
from agentdrive.enrichment.contextual import enrich_chunks
from agentdrive.enrichment.table_questions import generate_table_aliases
from agentdrive.models.chunk import Chunk, ParentChunk
from agentdrive.models.chunk_alias import ChunkAlias
from agentdrive.models.file import File
from agentdrive.models.types import FileStatus
from agentdrive.services.storage import StorageService
from agentdrive.embedding.pipeline import embed_file_chunks, embed_file_aliases

logger = logging.getLogger(__name__)
registry = ChunkerRegistry()


async def process_file(file_id: uuid.UUID, session: AsyncSession) -> None:
    result = await session.execute(select(File).where(File.id == file_id))
    file = result.scalar_one_or_none()
    if not file:
        logger.error(f"File {file_id} not found")
        return

    file.status = FileStatus.PROCESSING
    await session.commit()

    try:
        storage = StorageService()
        data = storage.download(file.gcs_path)

        chunker = registry.get_chunker(file.content_type)
        chunk_groups = chunker.chunk_bytes(data, file.filename)

        # Get document text for enrichment
        document_text = data.decode("utf-8", errors="replace")

        # Enrich all chunks with LLM context
        chunk_groups = await enrich_chunks(document_text, chunk_groups)

        # Generate table aliases
        table_aliases = await generate_table_aliases(chunk_groups)

        chunk_id_map = {}
        chunk_index = 0
        for group in chunk_groups:
            parent_record = ParentChunk(
                file_id=file.id,
                content=group.parent.content,
                token_count=group.parent.token_count,
            )
            session.add(parent_record)
            await session.flush()

            for child in group.children:
                chunk_record = Chunk(
                    file_id=file.id,
                    parent_chunk_id=parent_record.id,
                    chunk_index=chunk_index,
                    content=child.content,
                    context_prefix=child.context_prefix,
                    token_count=child.token_count,
                    content_type=child.content_type,
                )
                session.add(chunk_record)
                await session.flush()
                chunk_id_map[id(child)] = chunk_record.id
                chunk_index += 1

        for alias_data in table_aliases:
            chunk_db_id = chunk_id_map.get(id(alias_data["chunk"]))
            if chunk_db_id:
                alias_record = ChunkAlias(
                    chunk_id=chunk_db_id,
                    file_id=file.id,
                    content=alias_data["question"],
                    token_count=count_tokens(alias_data["question"]),
                )
                session.add(alias_record)

        if chunk_index == 0:
            logger.warning(f"File {file_id} produced 0 chunks — marking as failed")
            file.status = FileStatus.FAILED
            await session.commit()
            return

        file.status = FileStatus.READY
        await embed_file_chunks(file.id, session)
        await embed_file_aliases(file.id, session)
        await session.commit()
        logger.info(f"File {file_id} processed: {chunk_index} chunks created")

    except Exception as e:
        logger.exception(f"Failed to process file {file_id}: {e}")
        await session.rollback()
        file.status = FileStatus.FAILED
        await session.commit()
