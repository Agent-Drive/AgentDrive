from pydantic import BaseModel


class ErrorResponse(BaseModel):
    detail: str


class PaginationParams(BaseModel):
    offset: int = 0
    limit: int = 50
