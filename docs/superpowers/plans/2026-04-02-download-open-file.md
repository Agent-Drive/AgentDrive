# Download & Open File Locally — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable downloading files from AgentDrive to a structured local directory via MCP, with optional native app open.

**Architecture:** New REST streaming endpoint (`GET /v1/files/{file_id}/download`) backed by a new `StorageService.download_stream()` method. Shared `local_files.py` module handles manifest-based caching, path resolution, and native open. Both MCP servers (standalone + in-process) add a `download_file` tool that delegates to the shared module.

**Tech Stack:** FastAPI StreamingResponse, GCS blob streaming, httpx for MCP HTTP calls, JSON manifest with atomic writes.

**Spec:** `docs/superpowers/specs/2026-04-02-download-open-file-design.md`

---

### Task 1: Add `updated_at` and `collection_name` to FileDetailResponse

**Files:**
- Modify: `src/agentdrive/schemas/files.py:28-41`
- Modify: `src/agentdrive/routers/files.py:114-126`
- Test: `tests/test_files.py`

- [ ] **Step 1: Write failing test for `updated_at` in file detail response**

```python
# In tests/test_files.py, add after test_get_file_status

@pytest.mark.asyncio
@patch("agentdrive.routers.files.StorageService")
async def test_get_file_detail_includes_updated_at(mock_storage, authed_client):
    client, tenant = authed_client
    mock_storage.return_value.upload.return_value = "fake/path"
    resp = await client.post(
        "/v1/files",
        files={"file": ("test.txt", b"hello", "text/plain")},
    )
    file_id = resp.json()["id"]
    detail = await client.get(f"/v1/files/{file_id}")
    assert detail.status_code == 200
    assert "updated_at" in detail.json()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_files.py::test_get_file_detail_includes_updated_at -v`
Expected: FAIL — `updated_at` not in response JSON.

- [ ] **Step 3: Add `updated_at` and `collection_name` to `FileDetailResponse`**

In `src/agentdrive/schemas/files.py`, add two fields to `FileDetailResponse` (after line 36):

```python
class FileDetailResponse(BaseModel):
    id: uuid.UUID
    filename: str
    content_type: str
    file_size: int
    status: str
    collection_id: uuid.UUID | None
    metadata: dict = Field(validation_alias="extra_metadata")
    created_at: datetime
    updated_at: datetime
    collection_name: str | None = None
    chunk_count: int | None = None
    total_batches: int = 0
    completed_batches: int = 0
    current_phase: str | None = None
    model_config = {"from_attributes": True, "populate_by_name": True}
```

Note: `updated_at` is new. `collection_name` is new (default None). `total_batches` and `completed_batches` keep their existing `int = 0` defaults. `model_config` matches the existing dict style.

Add imports at top of `files.py` schema if not already present: `from datetime import datetime`.

In `src/agentdrive/routers/files.py`, add these imports at the top:

```python
from sqlalchemy import func
from sqlalchemy.orm import selectinload
from agentdrive.models.chunk import Chunk
```

Update `get_file()` (around line 114) to eagerly load the collection relationship and set `collection_name`:

```python
@router.get("/{file_id}", response_model=FileDetailResponse)
async def get_file(
    file_id: uuid.UUID,
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
):
    from sqlalchemy.orm import selectinload

    result = await session.execute(
        select(File)
        .options(selectinload(File.collection))
        .where(File.id == file_id, File.tenant_id == tenant.id)
    )
    file = result.scalar_one_or_none()
    if not file:
        raise HTTPException(status_code=404, detail="File not found")
    chunk_count = await session.scalar(
        select(func.count()).where(Chunk.file_id == file.id)
    )
    response = FileDetailResponse.model_validate(file)
    response.chunk_count = chunk_count
    response.collection_name = file.collection.name if file.collection else None
    return response
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_files.py::test_get_file_detail_includes_updated_at -v`
Expected: PASS

- [ ] **Step 5: Write test for `collection_name` in response**

