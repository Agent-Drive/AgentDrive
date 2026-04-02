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
