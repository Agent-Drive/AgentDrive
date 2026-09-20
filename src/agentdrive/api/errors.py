from fastapi import HTTPException

from agentdrive.core.errors import (
    ChunkNotFound,
    CoreError,
    FileNotFound,
    FileTooLarge,
    StoredBlobMissing,
    UploadBlobMissing,
    UploadNotReady,
)

_STATUS = {
    FileNotFound: 404,
    UploadNotReady: 404,
    ChunkNotFound: 404,
    UploadBlobMissing: 400,
    StoredBlobMissing: 502,
    FileTooLarge: 413,
}


def status_for(exc: CoreError) -> int:
    return _STATUS[type(exc)]


def raise_http(exc: CoreError) -> None:
    raise HTTPException(status_code=status_for(exc), detail=str(exc)) from exc


def mcp_message(exc: CoreError) -> str:
    return f"Error ({status_for(exc)}): {exc}"
