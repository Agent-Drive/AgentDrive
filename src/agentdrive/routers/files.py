import uuid
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from urllib.parse import quote
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from agentdrive.config import settings
from agentdrive.db.session import get_session
from agentdrive.dependencies import get_current_tenant
from agentdrive.models.file import File as FileModel
from agentdrive.models.tenant import Tenant
from agentdrive.models.types import FileStatus
from agentdrive.schemas.files import (
    FileDetailResponse, FileListResponse, FileUploadResponse,
    UploadUrlRequest, UploadUrlResponse,
)
from agentdrive.services.file_type import detect_content_type
from agentdrive.services.queue import enqueue
from agentdrive.services.storage import StorageService

router = APIRouter(prefix="/v1/files", tags=["files"])


@router.post("", status_code=202, response_model=FileUploadResponse)
async def upload_file(
    file: UploadFile = File(...),
    collection: uuid.UUID | None = Form(None),
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
):
    data = await file.read()
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="File exceeds 32MB limit")
    content_type = detect_content_type(file.filename or "unknown", file.content_type)
    file_id = uuid.uuid4()
    storage = StorageService()
    gcs_path = storage.upload(tenant.id, file_id, file.filename or "unknown", data, file.content_type or "")
    file_record = FileModel(
        id=file_id, tenant_id=tenant.id, collection_id=collection,
        filename=file.filename or "unknown", content_type=content_type,
        gcs_path=gcs_path, file_size=len(data), status="pending",
    )
    session.add(file_record)
    await session.commit()
    await session.refresh(file_record)

    enqueue(file_record.id)
    return FileUploadResponse.model_validate(file_record)


@router.post("/upload-url", status_code=201, response_model=UploadUrlResponse)
async def create_upload_url(
    body: UploadUrlRequest,
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
):
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
        id=file_id, tenant_id=tenant.id, collection_id=body.collection_id,
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


@router.post("/{file_id}/complete", status_code=200, response_model=FileUploadResponse)
async def complete_upload(
    file_id: uuid.UUID,
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
):
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


@router.get("/{file_id}", response_model=FileDetailResponse)
async def get_file(
    file_id: uuid.UUID,
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(FileModel)
        .options(selectinload(FileModel.collection))
        .where(FileModel.id == file_id, FileModel.tenant_id == tenant.id)
    )
    file_record = result.scalar_one_or_none()
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")
    response = FileDetailResponse.model_validate(file_record)
    response.collection_name = file_record.collection.name if file_record.collection else None
    return response


@router.get("/{file_id}/download")
async def download_file(
    file_id: uuid.UUID,
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
):
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


@router.get("", response_model=FileListResponse)
async def list_files(
    collection: uuid.UUID | None = None,
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
):
    query = select(FileModel).options(selectinload(FileModel.collection)).where(FileModel.tenant_id == tenant.id)
    if collection:
        query = query.where(FileModel.collection_id == collection)
    query = query.order_by(FileModel.created_at.desc())
    result = await session.execute(query)
    files = result.scalars().all()
    responses = []
    for f in files:
        resp = FileDetailResponse.model_validate(f)
        resp.collection_name = f.collection.name if f.collection else None
        responses.append(resp)
    return FileListResponse(
        files=responses,
        total=len(files),
    )


@router.delete("/{file_id}", status_code=204)
async def delete_file(
    file_id: uuid.UUID,
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
):
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