```python
@pytest.mark.asyncio
@patch("agentdrive.routers.files.StorageService")
async def test_get_file_detail_includes_collection_name(mock_storage, authed_client):
    client, tenant = authed_client
    mock_storage.return_value.upload.return_value = "fake/path"
    # Create collection
    col_resp = await client.post(
        "/v1/collections", json={"name": "research"}
    )
    col_id = col_resp.json()["id"]
    # Upload file to collection
    resp = await client.post(
        "/v1/files",
        files={"file": ("test.txt", b"hello", "text/plain")},
        data={"collection": col_id},
    )
    file_id = resp.json()["id"]
    detail = await client.get(f"/v1/files/{file_id}")
    assert detail.status_code == 200
    assert detail.json()["collection_name"] == "research"
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/test_files.py::test_get_file_detail_includes_collection_name -v`
Expected: PASS

- [ ] **Step 7: Update `list_files` to also eagerly load collections**

In `src/agentdrive/routers/files.py`, update the `list_files` endpoint to use `selectinload(File.collection)` in its query and set `collection_name` on each response item. This prevents `collection_name` from always being `None` in list responses.

```python
# In list_files, add .options(selectinload(File.collection)) to the query
# and after building each FileDetailResponse, set:
#   resp.collection_name = file.collection.name if file.collection else None
```

- [ ] **Step 8: Run full test suite to confirm no regressions**

Run: `uv run pytest tests/test_files.py -v`
Expected: All tests PASS

- [ ] **Step 9: Commit**

```bash
git add src/agentdrive/schemas/files.py src/agentdrive/routers/files.py tests/test_files.py
git commit -m "feat(files): add updated_at and collection_name to FileDetailResponse"
```

---

### Task 2: Add `StorageService.download_stream()` method

**Files:**
- Modify: `src/agentdrive/services/storage.py:34` (add after `download` method)
- Test: `tests/test_streaming_download.py` (extend existing)

- [ ] **Step 1: Write failing test for `download_stream()`**

```python
# In tests/test_streaming_download.py, add:

def test_download_stream_yields_chunks(tmp_path, monkeypatch):
    """download_stream yields file content in chunks."""
    from agentdrive.services.storage import StorageService
    from unittest.mock import MagicMock
    import io

    content = b"A" * 8192 + b"B" * 4096  # 12KB total
    fake_blob = MagicMock()
    fake_blob.exists.return_value = True
    # io.BytesIO is itself a context manager, so blob.open() can return it directly
    fake_blob.open.return_value = io.BytesIO(content)

    svc = StorageService()
    monkeypatch.setattr(svc, "_bucket", MagicMock())
    svc._bucket.blob.return_value = fake_blob

    chunks = list(svc.download_stream("fake/path"))
    assert b"".join(chunks) == content
    assert len(chunks) >= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_streaming_download.py::test_download_stream_yields_chunks -v`
Expected: FAIL — `download_stream` not found.

- [ ] **Step 3: Implement `download_stream()` on StorageService**

In `src/agentdrive/services/storage.py`, add after the existing `download` method (line 36):

```python
def download_stream(
    self, gcs_path: str, chunk_size: int = 256 * 1024
) -> Iterator[bytes]:
    """Yield file content in chunks from GCS. Raises if blob does not exist."""
    blob = self._bucket.blob(gcs_path)
    if not blob.exists():
        raise FileNotFoundError(f"Blob not found: {gcs_path}")
    with blob.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            yield chunk
```

Add `Iterator` to imports at top of file:

```python
from collections.abc import Iterator
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_streaming_download.py::test_download_stream_yields_chunks -v`
Expected: PASS

- [ ] **Step 5: Write test for missing blob error**

```python
def test_download_stream_raises_on_missing_blob(monkeypatch):
    from agentdrive.services.storage import StorageService
    from unittest.mock import MagicMock

    fake_blob = MagicMock()
    fake_blob.exists.return_value = False

    svc = StorageService()
    monkeypatch.setattr(svc, "_bucket", MagicMock())
    svc._bucket.blob.return_value = fake_blob

    with pytest.raises(FileNotFoundError):
        list(svc.download_stream("missing/path"))
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/test_streaming_download.py::test_download_stream_raises_on_missing_blob -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/agentdrive/services/storage.py tests/test_streaming_download.py
git commit -m "feat(storage): add download_stream for chunked GCS reads"
```

---

### Task 3: Add REST download endpoint

**Files:**
- Modify: `src/agentdrive/routers/files.py` (add endpoint after existing `get_file`)
- Test: `tests/test_files.py`

