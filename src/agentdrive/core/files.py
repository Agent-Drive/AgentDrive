import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentdrive.config import settings
from agentdrive.core.data.models.file import File as FileModel
from agentdrive.core.data.models.tenant import Tenant
from agentdrive.core.data.models.types import FileStatus
from agentdrive.core.errors import (
    FileNotFound,
    FileTooLarge,
    StoredBlobMissing,
    UploadBlobMissing,
    UploadNotReady,
)
from agentdrive.core.pipeline.file_type import detect_content_type
from agentdrive.core.pipeline.queue import enqueue
from agentdrive.core.pipeline.storage import StorageService


@dataclass
class UploadSlot:
    file: FileModel
    upload_url: str
    expires_at: datetime


@dataclass
class DownloadSlot:
    file_id: uuid.UUID
    filename: str
    download_url: str
    expires_in_hours: int

    def as_dict(self) -> dict:
        return {
            "file_id": str(self.file_id),
            "filename": self.filename,
            "download_url": self.download_url,
            "expires_in_hours": self.expires_in_hours,
        }


@dataclass
class FileDownload:
    stream: Any
    filename: str
    content_type: str
    file_size: int | None


async def create_upload_url(
    session: AsyncSession,
    tenant: Tenant,
    filename: str,
    file_size: int,
    content_type: str = "application/octet-stream",
) -> UploadSlot:
    if file_size > settings.max_signed_upload_bytes:
        raise FileTooLarge(
            f"File exceeds {settings.max_signed_upload_bytes} byte limit"
        )
    file_id = uuid.uuid4()
    storage = StorageService()
    gcs_path = storage.generate_path(tenant.id, file_id, filename)
    upload_url = storage.generate_signed_upload_url(
        tenant.id, file_id, filename,
        content_type=content_type,
        expiry_hours=settings.signed_url_expiry_hours,
    )
    file_record = FileModel(
        id=file_id, tenant_id=tenant.id,
        filename=filename,
        content_type=detect_content_type(filename, content_type),
        gcs_path=gcs_path, file_size=file_size,
        status=FileStatus.UPLOADING,
    )
    session.add(file_record)
    await session.commit()
    await session.refresh(file_record)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.signed_url_expiry_hours)
    return UploadSlot(file=file_record, upload_url=upload_url, expires_at=expires_at)


async def complete_upload(
    session: AsyncSession, tenant: Tenant, file_id: uuid.UUID
) -> FileModel:
    result = await session.execute(
        select(FileModel).where(
            FileModel.id == file_id,
            FileModel.tenant_id == tenant.id,
            FileModel.status == FileStatus.UPLOADING,
        )
    )
    file_record = result.scalar_one_or_none()
    if not file_record:
        raise UploadNotReady()
    storage = StorageService()
    if not storage.blob_exists(file_record.gcs_path):
        raise UploadBlobMissing()
    actual_size = storage.get_blob_size(file_record.gcs_path)
    file_record.file_size = actual_size
    file_record.status = FileStatus.PENDING
    await session.commit()
    await session.refresh(file_record)
    enqueue(file_record.id)
    return file_record


async def get_file(session: AsyncSession, tenant: Tenant, file_id: uuid.UUID) -> FileModel:
    result = await session.execute(
        select(FileModel).where(FileModel.id == file_id, FileModel.tenant_id == tenant.id)
    )
    file_record = result.scalar_one_or_none()
    if not file_record:
        raise FileNotFound()
    return file_record


async def get_download_url(
    session: AsyncSession, tenant: Tenant, file_id: uuid.UUID
) -> DownloadSlot:
    file_record = await get_file(session, tenant, file_id)
    storage = StorageService()
    if not storage.blob_exists(file_record.gcs_path):
        raise StoredBlobMissing()
    download_url = storage.generate_signed_download_url(
        file_record.gcs_path,
        file_record.filename,
        expiry_hours=settings.signed_url_expiry_hours,
    )
    return DownloadSlot(
        file_id=file_record.id,
        filename=file_record.filename,
        download_url=download_url,
        expires_in_hours=settings.signed_url_expiry_hours,
    )


async def open_download(
    session: AsyncSession, tenant: Tenant, file_id: uuid.UUID
) -> FileDownload:
    file_record = await get_file(session, tenant, file_id)
    storage = StorageService()
    try:
        stream = storage.download_stream(file_record.gcs_path)
    except FileNotFoundError:
        raise StoredBlobMissing()
    return FileDownload(
        stream=stream,
        filename=file_record.filename,
        content_type=file_record.content_type,
        file_size=file_record.file_size,
    )


async def list_files(session: AsyncSession, tenant: Tenant) -> list[FileModel]:
    query = select(FileModel).where(FileModel.tenant_id == tenant.id)
    query = query.order_by(FileModel.created_at.desc())
    result = await session.execute(query)
    return list(result.scalars().all())


async def delete_file(session: AsyncSession, tenant: Tenant, file_id: uuid.UUID) -> None:
    file_record = await get_file(session, tenant, file_id)
    storage = StorageService()
    storage.delete(file_record.gcs_path)
    await session.delete(file_record)
    await session.commit()
