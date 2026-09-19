import json
import uuid

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from agentdrive.api.files import service as files_service
from agentdrive.api.files.schemas import UploadUrlRequest
from agentdrive.api.search import service as search_service
from agentdrive.api.search.schemas import SearchRequest
from agentdrive.engine.data.models.tenant import Tenant


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
    result = await search_service.search(session, tenant, SearchRequest(query=query, top_k=top_k))
    return _dump(result)


async def list_files(session: AsyncSession, tenant: Tenant) -> str:
    result = await files_service.list_files(session, tenant)
    return _dump(result)


async def get_file_status(session: AsyncSession, tenant: Tenant, file_id: str) -> str:
    result = await files_service.get_file(session, tenant, _parse_file_id(file_id))
    return _dump(result)


async def delete_file(session: AsyncSession, tenant: Tenant, file_id: str) -> str:
    await files_service.delete_file(session, tenant, _parse_file_id(file_id))
    return "File deleted successfully."


async def start_upload(
    session: AsyncSession,
    tenant: Tenant,
    filename: str,
    file_size: int,
    mime_type: str = "application/octet-stream",
) -> str:
    result = await files_service.create_upload_url(
        session,
        tenant,
        UploadUrlRequest(filename=filename, file_size=file_size, content_type=mime_type),
    )
    return json.dumps(
        {
            "file_id": str(result.file_id),
            "upload_url": result.upload_url,
            "expires_at": result.expires_at.isoformat(),
            "instructions": (
                "PUT the file bytes to upload_url with the same Content-Type as mime_type, "
                "then call complete_upload with file_id."
            ),
        },
        indent=2,
    )


async def complete_upload(session: AsyncSession, tenant: Tenant, file_id: str) -> str:
    result = await files_service.complete_upload(session, tenant, _parse_file_id(file_id))
    return _dump(result)


async def download_file(session: AsyncSession, tenant: Tenant, file_id: str) -> str:
    result = await files_service.get_download_url(session, tenant, _parse_file_id(file_id))
    return json.dumps(result, indent=2)