- [ ] **Step 1: Write failing test for download endpoint**

```python
@pytest.mark.asyncio
@patch("agentdrive.routers.files.StorageService")
async def test_download_file(mock_storage, authed_client):
    client, tenant = authed_client
    file_content = b"hello world file content"
    mock_storage.return_value.upload.return_value = "fake/path"
    mock_storage.return_value.download_stream.return_value = iter([file_content])

    # Upload
    resp = await client.post(
        "/v1/files",
        files={"file": ("test.txt", file_content, "text/plain")},
    )
    file_id = resp.json()["id"]

    # Download
    dl_resp = await client.get(f"/v1/files/{file_id}/download")
    assert dl_resp.status_code == 200
    assert dl_resp.content == file_content
    assert "attachment" in dl_resp.headers.get("content-disposition", "")
    assert "test.txt" in dl_resp.headers.get("content-disposition", "")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_files.py::test_download_file -v`
Expected: FAIL — 404, endpoint doesn't exist.

- [ ] **Step 3: Implement download endpoint**

In `src/agentdrive/routers/files.py`, add after the `get_file` endpoint:

```python
from fastapi.responses import StreamingResponse

@router.get("/{file_id}/download")
async def download_file(
    file_id: uuid.UUID,
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(File).where(File.id == file_id, File.tenant_id == tenant.id)
    )
    file = result.scalar_one_or_none()
    if not file:
        raise HTTPException(status_code=404, detail="File not found")

    storage = StorageService()
    try:
        stream = storage.download_stream(file.gcs_path)
    except FileNotFoundError:
        raise HTTPException(status_code=502, detail="File blob not found in storage")

    return StreamingResponse(
        stream,
        media_type=file.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{file.filename}"',
            "Content-Length": str(file.file_size),
        },
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_files.py::test_download_file -v`
Expected: PASS

- [ ] **Step 5: Write test for 404 on missing file**

```python
@pytest.mark.asyncio
async def test_download_file_not_found(authed_client):
    client, tenant = authed_client
    resp = await client.get(f"/v1/files/{uuid.uuid4()}/download")
    assert resp.status_code == 404
```

- [ ] **Step 6: Run test and confirm it passes**

Run: `uv run pytest tests/test_files.py::test_download_file_not_found -v`
Expected: PASS

- [ ] **Step 7: Run full file tests**

Run: `uv run pytest tests/test_files.py -v`
Expected: All PASS

- [ ] **Step 8: Commit**

```bash
git add src/agentdrive/routers/files.py tests/test_files.py
git commit -m "feat(files): add GET /v1/files/{file_id}/download streaming endpoint"
```

---

### Task 4: Implement shared `local_files.py` module

**Files:**
- Create: `packages/mcp/src/agentdrive_mcp/local_files.py`
- Create: `packages/mcp/tests/test_local_files.py`

- [ ] **Step 1: Write failing tests for manifest operations**

Create `packages/mcp/tests/test_local_files.py`:

```python
import json
import pytest
from pathlib import Path
from datetime import datetime, timezone


@pytest.fixture
def files_dir(tmp_path):
    """Use a temp directory instead of ~/.agentdrive/files/."""
    return tmp_path / "files"


class TestManifest:
    def test_read_manifest_returns_empty_when_missing(self, files_dir):
        from agentdrive_mcp.local_files import read_manifest

        result = read_manifest(files_dir)
        assert result == {"version": 1, "files": {}}

    def test_read_manifest_returns_empty_on_corrupt_json(self, files_dir):
        from agentdrive_mcp.local_files import read_manifest

        files_dir.mkdir(parents=True)
        (files_dir / ".manifest.json").write_text("not json{{{")
        result = read_manifest(files_dir)
        assert result == {"version": 1, "files": {}}

    def test_write_then_read_manifest(self, files_dir):
        from agentdrive_mcp.local_files import read_manifest, write_manifest

        data = {
            "version": 1,
            "files": {
                "abc-123": {
                    "local_path": "default/test.txt",
                    "filename": "test.txt",
                    "collection": "default",
                    "file_id": "abc-123",
                    "file_size": 100,
                    "content_type": "text/plain",
                    "downloaded_at": "2026-04-02T10:00:00Z",
                    "remote_updated_at": "2026-04-01T08:00:00Z",
                },
            },
        }
        write_manifest(data, files_dir)
        assert read_manifest(files_dir) == data
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd packages/mcp && uv run pytest tests/test_local_files.py::TestManifest -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement manifest operations in `local_files.py`**

Create `packages/mcp/src/agentdrive_mcp/local_files.py`:

```python
"""Local file management for AgentDrive MCP — manifest, path resolution, native open."""

