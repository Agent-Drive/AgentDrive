import enum


class FileStatus(str, enum.Enum):
    UPLOADING = "uploading"
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class BatchStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ContentType(str, enum.Enum):
    PDF = "pdf"
    MARKDOWN = "markdown"
    CODE = "code"
    JSON = "json"
    YAML = "yaml"
    CSV = "csv"
    XLSX = "xlsx"
    NOTEBOOK = "notebook"
    IMAGE = "image"
    TEXT = "text"


class KBStatus(str, enum.Enum):
    ACTIVE = "active"
    COMPILING = "compiling"
    ERROR = "error"


class ArticleType(str, enum.Enum):
    CONCEPT = "concept"
    SUMMARY = "summary"
    CONNECTION = "connection"
    QUESTION = "question"
    DERIVED = "derived"
    MANUAL = "manual"


class ArticleStatus(str, enum.Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    STALE = "stale"


class LinkType(str, enum.Enum):
    RELATED = "related"
    CONTRADICTS = "contradicts"
    EXTENDS = "extends"
    PREREQUISITE = "prerequisite"
