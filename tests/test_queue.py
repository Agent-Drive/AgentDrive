import asyncio
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from agentdrive.models.file import File as FileModel
from agentdrive.models.tenant import Tenant
from agentdrive.models.types import FileStatus
from agentdrive.services.queue import (
    _queue,
    _workers,
    enqueue,
    start_workers,
    stop_workers,
)
from agentdrive.config import settings as real_settings


@pytest.fixture(autouse=True)
def reset_queue():
    """Clear queue and worker state between tests to prevent leaks."""
    while not _queue.empty():
        try:
            _queue.get_nowait()
        except asyncio.QueueEmpty:
            break
    _workers.clear()
    yield
    while not _queue.empty():
        try:
            _queue.get_nowait()
        except asyncio.QueueEmpty:
            break
    _workers.clear()


@pytest.mark.asyncio
async def test_worker_processes_enqueued_file(db_session_factory, db_session):
    """Worker should call process_file for a PENDING file."""
    tenant = Tenant(name="Queue Test Tenant")
    db_session.add(tenant)
    await db_session.flush()

    file = FileModel(
        tenant_id=tenant.id,
        filename="test.txt",
        content_type="text",
        gcs_path="fake/path",
        file_size=100,
        status=FileStatus.PENDING,
    )
    db_session.add(file)
    await db_session.commit()

    mock_process = AsyncMock()

    with patch("agentdrive.services.queue.process_file", mock_process), \
         patch("agentdrive.services.queue.async_session_factory", db_session_factory):
        start_workers(n=1)
        enqueue(file.id)
        await asyncio.sleep(0.2)
        await stop_workers()

    mock_process.assert_called_once()
    call_args = mock_process.call_args
    assert call_args[0][0] == file.id


@pytest.mark.asyncio
async def test_worker_skips_non_pending_file(db_session_factory, db_session):
    """Worker should skip files that are not in PENDING status."""
    tenant = Tenant(name="Skip Test Tenant")
    db_session.add(tenant)
    await db_session.flush()

    file = FileModel(
        tenant_id=tenant.id,
        filename="already_done.txt",
        content_type="text",
        gcs_path="fake/path",
        file_size=100,
        status=FileStatus.READY,
    )
    db_session.add(file)
    await db_session.commit()

    mock_process = AsyncMock()

    with patch("agentdrive.services.queue.process_file", mock_process), \
         patch("agentdrive.services.queue.async_session_factory", db_session_factory):
        start_workers(n=1)
        enqueue(file.id)
        await asyncio.sleep(0.2)
        await stop_workers()

    mock_process.assert_not_called()


@pytest.mark.asyncio
async def test_worker_times_out_and_marks_failed(db_session_factory, db_session):
    """Worker should mark file as FAILED when process_file exceeds timeout."""
    tenant = Tenant(name="Timeout Test Tenant")
    db_session.add(tenant)
    await db_session.flush()

    file = FileModel(
        tenant_id=tenant.id,
        filename="slow.pdf",
        content_type="pdf",
        gcs_path="fake/path",
        file_size=100,
        status=FileStatus.PENDING,
    )
    db_session.add(file)
    await db_session.commit()
    file_id = file.id

    async def slow_process(*args, **kwargs):
        await asyncio.sleep(10)

    with patch("agentdrive.services.queue.process_file", side_effect=slow_process), \
         patch("agentdrive.services.queue.async_session_factory", db_session_factory), \
         patch.object(real_settings, "ingestion_timeout_seconds", 0.3):
        start_workers(n=1)
        enqueue(file_id)
        await asyncio.sleep(1)
        await stop_workers()

    async with db_session_factory() as check_session:
        result = await check_session.get(FileModel, file_id)
        assert result.status == FileStatus.FAILED
        assert "timed out" in (result.extra_metadata or {}).get("error", "")


@pytest.mark.asyncio
async def test_worker_handles_unexpected_exception(db_session_factory, db_session):
    """Worker should mark file as FAILED on unexpected exceptions."""
    tenant = Tenant(name="Error Test Tenant")
    db_session.add(tenant)
    await db_session.flush()

    file = FileModel(
        tenant_id=tenant.id,
        filename="bad.txt",
        content_type="text",
        gcs_path="fake/path",
        file_size=100,
        status=FileStatus.PENDING,
    )
    db_session.add(file)
    await db_session.commit()
    file_id = file.id

    async def failing_process(*args, **kwargs):
        raise RuntimeError("Something broke")

    with patch("agentdrive.services.queue.process_file", side_effect=failing_process), \
         patch("agentdrive.services.queue.async_session_factory", db_session_factory):
        start_workers(n=1)
        enqueue(file_id)
        await asyncio.sleep(0.5)
        await stop_workers()

    async with db_session_factory() as check_session:
        result = await check_session.get(FileModel, file_id)
        assert result.status == FileStatus.FAILED
        assert "Unexpected" in (result.extra_metadata or {}).get("error", "")