from __future__ import annotations

import json
import platform
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

AGENTDRIVE_FILES_DIR = Path.home() / ".agentdrive" / "files"
MANIFEST_FILENAME = ".manifest.json"


def _empty_manifest() -> dict:
    return {"version": 1, "files": {}}


def read_manifest(files_dir: Path = AGENTDRIVE_FILES_DIR) -> dict:
    """Load manifest from disk. Returns empty manifest if missing or corrupt."""
    manifest_path = files_dir / MANIFEST_FILENAME
    if not manifest_path.exists():
        return _empty_manifest()
    try:
        data = json.loads(manifest_path.read_text())
        if not isinstance(data, dict) or "files" not in data:
            return _empty_manifest()
        return data
    except (json.JSONDecodeError, OSError):
        return _empty_manifest()


def write_manifest(data: dict, files_dir: Path = AGENTDRIVE_FILES_DIR) -> None:
    """Atomically write manifest to disk (temp file + rename)."""
    files_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = files_dir / MANIFEST_FILENAME
    import os

    fd, tmp_path = tempfile.mkstemp(
        dir=files_dir, prefix=".manifest_", suffix=".tmp"
    )
    os.close(fd)  # close immediately; write_text opens by path
    try:
        Path(tmp_path).write_text(json.dumps(data, indent=2))
        Path(tmp_path).replace(manifest_path)
    except Exception:
        Path(tmp_path).unlink(missing_ok=True)
        raise
```

- [ ] **Step 4: Run manifest tests to verify they pass**

Run: `cd packages/mcp && uv run pytest tests/test_local_files.py::TestManifest -v`
Expected: PASS

- [ ] **Step 5: Write failing tests for path resolution and caching**

Append to `packages/mcp/tests/test_local_files.py`:

```python
class TestPathResolution:
    def test_resolve_path_with_collection(self, files_dir):
        from agentdrive_mcp.local_files import resolve_local_path

        path = resolve_local_path("report.xlsx", "research", "abc-123", files_dir)
        assert path == files_dir / "research" / "report.xlsx"

    def test_resolve_path_default_collection(self, files_dir):
        from agentdrive_mcp.local_files import resolve_local_path

        path = resolve_local_path("notes.txt", None, "abc-123", files_dir)
        assert path == files_dir / "default" / "notes.txt"

    def test_resolve_path_handles_collision(self, files_dir):
        from agentdrive_mcp.local_files import resolve_local_path

        # Create existing file at the target path
        target = files_dir / "default" / "notes.txt"
        target.parent.mkdir(parents=True)
        target.write_text("existing")

        path = resolve_local_path("notes.txt", None, "abc-12345-uuid", files_dir)
        assert path == files_dir / "default" / "notes_abc-1234.txt"


class TestCaching:
    def test_is_cached_false_when_not_in_manifest(self, files_dir):
        from agentdrive_mcp.local_files import is_cached

        assert is_cached("nonexistent-id", files_dir) is False

    def test_is_cached_false_when_file_deleted_from_disk(self, files_dir):
        from agentdrive_mcp.local_files import is_cached, write_manifest

        write_manifest(
            {
                "version": 1,
                "files": {
                    "abc-123": {
                        "local_path": "default/gone.txt",
                        "filename": "gone.txt",
                        "collection": "default",
                        "file_id": "abc-123",
                        "file_size": 5,
                        "content_type": "text/plain",
                        "downloaded_at": "2026-04-02T10:00:00Z",
                        "remote_updated_at": "2026-04-01T08:00:00Z",
                    }
                },
            },
            files_dir,
        )
        assert is_cached("abc-123", files_dir) is False

    def test_is_stale_when_remote_is_newer(self, files_dir):
        from agentdrive_mcp.local_files import is_stale, write_manifest

        # Create file on disk so it's "cached"
        (files_dir / "default").mkdir(parents=True)
        (files_dir / "default" / "doc.txt").write_text("old")
        write_manifest(
            {
                "version": 1,
                "files": {
                    "abc-123": {
                        "local_path": "default/doc.txt",
                        "filename": "doc.txt",
                        "collection": "default",
                        "file_id": "abc-123",
                        "file_size": 3,
                        "content_type": "text/plain",
                        "downloaded_at": "2026-04-01T10:00:00Z",
                        "remote_updated_at": "2026-04-01T08:00:00Z",
                    }
                },
            },
            files_dir,
        )
        # Remote is newer
        assert is_stale("abc-123", "2026-04-02T12:00:00Z", files_dir) is True
        # Remote is same
        assert is_stale("abc-123", "2026-04-01T08:00:00Z", files_dir) is False
