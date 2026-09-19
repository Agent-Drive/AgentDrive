import json
import mimetypes
from pathlib import Path

import httpx

STORAGE_PUT_TIMEOUT = 3600.0


def guess_upload_mime(filename: str) -> str:
    mime, _ = mimetypes.guess_type(filename)
    return mime or "application/octet-stream"


def _error_text(response: httpx.Response) -> str:
    return f"Error: {response.status_code} {response.text}"


async def _iter_file_chunks(path: Path, chunk_size: int = 1024 * 1024):
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            yield chunk


async def upload_via_signed_url(
    file_path: Path,
    api_client: httpx.AsyncClient,
    storage_client: httpx.AsyncClient | None = None,
) -> str:
    """Upload via signed URL: request URL, PUT bytes to storage, complete."""
    file_size = file_path.stat().st_size
    content_type = guess_upload_mime(file_path.name)

    url_resp = await api_client.post(
        "/v1/files/upload-url",
        json={
            "filename": file_path.name,
            "content_type": content_type,
            "file_size": file_size,
        },
    )
    if url_resp.status_code != 201:
        return _error_text(url_resp)

    payload = url_resp.json()
    file_id = payload["file_id"]
    upload_url = payload["upload_url"]

    owns_storage = storage_client is None
    if owns_storage:
        storage_client = httpx.AsyncClient(timeout=httpx.Timeout(STORAGE_PUT_TIMEOUT))
    try:
        put_resp = await storage_client.put(
            upload_url,
            content=_iter_file_chunks(file_path),
            headers={
                "Content-Type": content_type,
                "Content-Length": str(file_size),
            },
            timeout=STORAGE_PUT_TIMEOUT,
        )
    finally:
        if owns_storage:
            await storage_client.aclose()

    if put_resp.status_code >= 400:
        return _error_text(put_resp)

    complete_resp = await api_client.post(f"/v1/files/{file_id}/complete")
    if complete_resp.status_code != 200:
        return _error_text(complete_resp)
    return json.dumps(complete_resp.json(), indent=2)
