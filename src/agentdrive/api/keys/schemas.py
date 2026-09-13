import uuid
from datetime import datetime

from pydantic import BaseModel


class ApiKeyCreate(BaseModel):
    name: str | None = None
    expires_at: datetime | None = None


class ApiKeyCreateResponse(BaseModel):
    """Returned only on creation — includes the raw key (shown once)."""

    id: uuid.UUID
    key: str
    key_prefix: str
    name: str | None
    created_at: datetime
    expires_at: datetime | None


class ApiKeyResponse(BaseModel):
    """Used for list — never includes the full key."""

    id: uuid.UUID
    key_prefix: str
    name: str | None
    created_at: datetime
    expires_at: datetime | None
    revoked_at: datetime | None
    last_used: datetime | None

    model_config = {"from_attributes": True}


class ApiKeyListResponse(BaseModel):
    api_keys: list[ApiKeyResponse]
    total: int