```

- [ ] **Step 6: Implement path resolution and caching functions**

Add to `packages/mcp/src/agentdrive_mcp/local_files.py`:

```python
def resolve_local_path(
    filename: str,
    collection: str | None,
    file_id: str,
    files_dir: Path = AGENTDRIVE_FILES_DIR,
) -> Path:
    """Build local path. Appends file_id prefix on name collision."""
    collection_name = collection or "default"
    target = files_dir / collection_name / filename
    if target.exists():
        stem = Path(filename).stem
        suffix = Path(filename).suffix
        short_id = file_id[:8]
        target = files_dir / collection_name / f"{stem}_{short_id}{suffix}"
    return target


def is_cached(file_id: str, files_dir: Path = AGENTDRIVE_FILES_DIR) -> bool:
    """True if file is in manifest AND exists on disk."""
    manifest = read_manifest(files_dir)
    entry = manifest.get("files", {}).get(file_id)
    if not entry:
        return False
    local_path = files_dir / entry["local_path"]
    return local_path.exists()


def is_stale(
    file_id: str,
    remote_updated_at: str,
    files_dir: Path = AGENTDRIVE_FILES_DIR,
) -> bool:
    """True if remote file is newer than the cached version."""
    manifest = read_manifest(files_dir)
    entry = manifest.get("files", {}).get(file_id)
    if not entry:
        return True
    return remote_updated_at > entry.get("remote_updated_at", "")
```

- [ ] **Step 7: Run all tests so far**

Run: `cd packages/mcp && uv run pytest tests/test_local_files.py -v`
Expected: All PASS

- [ ] **Step 8: Write failing test for `save_file`**

Append to `packages/mcp/tests/test_local_files.py`:

```python
class TestSaveFile:
    def test_save_file_writes_bytes_and_updates_manifest(self, files_dir):
        from agentdrive_mcp.local_files import save_file, read_manifest

        content = b"file content here"
        metadata = {
            "filename": "report.txt",
            "collection": "research",
            "file_size": len(content),
            "content_type": "text/plain",
            "remote_updated_at": "2026-04-02T10:00:00Z",
        }
        result = save_file("file-001", iter([content]), metadata, files_dir)
        assert result["local_path"].endswith("research/report.txt")
        assert result["already_cached"] is False

        # File exists on disk
        saved = Path(result["local_path"])
        assert saved.read_bytes() == content

        # Manifest updated
        manifest = read_manifest(files_dir)
        assert "file-001" in manifest["files"]
        assert manifest["files"]["file-001"]["collection"] == "research"
