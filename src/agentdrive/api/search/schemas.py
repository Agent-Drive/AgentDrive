from pydantic import BaseModel


class SearchRequest(BaseModel):
    query: str
    top_k: int = 5
    content_types: list[str] | None = None
    include_parent: bool = True


class SearchResultResponse(BaseModel):
    chunk_id: str
    content: str
    token_count: int
    score: float
    content_type: str
    parent_content: str | None = None
    parent_token_count: int | None = None
    provenance: dict


class SearchResponse(BaseModel):
    results: list[SearchResultResponse]
    query_tokens: int
    search_time_ms: int
