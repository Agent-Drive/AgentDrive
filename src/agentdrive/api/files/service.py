import uuid
from urllib.parse import quote

from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from agentdrive.api.errors import raise_http
from agentdrive.api.files.schemas import (
    FileDetailResponse,
    FileListResponse,
    FileUploadResponse,
    UploadUrlRequest,
    UploadUrlResponse,
)
from agentdrive.core import files as core_files
from agentdrive.core.data.models.tenant import Tenant
from agentdrive.core.errors import CoreError


async def create_upload_url(
    session: AsyncSession, tenant: Tenant, body: UploadUrlRequest
) -> UploadUrlResponse:
    try:
        slot = await core_files.create_upload_url(
            session, tenant, body.filename, body.file_size, body.content_type,
        )
    except CoreError as exc:
        raise_http(exc)
    return UploadUrlResponse(
        file_id=slot.file.id,
        upload_url=slot.upload_url,
        expires_at=slot.expires_at,
    )


async def complete_upload(
    session: AsyncSession, tenant: Tenant, file_id: uuid.UUID
) -> FileUploadResponse:
    try:
        file_record = await core_files.complete_upload(session, tenant, file_id)
    except CoreError as exc:
        raise_http(exc)
    return FileUploadResponse.model_validate(file_record)


async def get_file(session: AsyncSession, tenant: Tenant, file_id: uuid.UUID) -> FileDetailResponse:
    try:
        file_record = await core_files.get_file(session, tenant, file_id)
    except CoreError as exc:
        raise_http(exc)
    return FileDetailResponse.model_validate(file_record)


async def get_download_url(session: AsyncSession, tenant: Tenant, file_id: uuid.UUID) -> dict:
    try:
        slot = await core_files.get_download_url(session, tenant, file_id)
    except CoreError as exc:
        raise_http(exc)
    return slot.as_dict()


async def download_file(session: AsyncSession, tenant: Tenant, file_id: uuid.UUID) -> StreamingResponse:
    try:
        download = await core_files.open_download(session, tenant, file_id)
    except CoreError as exc:
        raise_http(exc)
    safe_filename = download.filename.replace('"', '_')
    headers = {
        "Content-Disposition": (
            f'attachment; filename="{safe_filename}"; '
            f"filename*=UTF-8''{quote(download.filename)}"
        ),
    }
    if download.file_size:
        headers["Content-Length"] = str(download.file_size)
    return StreamingResponse(
        download.stream,
        media_type=download.content_type,
        headers=headers,
    )


async def list_files(session: AsyncSession, tenant: Tenant) -> FileListResponse:
    try:
        files = await core_files.list_files(session, tenant)
    except CoreError as exc:
        raise_http(exc)
    responses = [FileDetailResponse.model_validate(f) for f in files]
    return FileListResponse(files=responses, total=len(files))


async def delete_file(session: AsyncSession, tenant: Tenant, file_id: uuid.UUID) -> None:
    try:
        await core_files.delete_file(session, tenant, file_id)
    except CoreError as exc:
        raise_http(exc)
