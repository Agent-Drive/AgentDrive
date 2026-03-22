import uuid
from datetime import datetime
from pydantic import BaseModel


class CollectionCreate(BaseModel):
    name: str
    description: str | None = None


class CollectionResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    created_at: datetime
    file_count: int | None = None
    model_config = {"from_attributes": True}


class CollectionListResponse(BaseModel):
    collections: list[CollectionResponse]
    total: int
