import asyncio
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentdrive.config import settings
from agentdrive.db.session import async_session_factory
from agentdrive.models.file import File
from agentdrive.models.types import FileStatus
from agentdrive.services.ingest import process_file

logger = logging.getLogger(__name__)

_queue: asyncio.Queue[UUID] = asyncio.Queue()
_workers: list[asyncio.Task] = []


def enqueue(file_id: UUID) -> None:
    _queue.put_nowait(file_id)
    logger.info(f"Enqueued file {file_id} (queue depth: {_queue.qsize()})")


async def _worker(worker_id: int) -> None:
    logger.info(f"Ingestion worker {worker_id} started")
    while True:
        file_id = await _queue.get()
        try:
            async with async_session_factory() as session:
                file = await session.get(File, file_id)
                if not file or file.status != FileStatus.PENDING:
                    logger.info(
                        f"Skipping file {file_id} "
                        f"(status={file.status if file else 'not found'})"
                    )
                    continue

                try:
                    await asyncio.wait_for(
                        process_file(file_id, session),
                        timeout=settings.ingestion_timeout_seconds,
                    )
                except asyncio.TimeoutError:
                    await session.rollback()
                    file = await session.get(File, file_id)
                    if file:
                        file.status = FileStatus.FAILED
                        file.extra_metadata = {
                            **(file.extra_metadata or {}),
                            "error": f"Ingestion timed out after {settings.ingestion_timeout_seconds}s",
                        }
                        await session.commit()
                    logger.error(
                        f"File {file_id} timed out after {settings.ingestion_timeout_seconds}s"
                    )
                except Exception:
                    await session.rollback()
                    file = await session.get(File, file_id)
                    if file and file.status != FileStatus.FAILED:
                        file.status = FileStatus.FAILED
                        file.extra_metadata = {
                            **(file.extra_metadata or {}),
                            "error": "Unexpected ingestion error",
                        }
                        await session.commit()
                    logger.exception(f"Unexpected error processing file {file_id}")
        finally:
            _queue.task_done()


def start_workers(n: int = settings.ingestion_workers) -> None:
    for i in range(n):
        task = asyncio.create_task(_worker(i))
        _workers.append(task)
    logger.info(f"Started {n} ingestion workers")


async def stop_workers() -> None:
    for task in _workers:
        task.cancel()
    await asyncio.gather(*_workers, return_exceptions=True)
    _workers.clear()
    logger.info("All ingestion workers stopped")


async def reap_stuck_files(session: AsyncSession) -> list[UUID]:
    """Reset stuck PROCESSING files to PENDING and enqueue all PENDING files.

    Returns list of file IDs that were enqueued.
    """
    threshold = datetime.now(timezone.utc) - timedelta(minutes=settings.reaper_threshold_minutes)

    # Step 1: Reset stuck processing files
    result = await session.execute(
        select(File).where(
            File.status == FileStatus.PROCESSING,
            File.updated_at < threshold,
        )
    )
    stuck_files = result.scalars().all()
    for f in stuck_files:
        logger.warning(f"Reaper: resetting stuck file {f.id} ({f.filename}) to PENDING")
        f.status = FileStatus.PENDING
    if stuck_files:
        await session.commit()

    # Step 2: Enqueue all pending files
    result = await session.execute(
        select(File).where(File.status == FileStatus.PENDING)
    )
    pending_files = result.scalars().all()
    enqueued = []
    for f in pending_files:
        enqueue(f.id)
        enqueued.append(f.id)

    if enqueued:
        logger.info(f"Reaper: enqueued {len(enqueued)} pending files")

    return enqueued
