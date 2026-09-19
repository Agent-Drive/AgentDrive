import asyncio
import json
from pathlib import Path

import httpx

from agentdrive_mcp.upload import upload_via_signed_url


def _run(coro):
    return asyncio.run(coro)


def test_happy_path_url_put_complete(tmp_path: Path) -> None:
    source = tmp_path / "report.pdf"
    source.write_bytes(b"%PDF-1.4 fake")
    calls: list[str] = []

    def api_handler(request: httpx.Request) -> httpx.Response:
        calls.append(f"{request.method} {request.url.path}")
        if request.method == "POST" and request.url.path == "/v1/files/upload-url":
            body = json.loads(request.content)
            assert body["filename"] == "report.pdf"
            assert body["content_type"] == "application/pdf"
            assert body["file_size"] == source.stat().st_size
            assert request.headers["authorization"] == "Bearer test-key"
            return httpx.Response(
                201,
                json={
                    "file_id": "11111111-1111-1111-1111-111111111111",
                    "upload_url": "https://storage.example/put",
                    "expires_at": "2026-01-01T00:00:00Z",
                },
            )
        if request.method == "POST" and request.url.path.endswith("/complete"):
            return httpx.Response(
                200,
                json={
                    "id": "11111111-1111-1111-1111-111111111111",
                    "filename": "report.pdf",
                    "content_type": "pdf",
                    "file_size": source.stat().st_size,
                    "status": "pending",
                },
            )
        return httpx.Response(500, text=f"unexpected {request.method} {request.url}")

    def storage_handler(request: httpx.Request) -> httpx.Response:
        calls.append(f"{request.method} {request.url}")
        assert request.method == "PUT"
        assert request.headers["content-type"] == "application/pdf"
        assert "authorization" not in request.headers
        assert request.content == source.read_bytes()
        return httpx.Response(200)

    api_client = httpx.AsyncClient(
        base_url="https://api.example",
        headers={"Authorization": "Bearer test-key"},
        transport=httpx.MockTransport(api_handler),
    )
    storage_client = httpx.AsyncClient(transport=httpx.MockTransport(storage_handler))

    async def _exercise() -> str:
        async with api_client, storage_client:
            return await upload_via_signed_url(source, api_client, storage_client)

    result = json.loads(_run(_exercise()))
    assert result["status"] == "pending"
    assert result["id"] == "11111111-1111-1111-1111-111111111111"
    assert calls == [
        "POST /v1/files/upload-url",
        "PUT https://storage.example/put",
        "POST /v1/files/11111111-1111-1111-1111-111111111111/complete",
    ]


def test_upload_url_413_does_not_put(tmp_path: Path) -> None:
    source = tmp_path / "huge.bin"
    source.write_bytes(b"x")
    storage_called = False

    def api_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(413, json={"detail": "File exceeds 5368709120 byte limit"})

    def storage_handler(request: httpx.Request) -> httpx.Response:
        nonlocal storage_called
        storage_called = True
        return httpx.Response(200)

    api_client = httpx.AsyncClient(
        base_url="https://api.example",
        transport=httpx.MockTransport(api_handler),
    )
    storage_client = httpx.AsyncClient(transport=httpx.MockTransport(storage_handler))

    async def _exercise() -> str:
        async with api_client, storage_client:
            return await upload_via_signed_url(source, api_client, storage_client)

    result = _run(_exercise())
    assert "413" in result
    assert storage_called is False


def test_put_failure_does_not_complete(tmp_path: Path) -> None:
    source = tmp_path / "notes.txt"
    source.write_bytes(b"hello")
    calls: list[str] = []

    def api_handler(request: httpx.Request) -> httpx.Response:
        calls.append(f"{request.method} {request.url.path}")
        if request.url.path == "/v1/files/upload-url":
            return httpx.Response(
                201,
                json={
                    "file_id": "22222222-2222-2222-2222-222222222222",
                    "upload_url": "https://storage.example/put",
                    "expires_at": "2026-01-01T00:00:00Z",
                },
            )
        return httpx.Response(200, json={"status": "pending"})

    def storage_handler(request: httpx.Request) -> httpx.Response:
        calls.append("PUT")
        return httpx.Response(403, text="signature mismatch")

    api_client = httpx.AsyncClient(
        base_url="https://api.example",
        transport=httpx.MockTransport(api_handler),
    )
    storage_client = httpx.AsyncClient(transport=httpx.MockTransport(storage_handler))

    async def _exercise() -> str:
        async with api_client, storage_client:
            return await upload_via_signed_url(source, api_client, storage_client)

    result = _run(_exercise())
    assert "403" in result
    assert "signature mismatch" in result
    assert calls == ["POST /v1/files/upload-url", "PUT"]


def test_oversized_file_still_hits_api(tmp_path: Path) -> None:
    source = tmp_path / "huge.bin"
    source.write_bytes(b"too-big")
    seen_sizes: list[int] = []

    def api_handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen_sizes.append(body["file_size"])
        return httpx.Response(413, json={"detail": "File exceeds 5368709120 byte limit"})

    api_client = httpx.AsyncClient(
        base_url="https://api.example",
        transport=httpx.MockTransport(api_handler),
    )

    async def _exercise() -> str:
        async with api_client:
            return await upload_via_signed_url(source, api_client)

    result = _run(_exercise())
    assert seen_sizes == [source.stat().st_size]
    assert "413" in result
