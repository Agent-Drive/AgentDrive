import uuid
from datetime import datetime
from pydantic import BaseModel, Field


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
    collection_id: uuid.UUID | None
    metadata: dict = Field(validation_alias="extra_metadata")
    created_at: datetime
    chunk_count: int | None = None
    model_config = {"from_attributes": True, "populate_by_name": True}


class FileListResponse(BaseModel):
    files: list[FileDetailResponse]
    total: int