```

- [ ] **Step 9: Implement `save_file`**

Add to `packages/mcp/src/agentdrive_mcp/local_files.py`:

```python
def save_file(
    file_id: str,
    byte_stream: Iterator[bytes],
    metadata: dict,
    files_dir: Path = AGENTDRIVE_FILES_DIR,
) -> dict:
    """Write streamed bytes to local path and update manifest. Returns result dict."""
    filename = metadata["filename"]
    collection = metadata.get("collection")

    # On re-download (stale update), reuse existing path from manifest
    manifest = read_manifest(files_dir)
    existing = manifest.get("files", {}).get(file_id)
    if existing:
        local_path = files_dir / existing["local_path"]
    else:
        local_path = resolve_local_path(filename, collection, file_id, files_dir)

    local_path.parent.mkdir(parents=True, exist_ok=True)
    with open(local_path, "wb") as f:
        for chunk in byte_stream:
            f.write(chunk)

    relative_path = str(local_path.relative_to(files_dir))
    now = datetime.now(timezone.utc).isoformat()

    manifest = read_manifest(files_dir)
    manifest["files"][file_id] = {
        "local_path": relative_path,
        "filename": filename,
        "collection": collection or "default",
        "file_id": file_id,
        "file_size": metadata["file_size"],
        "content_type": metadata["content_type"],
        "downloaded_at": now,
        "remote_updated_at": metadata["remote_updated_at"],
    }
    write_manifest(manifest, files_dir)

    return {
        "local_path": str(local_path),
        "filename": filename,
        "collection": collection or "default",
        "file_size": metadata["file_size"],
        "already_cached": False,
    }
```

Add `Iterator` to imports:

```python
from collections.abc import Iterator
```

- [ ] **Step 10: Run save_file test**

Run: `cd packages/mcp && uv run pytest tests/test_local_files.py::TestSaveFile -v`
Expected: PASS

- [ ] **Step 11: Write test for `open_native`**

Append to `packages/mcp/tests/test_local_files.py`:

```python
from unittest.mock import patch

class TestOpenNative:
    @patch("agentdrive_mcp.local_files.subprocess.Popen")
    @patch("agentdrive_mcp.local_files.platform.system", return_value="Darwin")
    def test_open_native_macos(self, mock_system, mock_popen):
        from agentdrive_mcp.local_files import open_native

        open_native(Path("/tmp/test.txt"))
        mock_popen.assert_called_once_with(["open", "/tmp/test.txt"])

    @patch("agentdrive_mcp.local_files.subprocess.Popen")
    @patch("agentdrive_mcp.local_files.platform.system", return_value="Linux")
    def test_open_native_linux(self, mock_system, mock_popen):
        from agentdrive_mcp.local_files import open_native

        open_native(Path("/tmp/test.txt"))
        mock_popen.assert_called_once_with(["xdg-open", "/tmp/test.txt"])
```

- [ ] **Step 12: Implement `open_native`**

Add to `packages/mcp/src/agentdrive_mcp/local_files.py`:

```python
def open_native(local_path: Path) -> None:
    """Open file in native OS application. Non-blocking (fire-and-forget)."""
    system = platform.system()
    if system == "Darwin":
        subprocess.Popen(["open", str(local_path)])
    else:
        subprocess.Popen(["xdg-open", str(local_path)])
```

- [ ] **Step 13: Run all local_files tests**

Run: `cd packages/mcp && uv run pytest tests/test_local_files.py -v`
Expected: All PASS

- [ ] **Step 14: Commit**

```bash
git add packages/mcp/src/agentdrive_mcp/local_files.py packages/mcp/tests/test_local_files.py
git commit -m "feat(mcp): add local_files module for manifest, path resolution, and native open"
```

---

### Task 5: Add `download_file` tool to standalone MCP server

**Files:**
- Modify: `packages/mcp/src/agentdrive_mcp/server.py:42-93` (add tool to list)
- Modify: `packages/mcp/src/agentdrive_mcp/server.py:96-161` (add tool handler)

- [ ] **Step 1: Add `download_file` to tool list in `list_tools()`**

In `packages/mcp/src/agentdrive_mcp/server.py`, add to the tools list (after line 92, before the closing `]`):

```python
        types.Tool(
            name="download_file",
            description="Download a file from Agent Drive to local disk. Optionally open it in the native OS application.",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_id": {
                        "type": "string",
                        "description": "UUID of the file to download",
                    },
                    "open": {
                        "type": "boolean",
                        "description": "Open the file in the native app after download (default: false)",
                        "default": False,
                    },
                },
                "required": ["file_id"],
            },
        ),
