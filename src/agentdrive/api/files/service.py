import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from urllib.parse import quote
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentdrive.config import settings
from agentdrive.engine.data.models.file import File as FileModel
from agentdrive.engine.data.models.tenant import Tenant
from agentdrive.engine.data.models.types import FileStatus
from agentdrive.api.files.schemas import (
    FileDetailResponse,
    FileListResponse,
    FileUploadResponse,
    UploadUrlRequest,
    UploadUrlResponse,
)
from agentdrive.engine.pipeline.file_type import detect_content_type
from agentdrive.engine.pipeline.queue import enqueue
from agentdrive.engine.pipeline.storage import StorageService


async def upload_file(session: AsyncSession, tenant: Tenant, file: UploadFile) -> FileUploadResponse:
    data = await file.read()
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="File exceeds 32MB limit")
    content_type = detect_content_type(file.filename or "unknown", file.content_type)
    file_id = uuid.uuid4()
    storage = StorageService()
    gcs_path = storage.upload(tenant.id, file_id, file.filename or "unknown", data, file.content_type or "")
    file_record = FileModel(
        id=file_id, tenant_id=tenant.id,
        filename=file.filename or "unknown", content_type=content_type,
        gcs_path=gcs_path, file_size=len(data), status="pending",
    )
    session.add(file_record)
    await session.commit()
    await session.refresh(file_record)

    enqueue(file_record.id)
    return FileUploadResponse.model_validate(file_record)


async def create_upload_url(
    session: AsyncSession, tenant: Tenant, body: UploadUrlRequest
) -> UploadUrlResponse:
    if body.file_size > settings.max_signed_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds {settings.max_signed_upload_bytes} byte limit",
        )
    file_id = uuid.uuid4()
    storage = StorageService()
    gcs_path = storage.generate_path(tenant.id, file_id, body.filename)
    upload_url = storage.generate_signed_upload_url(
        tenant.id, file_id, body.filename,
        content_type=body.content_type,
        expiry_hours=settings.signed_url_expiry_hours,
    )
    file_record = FileModel(
        id=file_id, tenant_id=tenant.id,
        filename=body.filename, content_type=body.content_type,
        gcs_path=gcs_path, file_size=body.file_size,
        status=FileStatus.UPLOADING,
    )
    session.add(file_record)
    await session.commit()
    await session.refresh(file_record)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.signed_url_expiry_hours)
    return UploadUrlResponse(
        file_id=file_record.id,
        upload_url=upload_url,
        expires_at=expires_at,
    )


async def complete_upload(
    session: AsyncSession, tenant: Tenant, file_id: uuid.UUID
) -> FileUploadResponse:
    result = await session.execute(
        select(FileModel).where(
            FileModel.id == file_id,
            FileModel.tenant_id == tenant.id,
            FileModel.status == FileStatus.UPLOADING,
        )
    )
    file_record = result.scalar_one_or_none()
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found or not in uploading state")
    storage = StorageService()
    if not storage.blob_exists(file_record.gcs_path):
        raise HTTPException(status_code=400, detail="Upload not found in storage")
    actual_size = storage.get_blob_size(file_record.gcs_path)
    file_record.file_size = actual_size
    file_record.status = FileStatus.PENDING
    await session.commit()
    await session.refresh(file_record)
    enqueue(file_record.id)
    return FileUploadResponse.model_validate(file_record)


async def get_file(session: AsyncSession, tenant: Tenant, file_id: uuid.UUID) -> FileDetailResponse:
    result = await session.execute(
        select(FileModel)
        .where(FileModel.id == file_id, FileModel.tenant_id == tenant.id)
    )
    file_record = result.scalar_one_or_none()
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")
    return FileDetailResponse.model_validate(file_record)


async def download_file(session: AsyncSession, tenant: Tenant, file_id: uuid.UUID) -> StreamingResponse:
    result = await session.execute(
        select(FileModel).where(FileModel.id == file_id, FileModel.tenant_id == tenant.id)
    )
    file_record = result.scalar_one_or_none()
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")

    storage = StorageService()
    try:
        stream = storage.download_stream(file_record.gcs_path)
    except FileNotFoundError:
        raise HTTPException(status_code=502, detail="File blob not found in storage")

    safe_filename = file_record.filename.replace('"', '_')
    headers = {
        "Content-Disposition": f"attachment; filename=\"{safe_filename}\"; filename*=UTF-8''{quote(file_record.filename)}",
    }
    if file_record.file_size:
        headers["Content-Length"] = str(file_record.file_size)

    return StreamingResponse(
        stream,
        media_type=file_record.content_type,
        headers=headers,
    )


async def list_files(session: AsyncSession, tenant: Tenant) -> FileListResponse:
    query = select(FileModel).where(FileModel.tenant_id == tenant.id)
    query = query.order_by(FileModel.created_at.desc())
    result = await session.execute(query)
    files = result.scalars().all()
    responses = [FileDetailResponse.model_validate(f) for f in files]
    return FileListResponse(
        files=responses,
        total=len(files),
    )


async def delete_file(session: AsyncSession, tenant: Tenant, file_id: uuid.UUID) -> None:
    result = await session.execute(
        select(FileModel).where(FileModel.id == file_id, FileModel.tenant_id == tenant.id)
    )
    file_record = result.scalar_one_or_none()
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")
    storage = StorageService()
    storage.delete(file_record.gcs_path)
    await session.delete(file_record)
    await session.commit()
