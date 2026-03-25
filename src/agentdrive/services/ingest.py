import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentdrive.chunking.base import ChunkResult, ParentChildChunks
from agentdrive.chunking.registry import ChunkerRegistry
from agentdrive.chunking.tokens import count_tokens
from agentdrive.config import settings
from agentdrive.embedding.pipeline import embed_file_aliases, embed_file_chunks
from agentdrive.enrichment.contextual import (
    enrich_chunks_with_summaries,
    generate_document_summary,
)
from agentdrive.enrichment.table_questions import generate_table_aliases
from agentdrive.models.chunk import Chunk, ParentChunk
from agentdrive.models.chunk_alias import ChunkAlias
from agentdrive.models.file import File
from agentdrive.models.file_batch import FileBatch
from agentdrive.models.file_summary import FileSummary
from agentdrive.models.types import BatchStatus, FileStatus
from agentdrive.services.storage import StorageService

logger = logging.getLogger(__name__)
registry = ChunkerRegistry()


async def process_file(file_id: uuid.UUID, session: AsyncSession) -> None:
    """Orchestrate file ingestion with four phases and resume support."""
    result = await session.execute(select(File).where(File.id == file_id))
    file = result.scalar_one_or_none()
    if not file:
        logger.error(f"File {file_id} not found")
        return

    file.status = FileStatus.PROCESSING
    await session.commit()

    try:
        # --- Resume logic ---
        batch = await _get_batch(file_id, session)
        summary = await _get_summary(file_id, session)

        # Phase 1: Chunking
        if batch is None or batch.chunking_status != BatchStatus.COMPLETED:
            file.current_phase = "chunking"
            await session.commit()
            batch = await _phase1_chunking(file, session)
            if batch is None:
                # 0 chunks — file already marked FAILED inside _phase1_chunking
                return

        # Phase 2: Summarization
        if summary is None:
            file.current_phase = "summarization"
            await session.commit()
            summary = await _phase2_summarization(file, session)

        # Phase 3: Enrichment
        if batch.enrichment_status != BatchStatus.COMPLETED:
            file.current_phase = "enrichment"
            await session.commit()
            await _phase3_enrichment(file, summary, batch, session)

        # Phase 4: Embedding
        if batch.embedding_status != BatchStatus.COMPLETED:
            file.current_phase = "embedding"
            await session.commit()
            await _phase4_embedding(file, batch, session)

        # All phases complete
        file.status = FileStatus.READY
        file.current_phase = None
        file.total_batches = 1
        file.completed_batches = 1
        await session.commit()
        logger.info(f"File {file_id} processed successfully")

    except Exception as e:
        logger.exception(f"Failed to process file {file_id}: {e}")
        await session.rollback()
        # Re-fetch after rollback
        result = await session.execute(select(File).where(File.id == file_id))
        file = result.scalar_one_or_none()
        if file:
            file.status = FileStatus.FAILED
            file.retry_count = (file.retry_count or 0) + 1
            await session.commit()


async def _get_batch(file_id: uuid.UUID, session: AsyncSession) -> FileBatch | None:
    """Get the single FileBatch for a file, if it exists."""
    result = await session.execute(
        select(FileBatch).where(FileBatch.file_id == file_id)
    )
    return result.scalar_one_or_none()


async def _get_summary(file_id: uuid.UUID, session: AsyncSession) -> FileSummary | None:
    """Get the FileSummary for a file, if it exists."""
    result = await session.execute(
        select(FileSummary).where(FileSummary.file_id == file_id)
    )
    return result.scalar_one_or_none()


async def _phase1_chunking(file: File, session: AsyncSession) -> FileBatch | None:
    """Download file, chunk it, persist batch + chunks. Returns None if 0 chunks."""
    storage = StorageService()
    tmp_path = None
    try:
        tmp_path = storage.download_to_tempfile(file.gcs_path)
        chunk_groups = registry.chunk_file(file.content_type, tmp_path, file.filename)

        if not chunk_groups or sum(len(g.children) for g in chunk_groups) == 0:
            logger.warning(f"File {file.id} produced 0 chunks — marking as failed")
            file.status = FileStatus.FAILED
            await session.commit()
            return None

        # Create the batch
        batch = FileBatch(
            file_id=file.id,
            batch_index=0,
            chunking_status=BatchStatus.PENDING,
            enrichment_status=BatchStatus.PENDING,
            embedding_status=BatchStatus.PENDING,
            chunk_count=0,
        )
        session.add(batch)
        await session.flush()

        # Persist parent chunks and child chunks
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

        batch.chunk_count = chunk_index
        batch.chunking_status = BatchStatus.COMPLETED
        file.total_batches = 1
        await session.commit()

        logger.info(f"Phase 1 complete for file {file.id}: {chunk_index} chunks")
        return batch

    finally:
        if tmp_path is not None:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass


