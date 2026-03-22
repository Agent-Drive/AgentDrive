import logging
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from agentdrive.chunking.registry import ChunkerRegistry
from agentdrive.models.chunk import Chunk, ParentChunk
from agentdrive.models.file import File
from agentdrive.models.types import FileStatus
from agentdrive.services.storage import StorageService

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
                chunk_index += 1

        file.status = FileStatus.READY
        await session.commit()
        logger.info(f"File {file_id} processed: {chunk_index} chunks created")

    except Exception as e:
        logger.exception(f"Failed to process file {file_id}: {e}")
        await session.rollback()
        file.status = FileStatus.FAILED
        await session.commit()
