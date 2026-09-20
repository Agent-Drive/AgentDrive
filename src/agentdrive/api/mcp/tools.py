import json
import uuid

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from agentdrive.api.files.schemas import FileDetailResponse, FileListResponse, FileUploadResponse
from agentdrive.core import files as core_files
from agentdrive.core import search as core_search
from agentdrive.core.data.models.tenant import Tenant


def _dump(payload) -> str:
    if hasattr(payload, "model_dump"):
        return json.dumps(payload.model_dump(mode="json"), indent=2)
    return json.dumps(payload, indent=2, default=str)


def _parse_file_id(file_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(file_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid file_id") from exc


async def search(session: AsyncSession, tenant: Tenant, query: str, top_k: int = 5) -> str:
    result = await core_search.search(session, tenant.id, query, top_k=top_k)
    return _dump(result)


async def list_files(session: AsyncSession, tenant: Tenant) -> str:
    files = await core_files.list_files(session, tenant)
    return _dump(FileListResponse(
        files=[FileDetailResponse.model_validate(f) for f in files],
        total=len(files),
    ))


async def get_file_status(session: AsyncSession, tenant: Tenant, file_id: str) -> str:
    file_record = await core_files.get_file(session, tenant, _parse_file_id(file_id))
    return _dump(FileDetailResponse.model_validate(file_record))


async def delete_file(session: AsyncSession, tenant: Tenant, file_id: str) -> str:
    await core_files.delete_file(session, tenant, _parse_file_id(file_id))
    return "File deleted successfully."


async def start_upload(
    session: AsyncSession,
    tenant: Tenant,
    filename: str,
    file_size: int,
    mime_type: str = "application/octet-stream",
) -> str:
    slot = await core_files.create_upload_url(
        session, tenant, filename, file_size, mime_type,
    )
    return json.dumps(
        {
            "file_id": str(slot.file.id),
            "upload_url": slot.upload_url,
            "expires_at": slot.expires_at.isoformat(),
            "instructions": (
                "PUT the file bytes to upload_url with the same Content-Type as mime_type, "
                "then call complete_upload with file_id."
            ),
        },
        indent=2,
    )


async def complete_upload(session: AsyncSession, tenant: Tenant, file_id: str) -> str:
    file_record = await core_files.complete_upload(session, tenant, _parse_file_id(file_id))
    return _dump(FileUploadResponse.model_validate(file_record))


async def download_file(session: AsyncSession, tenant: Tenant, file_id: str) -> str:
    slot = await core_files.get_download_url(session, tenant, _parse_file_id(file_id))
    return json.dumps(slot.as_dict(), indent=2)