```

- [ ] **Step 2: Add `download_file` handler in `call_tool()`**

In `packages/mcp/src/agentdrive_mcp/server.py`, add to the `call_tool` dispatch (before the final else/raise):

```python
    elif name == "download_file":
        from agentdrive_mcp.local_files import (
            is_cached,
            is_stale,
            read_manifest,
            save_file,
            open_native,
            AGENTDRIVE_FILES_DIR,
        )
        from pathlib import Path

        file_id = arguments["file_id"]
        should_open = arguments.get("open", False)

        # Check cache
        if is_cached(file_id):
            # Fetch remote metadata to check staleness
            meta_resp = await client.get(
                f"{AGENT_DRIVE_URL}/v1/files/{file_id}", headers=_headers()
            )
            meta = meta_resp.json()
            remote_updated = meta.get("updated_at", "")
            if not is_stale(file_id, remote_updated):
                manifest = read_manifest()
                entry = manifest["files"][file_id]
                local_path = AGENTDRIVE_FILES_DIR / entry["local_path"]
                if should_open:
                    open_native(local_path)
                return [
                    types.TextContent(
                        type="text",
                        text=json.dumps({
                            "local_path": str(local_path),
                            "filename": entry["filename"],
                            "collection": entry["collection"],
                            "file_size": entry["file_size"],
                            "already_cached": True,
                        }),
                    )
                ]

        # Fetch metadata
        meta_resp = await client.get(
            f"{AGENT_DRIVE_URL}/v1/files/{file_id}", headers=_headers()
        )
        if meta_resp.status_code != 200:
            return [types.TextContent(type="text", text=meta_resp.text)]
        meta = meta_resp.json()

        # Stream download
        async with client.stream(
            "GET",
            f"{AGENT_DRIVE_URL}/v1/files/{file_id}/download",
            headers=_headers(),
        ) as dl_resp:
            if dl_resp.status_code != 200:
                text = await dl_resp.aread()
                return [types.TextContent(type="text", text=text.decode())]
            chunks = []
            async for chunk in dl_resp.aiter_bytes():
                chunks.append(chunk)

        # Save locally
        result = save_file(
            file_id,
            iter(chunks),
            {
                "filename": meta["filename"],
                "collection": meta.get("collection_name"),
                "file_size": meta["file_size"],
                "content_type": meta["content_type"],
                "remote_updated_at": meta.get("updated_at", ""),
            },
        )

        if should_open:
            open_native(Path(result["local_path"]))

        return [types.TextContent(type="text", text=json.dumps(result))]
```

Add `json` to imports at top if not already present.

**Known limitation:** The handler collects all streamed bytes into a list before writing to disk. This loads the full file into MCP process memory. Acceptable for typical file sizes (most files under 32MB), but a future optimization could stream directly to a temp file.

- [ ] **Step 3: Run existing MCP tests to confirm no regressions**

Run: `cd packages/mcp && uv run pytest tests/ -v`
Expected: All existing tests PASS

- [ ] **Step 4: Commit**

```bash
git add packages/mcp/src/agentdrive_mcp/server.py
git commit -m "feat(mcp): add download_file tool to standalone MCP server"
```

---

### Task 6: Add `download_file` tool to in-process MCP server

**Files:**
- Modify: `src/agentdrive/mcp/server.py:33-84` (add tool to list)
- Modify: `src/agentdrive/mcp/server.py:87-187` (add tool handler)

- [ ] **Step 1: Add `download_file` to tool list in `list_tools()`**

In `src/agentdrive/mcp/server.py`, add the same tool definition to the tools list (same schema as Task 5 Step 1).

- [ ] **Step 2: Add `download_file` handler in `call_tool()`**

In `src/agentdrive/mcp/server.py`, add the same `elif name == "download_file":` handler as Task 5 Step 2. The code is identical — both servers use HTTP via `httpx.AsyncClient`. Copy the full handler block from Task 5 Step 2 verbatim. Both servers share the same patterns: `AGENT_DRIVE_URL` for base URL, `_headers()` for auth, `client` as the httpx variable name, and `types.TextContent` for return values.

- [ ] **Step 3: Run MCP tests to confirm no regressions**

Run: `uv run pytest tests/mcp/ -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add src/agentdrive/mcp/server.py
git commit -m "feat(mcp): add download_file tool to in-process MCP server"
```

---

### Task 7: MCP tool handler tests

**Files:**
- Create: `packages/mcp/tests/test_download_tool.py`

- [ ] **Step 1: Write tests for download_file MCP tool handler**

Create `packages/mcp/tests/test_download_tool.py`:

```python
"""Tests for the download_file MCP tool handler logic."""

