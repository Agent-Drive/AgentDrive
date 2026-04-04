import uuid
from datetime import datetime

from pydantic import BaseModel


# --- KB Config ---
class KBConfig(BaseModel):
    article_types: list[str] = ["concept", "summary", "connection", "question"]
    max_article_tokens: int = 8192


# --- KB Schemas ---
class KBCreateRequest(BaseModel):
    name: str
    description: str | None = None
    config: KBConfig = KBConfig()


class KBResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    status: str
    config: dict
    created_at: datetime
    updated_at: datetime
    file_count: int = 0
    article_count: int = 0

    model_config = {"from_attributes": True}


class KBListResponse(BaseModel):
    knowledge_bases: list[KBResponse]
    total: int


# --- File Management ---
class KBAddFilesRequest(BaseModel):
    file_ids: list[uuid.UUID]


class KBRemoveFilesRequest(BaseModel):
    file_ids: list[uuid.UUID]


# --- Article Schemas ---
class ArticleSourceResponse(BaseModel):
    chunk_id: uuid.UUID
    excerpt: str

    model_config = {"from_attributes": True}


class ArticleResponse(BaseModel):
    id: uuid.UUID
    title: str
    content: str
    article_type: str
    category: str | None
    status: str
    token_count: int
    created_at: datetime
    updated_at: datetime
    sources: list[ArticleSourceResponse] = []

    model_config = {"from_attributes": True}


class ArticleLinkResponse(BaseModel):
    id: uuid.UUID
    source_article_id: uuid.UUID
    target_article_id: uuid.UUID
    link_type: str

    model_config = {"from_attributes": True}


class ArticleListResponse(BaseModel):
    articles: list[ArticleResponse]
    total: int


# --- Derive Article ---
class DeriveArticleRequest(BaseModel):
    title: str
    content: str
    source_ids: list[uuid.UUID] = []


# --- KB Search ---
class KBSearchRequest(BaseModel):
    query: str
    top_k: int = 5
    articles_only: bool = False
    content_types: list[str] | None = None


class KBSearchResultResponse(BaseModel):
    result_type: str  # "chunk" | "article"
    id: uuid.UUID
    content: str
    score: float
    # chunk-specific
    file_id: uuid.UUID | None = None
    context_prefix: str | None = None
    content_type: str | None = None
    parent_chunk_id: uuid.UUID | None = None
    parent_content: str | None = None
    # article-specific
    title: str | None = None
    article_type: str | None = None
    category: str | None = None
    source_refs: list[ArticleSourceResponse] | None = None


class KBSearchResponse(BaseModel):
    results: list[KBSearchResultResponse]
    query_tokens: int
    search_time_ms: int


# --- Health Check ---
class HealthIssue(BaseModel):
    type: str
    article_id: uuid.UUID | None = None
    topic: str | None = None
    articles: list[uuid.UUID] | None = None
    reason: str | None = None
    details: str | None = None
    mentioned_in: list[uuid.UUID] | None = None


class HealthSuggestion(BaseModel):
    action: str
    topic: str | None = None
    article_ids: list[uuid.UUID] | None = None
    source: uuid.UUID | None = None
    target: uuid.UUID | None = None


class HealthCheckResponse(BaseModel):
    score: float
    issues: list[HealthIssue]
    suggestions: list[HealthSuggestion]


class RepairRequest(BaseModel):
    apply: list[str]  # e.g., ["stale", "gaps"]
