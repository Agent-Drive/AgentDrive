import asyncio
import logging
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentdrive.chunking.base import ChunkResult, ParentChildChunks
from agentdrive.chunking.registry import ChunkerRegistry
from agentdrive.chunking.tokens import count_tokens
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

MAX_SINGLE_PASS_TOKENS = 200_000
GROUP_BATCH_TOKENS = 50_000


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
        batches = await _get_batches(file_id, session)
        summary = await _get_summary(file_id, session)

        all_chunked = batches and all(
            b.chunking_status == BatchStatus.COMPLETED for b in batches
        )
        all_enriched = batches and all(
            b.enrichment_status == BatchStatus.COMPLETED for b in batches
        )
        all_embedded = batches and all(
            b.embedding_status == BatchStatus.COMPLETED for b in batches
        )

        # Phase 1: Chunking
        if not all_chunked:
            file.current_phase = "chunking"
            await session.commit()
            batches = await _phase1_chunking(file, session)
            if not batches:
                # 0 chunks — file already marked FAILED inside _phase1_chunking
                return

        # Phase 2: Summarization
        if summary is None:
            file.current_phase = "summarization"
            await session.commit()
            summary = await _phase2_summarization(file, session)

        # Phase 3: Enrichment
        if not all_enriched:
            file.current_phase = "enrichment"
            await session.commit()
            await _phase3_enrichment(file, summary, session)

        # Phase 4: Embedding
        if not all_embedded:
            file.current_phase = "embedding"
            await session.commit()
            await _phase4_embedding(file, session)

        # All phases complete
        file.status = FileStatus.READY
        file.current_phase = None
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


async def _get_batches(
    file_id: uuid.UUID, session: AsyncSession
) -> list[FileBatch]:
    """Get all FileBatches for a file, ordered by batch_index."""
    result = await session.execute(
        select(FileBatch)
        .where(FileBatch.file_id == file_id)
        .order_by(FileBatch.batch_index)
    )
    return list(result.scalars().all())


async def _get_summary(
    file_id: uuid.UUID, session: AsyncSession
) -> FileSummary | None:
    """Get the FileSummary for a file, if it exists."""
    result = await session.execute(
        select(FileSummary).where(FileSummary.file_id == file_id)
    )
    return result.scalar_one_or_none()


def _download_and_chunk(
    gcs_path: str, content_type: str, filename: str, file_id: str
) -> tuple[list[ParentChildChunks], Path]:
    """Sync I/O: download from GCS and chunk. Runs in a thread pool."""
    storage = StorageService()
    tmp_path = storage.download_to_tempfile(gcs_path)
    try:
        chunk_groups = registry.chunk_file(
            content_type,
            tmp_path,
            filename,
            gcs_path=gcs_path,
            file_id=file_id,
        )
        return chunk_groups, tmp_path
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