import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock


@pytest.fixture
def files_dir(tmp_path):
    return tmp_path / "files"


class TestDownloadToolFreshDownload:
    """Test fresh download (not cached)."""

    def test_save_file_creates_file_and_manifest(self, files_dir):
        from agentdrive_mcp.local_files import save_file, read_manifest

        content = b"fresh file content"
        result = save_file(
            "file-fresh",
            iter([content]),
            {
                "filename": "fresh.txt",
                "collection": "docs",
                "file_size": len(content),
                "content_type": "text/plain",
                "remote_updated_at": "2026-04-02T10:00:00Z",
            },
            files_dir,
        )
        assert result["already_cached"] is False
        assert Path(result["local_path"]).read_bytes() == content
        manifest = read_manifest(files_dir)
        assert "file-fresh" in manifest["files"]


class TestDownloadToolCachedHit:
    """Test cached file that is not stale."""

    def test_cached_fresh_file_returns_already_cached(self, files_dir):
        from agentdrive_mcp.local_files import (
            save_file,
            is_cached,
            is_stale,
            read_manifest,
            AGENTDRIVE_FILES_DIR,
        )

        # First download
        save_file(
            "file-cached",
            iter([b"content"]),
            {
                "filename": "cached.txt",
                "collection": None,
                "file_size": 7,
                "content_type": "text/plain",
                "remote_updated_at": "2026-04-01T08:00:00Z",
            },
            files_dir,
        )
        assert is_cached("file-cached", files_dir) is True
        # Same remote timestamp = not stale
        assert is_stale("file-cached", "2026-04-01T08:00:00Z", files_dir) is False


class TestDownloadToolStaleRedownload:
    """Test stale file triggers re-download and overwrites same path."""

    def test_stale_redownload_overwrites_existing_file(self, files_dir):
        from agentdrive_mcp.local_files import save_file, is_stale, read_manifest

        # Initial download
        save_file(
            "file-stale",
            iter([b"old content"]),
            {
                "filename": "stale.txt",
                "collection": "research",
                "file_size": 11,
                "content_type": "text/plain",
                "remote_updated_at": "2026-04-01T08:00:00Z",
            },
            files_dir,
        )
        assert is_stale("file-stale", "2026-04-02T12:00:00Z", files_dir) is True

        # Re-download with newer content
        result = save_file(
            "file-stale",
            iter([b"new content"]),
            {
                "filename": "stale.txt",
                "collection": "research",
                "file_size": 11,
                "content_type": "text/plain",
                "remote_updated_at": "2026-04-02T12:00:00Z",
            },
            files_dir,
        )
        # Should reuse same path, not create collision-suffixed path
        assert result["local_path"].endswith("research/stale.txt")
        assert Path(result["local_path"]).read_bytes() == b"new content"
        # Manifest updated with new timestamp
        manifest = read_manifest(files_dir)
        assert manifest["files"]["file-stale"]["remote_updated_at"] == "2026-04-02T12:00:00Z"


class TestDownloadToolOpenFlag:
    """Test open flag triggers native open."""

    @patch("agentdrive_mcp.local_files.subprocess.Popen")
    @patch("agentdrive_mcp.local_files.platform.system", return_value="Darwin")
    def test_open_flag_calls_native_open(self, mock_system, mock_popen, files_dir):
        from agentdrive_mcp.local_files import save_file, open_native

        result = save_file(
            "file-open",
            iter([b"open me"]),
            {
                "filename": "open.txt",
                "collection": None,
                "file_size": 7,
                "content_type": "text/plain",
                "remote_updated_at": "2026-04-02T10:00:00Z",
            },
            files_dir,
        )
        open_native(Path(result["local_path"]))
        mock_popen.assert_called_once()
        assert "open" in mock_popen.call_args[0][0]
```

- [ ] **Step 2: Run MCP tool tests**

Run: `cd packages/mcp && uv run pytest tests/test_download_tool.py -v`
Expected: All PASS

- [ ] **Step 3: Run full test suite**

Run: `uv run pytest tests/ -v && cd packages/mcp && uv run pytest tests/ -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add packages/mcp/tests/test_download_tool.py
git commit -m "test: add MCP download_file tool handler tests"
```
