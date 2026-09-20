class CoreError(Exception):
    """Product error. api maps this to HTTP / MCP error text."""


class FileNotFound(CoreError):
    def __init__(self, message: str = "File not found") -> None:
        super().__init__(message)


class UploadNotReady(CoreError):
    def __init__(self, message: str = "File not found or not in uploading state") -> None:
        super().__init__(message)


class UploadBlobMissing(CoreError):
    def __init__(self, message: str = "Upload not found in storage") -> None:
        super().__init__(message)


class StoredBlobMissing(CoreError):
    def __init__(self, message: str = "File blob not found in storage") -> None:
        super().__init__(message)


class ChunkNotFound(CoreError):
    def __init__(self, message: str = "Chunk not found") -> None:
        super().__init__(message)


class FileTooLarge(CoreError):
    def __init__(self, message: str) -> None:
        super().__init__(message)
