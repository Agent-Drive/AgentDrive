import uuid

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from agentdrive.engine.data.session import get_session
from agentdrive.api.dependencies import get_current_tenant
from agentdrive.engine.data.models.tenant import Tenant
from agentdrive.api.files import service
from agentdrive.api.files.schemas import (
    FileDetailResponse,
    FileListResponse,
    FileUploadResponse,
    UploadUrlRequest,
    UploadUrlResponse,
)

router = APIRouter(prefix="/v1/files", tags=["files"])


@router.post("", status_code=202, response_model=FileUploadResponse)
async def upload_file(
    file: UploadFile = File(...),
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
):
    return await service.upload_file(session, tenant, file)


@router.post("/upload-url", status_code=201, response_model=UploadUrlResponse)
async def create_upload_url(
    body: UploadUrlRequest,
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
):
    return await service.create_upload_url(session, tenant, body)


@router.post("/{file_id}/complete", status_code=200, response_model=FileUploadResponse)
async def complete_upload(
    file_id: uuid.UUID,
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
):
    return await service.complete_upload(session, tenant, file_id)


@router.get("/{file_id}", response_model=FileDetailResponse)
async def get_file(
    file_id: uuid.UUID,
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
):
    return await service.get_file(session, tenant, file_id)


@router.get("/{file_id}/download")
async def download_file(
    file_id: uuid.UUID,
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
):
    return await service.download_file(session, tenant, file_id)


@router.get("", response_model=FileListResponse)
async def list_files(
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
):
    return await service.list_files(session, tenant)


@router.delete("/{file_id}", status_code=204)
async def delete_file(
    file_id: uuid.UUID,
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
):
    return await service.delete_file(session, tenant, file_id)
