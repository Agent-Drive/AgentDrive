import uuid
from datetime import datetime
from pydantic import BaseModel, Field


class UploadUrlRequest(BaseModel):
    filename: str
    content_type: str = "application/octet-stream"
    file_size: int


class UploadUrlResponse(BaseModel):
    file_id: uuid.UUID
    upload_url: str
    expires_at: datetime


class FileUploadResponse(BaseModel):
    id: uuid.UUID
    filename: str
    content_type: str
    file_size: int
    status: str
    model_config = {"from_attributes": True}


class FileDetailResponse(BaseModel):
    id: uuid.UUID
    filename: str
    content_type: str
    file_size: int
    status: str
    metadata: dict = Field(validation_alias="extra_metadata")
    created_at: datetime
    updated_at: datetime
    chunk_count: int | None = None
    total_batches: int = 0
    completed_batches: int = 0
    current_phase: str | None = None
    model_config = {"from_attributes": True, "populate_by_name": True}


class FileListResponse(BaseModel):
    files: list[FileDetailResponse]
    total: int