async def _phase2_summarization(file: File, session: AsyncSession) -> FileSummary:
    """Read all parent chunks, generate document summary, persist FileSummary."""
    result = await session.execute(
        select(ParentChunk)
        .where(ParentChunk.file_id == file.id)
        .order_by(ParentChunk.created_at)
    )
    parents = result.scalars().all()
    document_text = "\n\n".join(p.content for p in parents)

    summary_data = await generate_document_summary(document_text)

    summary = FileSummary(
        file_id=file.id,
        document_summary=summary_data.get("document_summary", ""),
        section_summaries=summary_data.get("section_summaries", []),
    )
    session.add(summary)
    await session.commit()

    logger.info(f"Phase 2 complete for file {file.id}: summary generated")
    return summary


async def _phase3_enrichment(
    file: File, summary: FileSummary, batch: FileBatch, session: AsyncSession
) -> None:
    """Load chunks as ParentChildChunks, enrich, write back context_prefix, generate aliases."""
    chunk_groups = await _load_chunk_groups(file.id, session)

    # Enrich with two-pass summaries
    enriched_groups = await enrich_chunks_with_summaries(
        chunk_groups,
        doc_summary=summary.document_summary,
        section_summaries=summary.section_summaries,
    )

    # Write enriched context_prefix back to DB chunks
    result = await session.execute(
        select(Chunk)
        .where(Chunk.file_id == file.id)
        .order_by(Chunk.chunk_index)
    )
    db_chunks = result.scalars().all()

    # Flatten enriched children in order
    enriched_children = []
    for group in enriched_groups:
        for child in group.children:
            enriched_children.append(child)

    for db_chunk, enriched_child in zip(db_chunks, enriched_children):
        db_chunk.context_prefix = enriched_child.context_prefix

    # Generate table aliases
    table_aliases = await generate_table_aliases(enriched_groups)
    for alias_data in table_aliases:
        alias_record = ChunkAlias(
            chunk_id=alias_data["chunk_id"] if "chunk_id" in alias_data else None,
            file_id=file.id,
            content=alias_data["question"],
            token_count=count_tokens(alias_data["question"]),
        )
        session.add(alias_record)

    batch.enrichment_status = BatchStatus.COMPLETED
    await session.commit()

    logger.info(f"Phase 3 complete for file {file.id}: enrichment done")


async def _phase4_embedding(
    file: File, batch: FileBatch, session: AsyncSession
) -> None:
    """Embed chunks and aliases."""
    await embed_file_chunks(file.id, session)
    await embed_file_aliases(file.id, session)

    batch.embedding_status = BatchStatus.COMPLETED
    await session.commit()

    logger.info(f"Phase 4 complete for file {file.id}: embeddings done")


async def _load_chunk_groups(
    file_id: uuid.UUID, session: AsyncSession
) -> list[ParentChildChunks]:
    """Reconstruct ParentChildChunks from persisted DB records."""
    result = await session.execute(
        select(ParentChunk)
        .where(ParentChunk.file_id == file_id)
        .order_by(ParentChunk.created_at)
    )
    parents = result.scalars().all()

    groups = []
    for parent_record in parents:
        child_result = await session.execute(
            select(Chunk)
            .where(Chunk.parent_chunk_id == parent_record.id)
            .order_by(Chunk.chunk_index)
        )
        child_records = child_result.scalars().all()

        parent_chunk = ChunkResult(
            content=parent_record.content,
            context_prefix="",
            token_count=parent_record.token_count,
            content_type="text",
        )
        children = [
            ChunkResult(
                content=c.content,
                context_prefix=c.context_prefix,
                token_count=c.token_count,
                content_type=c.content_type,
            )
            for c in child_records
        ]
        groups.append(ParentChildChunks(parent=parent_chunk, children=children))

    return groups