async def _phase1_chunking(
    file: File, session: AsyncSession
) -> list[FileBatch]:
    """Download file, chunk it, persist batches + chunks. Returns empty list if 0 chunks."""
    tmp_path = None
    try:
        chunk_groups, tmp_path = await asyncio.to_thread(
            _download_and_chunk,
            file.gcs_path, file.content_type, file.filename, str(file.id),
        )

        if not chunk_groups or sum(len(g.children) for g in chunk_groups) == 0:
            logger.warning(
                f"File {file.id} produced 0 chunks — marking as failed"
            )
            file.status = FileStatus.FAILED
            await session.commit()
            return []

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
                batch_id=batch.id,
                content=group.parent.content,
                token_count=group.parent.token_count,
            )
            session.add(parent_record)
            await session.flush()

            for child in group.children:
                chunk_record = Chunk(
                    file_id=file.id,
                    parent_chunk_id=parent_record.id,
                    batch_id=batch.id,
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

        logger.info(
            f"Phase 1 complete for file {file.id}: {chunk_index} chunks"
        )
        return [batch]

    finally:
        if tmp_path is not None:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass


def _batch_parents(parents: list) -> list[list]:
    """Group parent chunks into batches of ~GROUP_BATCH_TOKENS tokens each."""
    if not parents:
        return []
    batches: list[list] = []
    current_batch: list = []
    current_tokens = 0

    for parent in parents:
        token_count = parent.token_count
        if current_batch and current_tokens + token_count > GROUP_BATCH_TOKENS:
            batches.append(current_batch)
            current_batch = []
            current_tokens = 0
        current_batch.append(parent)
        current_tokens += token_count

    if current_batch:
        batches.append(current_batch)
    return batches


async def _phase2_summarization(
    file: File, session: AsyncSession
) -> FileSummary:
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
    file: File, summary: FileSummary, session: AsyncSession
) -> None:
    """Load chunks per-batch, enrich, write back context_prefix, generate aliases."""
    batches = await _get_batches(file.id, session)
    for batch in batches:
        if batch.enrichment_status == BatchStatus.COMPLETED:
            continue

        batch.enrichment_status = BatchStatus.PROCESSING
        await session.commit()

        chunk_groups = await _load_chunk_groups(
            file.id, session, batch_id=batch.id
        )

        # Enrich with two-pass summaries
        enriched_groups = await enrich_chunks_with_summaries(
            chunk_groups,
            doc_summary=summary.document_summary,
            section_summaries=summary.section_summaries,
        )

        # Write enriched context_prefix back to DB chunks
        db_chunks = list(
            (
                await session.execute(
                    select(Chunk)
                    .where(Chunk.batch_id == batch.id)
                    .order_by(Chunk.chunk_index)
                )
            )
            .scalars()
            .all()
        )

        # Flatten enriched children in order
        enriched_children = []
        for group in enriched_groups:
            for child in group.children:
                enriched_children.append(child)

        # Build ChunkResult → db chunk_id mapping (positional)
        chunk_id_map: dict[int, uuid.UUID] = {}
        for db_chunk, enriched_child in zip(db_chunks, enriched_children):
            db_chunk.context_prefix = enriched_child.context_prefix
            chunk_id_map[id(enriched_child)] = db_chunk.id

        # Generate table aliases
        table_aliases = await generate_table_aliases(enriched_groups)
        for alias_data in table_aliases:
            alias_record = ChunkAlias(
                chunk_id=chunk_id_map[id(alias_data["chunk"])],
                file_id=file.id,
                content=alias_data["question"],
                token_count=count_tokens(alias_data["question"]),
            )
            session.add(alias_record)

        batch.enrichment_status = BatchStatus.COMPLETED
        await session.commit()

    logger.info(f"Phase 3 complete for file {file.id}: enrichment done")


async def _phase4_embedding(file: File, session: AsyncSession) -> None:
    """Embed chunks and aliases per-batch."""
    batches = await _get_batches(file.id, session)
    for batch in batches:
        if batch.embedding_status == BatchStatus.COMPLETED:
            continue

        batch.embedding_status = BatchStatus.PROCESSING
        await session.commit()

        await embed_file_chunks(file.id, session, batch_id=batch.id)
        await embed_file_aliases(file.id, session, batch_id=batch.id)

        batch.embedding_status = BatchStatus.COMPLETED
        await session.commit()

    file.completed_batches = sum(
        1 for b in batches if b.embedding_status == BatchStatus.COMPLETED
    )
    await session.commit()

    logger.info(f"Phase 4 complete for file {file.id}: embeddings done")


async def _load_chunk_groups(
    file_id: uuid.UUID,
    session: AsyncSession,
    batch_id: uuid.UUID | None = None,
) -> list[ParentChildChunks]:
    """Reconstruct ParentChildChunks from persisted DB records."""
    query = (
        select(ParentChunk)
        .where(ParentChunk.file_id == file_id)
        .order_by(ParentChunk.created_at)
    )
    if batch_id is not None:
        query = query.where(ParentChunk.batch_id == batch_id)

    result = await session.execute(query)
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
