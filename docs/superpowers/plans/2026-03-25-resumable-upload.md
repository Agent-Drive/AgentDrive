# Resumable Upload Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add signed URL upload flow for files >32MB, allowing clients to upload directly to GCS without file data flowing through the server.

**Architecture:** New two-step flow: (1) `POST /v1/files/upload-url` creates a File record with `status=uploading` and returns a GCS signed URL, (2) client uploads directly to GCS, (3) `POST /v1/files/{id}/complete` verifies the upload and enqueues for processing. Existing direct upload for ≤32MB is unchanged. MCP tool auto-selects the right path based on file size.

**Important: GCS V4 signed URLs require service account credentials.** The `blob.generate_signed_url(version="v4")` method requires a service account key (JSON file via `GOOGLE_APPLICATION_CREDENTIALS`), not user ADC from `gcloud auth application-default login`. Ensure the deployment environment has a service account key configured. In development, set `GOOGLE_APPLICATION_CREDENTIALS=/path/to/key.json`.

**Tech Stack:** Python 3.12, FastAPI, google-cloud-storage (signed URLs), Pydantic, pytest

**Spec:** `docs/superpowers/specs/2026-03-25-resumable-upload-design.md`

---

### Task 1: Add UPLOADING Status + Config

**Files:**
- Modify: `src/agentdrive/models/types.py`
- Modify: `src/agentdrive/config.py`
- Create: `tests/test_uploading_status.py`

- [ ] **Step 1: Write test**

```python
# tests/test_uploading_status.py
from agentdrive.models.types import FileStatus


def test_uploading_status_exists():
    assert FileStatus.UPLOADING == "uploading"
    assert FileStatus.UPLOADING in FileStatus.__members__.values()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_uploading_status.py -v`
Expected: FAIL

- [ ] **Step 3: Add UPLOADING to FileStatus**

Modify `src/agentdrive/models/types.py`:

```python
class FileStatus(str, enum.Enum):
    UPLOADING = "uploading"
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"
```

- [ ] **Step 4: Add config settings**

Add to `src/agentdrive/config.py`:

```python
    max_signed_upload_bytes: int = 5 * 1024 * 1024 * 1024  # 5GB
    signed_url_expiry_hours: int = 1
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_uploading_status.py -v && uv run pytest tests/ -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/agentdrive/models/types.py src/agentdrive/config.py tests/test_uploading_status.py
git commit -m "feat: add UPLOADING file status and signed upload config"
```

---

### Task 2: Signed URL Generation + Blob Helpers in StorageService

**Files:**
- Modify: `src/agentdrive/services/storage.py`
- Create: `tests/test_signed_url.py`

- [ ] **Step 1: Write tests**

```python
# tests/test_signed_url.py
import uuid
from unittest.mock import MagicMock, patch

from agentdrive.services.storage import StorageService


def test_generate_signed_upload_url():
    with patch("agentdrive.services.storage.storage_client") as mock_client:
        mock_bucket = MagicMock()
        mock_client.bucket.return_value = mock_bucket
        mock_blob = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_blob.generate_signed_url.return_value = "https://storage.googleapis.com/signed-url"

        service = StorageService()
        url = service.generate_signed_upload_url(
            uuid.uuid4(), uuid.uuid4(), "large.pdf", "application/pdf", expiry_hours=1
        )

        assert url == "https://storage.googleapis.com/signed-url"
        call_kwargs = mock_blob.generate_signed_url.call_args[1]
        assert call_kwargs["method"] == "PUT"
        assert call_kwargs["content_type"] == "application/pdf"


def test_blob_exists():
    with patch("agentdrive.services.storage.storage_client") as mock_client:
        mock_bucket = MagicMock()
        mock_client.bucket.return_value = mock_bucket
        mock_blob = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_blob.exists.return_value = True

        service = StorageService()
        assert service.blob_exists("tenants/x/files/y/test.pdf") is True
        mock_blob.exists.assert_called_once()


def test_get_blob_size():
    with patch("agentdrive.services.storage.storage_client") as mock_client:
        mock_bucket = MagicMock()
        mock_client.bucket.return_value = mock_bucket
        mock_blob = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_blob.size = 50_000_000

        service = StorageService()
        assert service.get_blob_size("some/path.pdf") == 50_000_000
        mock_blob.reload.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_signed_url.py -v`
Expected: FAIL

- [ ] **Step 3: Implement methods**

Add to `src/agentdrive/services/storage.py`:

```python
from datetime import timedelta
```

Add methods:

```python
    def generate_signed_upload_url(
        self, tenant_id: uuid.UUID, file_id: uuid.UUID, filename: str,
        content_type: str, expiry_hours: int = 1,
    ) -> str:
        """Generate a V4 signed URL for direct-to-GCS upload.

        Requires service account credentials (not user ADC).
        Set GOOGLE_APPLICATION_CREDENTIALS to a service account key JSON.
        """
        path = self.generate_path(tenant_id, file_id, filename)
        blob = self._bucket.blob(path)
        return blob.generate_signed_url(
            version="v4",
            expiration=timedelta(hours=expiry_hours),
            method="PUT",
            content_type=content_type,
        )

    def blob_exists(self, gcs_path: str) -> bool:
        """Check if a blob exists in GCS."""
        blob = self._bucket.blob(gcs_path)
        return blob.exists()

    def get_blob_size(self, gcs_path: str) -> int:
        """Get the size in bytes of a GCS blob."""
        blob = self._bucket.blob(gcs_path)
        blob.reload()
        return blob.size
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_signed_url.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/agentdrive/services/storage.py tests/test_signed_url.py
git commit -m "feat: add signed URL generation, blob existence, and size query"
```

---

### Task 3: Upload URL + Complete Endpoints

**Files:**
- Modify: `src/agentdrive/routers/files.py`
- Modify: `src/agentdrive/schemas/files.py`
- Create: `tests/test_signed_upload_endpoints.py`

- [ ] **Step 1: Add request/response schemas**

Add to `src/agentdrive/schemas/files.py`:

```python
class UploadUrlRequest(BaseModel):
    filename: str
    content_type: str = "application/octet-stream"
    file_size: int
    collection_id: uuid.UUID | None = None


class UploadUrlResponse(BaseModel):
    file_id: uuid.UUID
    upload_url: str
    expires_at: datetime
```

Note: `gcs_path` is NOT included in the response — it's an internal detail stored on the File record.

- [ ] **Step 2: Write tests**

```python
# tests/test_signed_upload_endpoints.py
import uuid
from unittest.mock import patch, MagicMock

import pytest
from httpx import AsyncClient

from agentdrive.models.file import File
from agentdrive.models.types import FileStatus
from sqlalchemy import select


@pytest.mark.asyncio
async def test_upload_url_creates_file_with_uploading_status(client: AsyncClient, db_session):
    with patch("agentdrive.routers.files.StorageService") as MockStorage:
        MockStorage.return_value.generate_signed_upload_url.return_value = "https://storage.googleapis.com/signed"
        MockStorage.return_value.generate_path.return_value = "tenants/x/files/y/large.pdf"

        response = await client.post("/v1/files/upload-url", json={
            "filename": "large.pdf",
            "content_type": "application/pdf",
            "file_size": 100_000_000,
        })

    assert response.status_code == 200
    data = response.json()
    assert data["upload_url"] == "https://storage.googleapis.com/signed"
    assert "file_id" in data
    assert "gcs_path" not in data  # Internal detail not exposed

    # Verify DB state
    result = await db_session.execute(select(File).where(File.id == uuid.UUID(data["file_id"])))
    file_record = result.scalar_one_or_none()
    assert file_record is not None
    assert file_record.status == FileStatus.UPLOADING


@pytest.mark.asyncio
async def test_upload_url_rejects_oversized_files(client: AsyncClient):
    response = await client.post("/v1/files/upload-url", json={
        "filename": "huge.pdf",
        "content_type": "application/pdf",
        "file_size": 10 * 1024 * 1024 * 1024,  # 10GB > 5GB limit
    })
    assert response.status_code == 413


@pytest.mark.asyncio
async def test_complete_upload_enqueues_file(client: AsyncClient, db_session):
    from agentdrive.models.tenant import Tenant

    result = await db_session.execute(select(Tenant))
    tenant = result.scalar_one_or_none()
    if not tenant:
        tenant = Tenant(name="test")
        db_session.add(tenant)
        await db_session.flush()

    file = File(
        tenant_id=tenant.id, filename="large.pdf", content_type="pdf",
        gcs_path="tenants/x/files/y/large.pdf", file_size=0,
        status=FileStatus.UPLOADING,
    )
    db_session.add(file)
    await db_session.commit()

    with patch("agentdrive.routers.files.StorageService") as MockStorage, \
         patch("agentdrive.routers.files.enqueue") as mock_enqueue:
        MockStorage.return_value.blob_exists.return_value = True
        MockStorage.return_value.get_blob_size.return_value = 100_000_000

        response = await client.post(f"/v1/files/{file.id}/complete")

    assert response.status_code == 200
    assert response.json()["status"] == "pending"
    mock_enqueue.assert_called_once_with(file.id)


@pytest.mark.asyncio
async def test_complete_upload_404_for_non_uploading(client: AsyncClient):
    response = await client.post(f"/v1/files/{uuid.uuid4()}/complete")
    assert response.status_code == 404
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_signed_upload_endpoints.py -v`
Expected: FAIL

- [ ] **Step 4: Implement endpoints**

Add imports to `src/agentdrive/routers/files.py`:

```python
from datetime import datetime, timedelta, timezone
from agentdrive.models.types import FileStatus
from agentdrive.schemas.files import UploadUrlRequest, UploadUrlResponse
```

Add these endpoints **BEFORE** the `get_file` route (above `@router.get("/{file_id}")`):

```python
@router.post("/upload-url", response_model=UploadUrlResponse)
async def create_upload_url(
    body: UploadUrlRequest,
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
):
    if body.file_size > settings.max_signed_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File size {body.file_size} exceeds {settings.max_signed_upload_bytes} byte limit",
        )

    file_id = uuid.uuid4()
    storage = StorageService()
    gcs_path = storage.generate_path(tenant.id, file_id, body.filename)
    content_type = detect_content_type(body.filename, body.content_type)

    upload_url = storage.generate_signed_upload_url(
        tenant.id, file_id, body.filename, body.content_type,
        expiry_hours=settings.signed_url_expiry_hours,
    )

    file_record = FileModel(
        id=file_id, tenant_id=tenant.id, collection_id=body.collection_id,
        filename=body.filename, content_type=content_type,
        gcs_path=gcs_path, file_size=body.file_size,
        status=FileStatus.UPLOADING,
    )
    session.add(file_record)
    await session.commit()

    expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.signed_url_expiry_hours)
    return UploadUrlResponse(file_id=file_id, upload_url=upload_url, expires_at=expires_at)


@router.post("/{file_id}/complete", response_model=FileUploadResponse)
async def complete_upload(
    file_id: uuid.UUID,
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(FileModel).where(
            FileModel.id == file_id,
            FileModel.tenant_id == tenant.id,
            FileModel.status == FileStatus.UPLOADING,
        )
    )
    file_record = result.scalar_one_or_none()
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found or not in uploading state")

    storage = StorageService()
    if not storage.blob_exists(file_record.gcs_path):
        raise HTTPException(status_code=400, detail="File not found in storage — upload may not be complete")

    actual_size = storage.get_blob_size(file_record.gcs_path)
    file_record.file_size = actual_size
    file_record.status = FileStatus.PENDING
    await session.commit()
    await session.refresh(file_record)

    enqueue(file_record.id)
    return FileUploadResponse.model_validate(file_record)
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_signed_upload_endpoints.py -v`
Expected: All PASS

- [ ] **Step 6: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add src/agentdrive/routers/files.py src/agentdrive/schemas/files.py \
  tests/test_signed_upload_endpoints.py
git commit -m "feat: add signed URL upload and completion endpoints"
```

---

### Task 4: Incomplete Upload Cleanup in Reaper

**Files:**
- Modify: `src/agentdrive/services/queue.py`
- Create: `tests/test_upload_reaper.py`

- [ ] **Step 1: Write tests**

```python
# tests/test_upload_reaper.py
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock
from sqlalchemy import select, text as sa_text

from agentdrive.models.file import File
from agentdrive.models.tenant import Tenant
from agentdrive.models.types import FileStatus
from agentdrive.services.queue import reap_stuck_files


@pytest.mark.asyncio
async def test_reaper_cleans_stale_uploading_files(db_session):
    tenant = Tenant(name="test")
    db_session.add(tenant)
    await db_session.flush()

    stale_file = File(
        tenant_id=tenant.id, filename="stale.pdf", content_type="pdf",
        gcs_path="tenants/x/files/stale/stale.pdf", file_size=0,
        status=FileStatus.UPLOADING,
    )
    db_session.add(stale_file)
    await db_session.commit()

    # Backdate to 25 hours ago
    await db_session.execute(sa_text(
        "UPDATE files SET created_at = :ts WHERE id = :fid"
    ), {"ts": datetime.now(timezone.utc) - timedelta(hours=25), "fid": stale_file.id})
    await db_session.commit()

    with patch("agentdrive.services.queue.StorageService") as MockStorage:
        instance = MockStorage.return_value
        instance.blob_exists.return_value = True
        instance.delete = MagicMock()

        await reap_stuck_files(db_session)

        # Verify GCS blob was deleted
        instance.delete.assert_called_once_with("tenants/x/files/stale/stale.pdf")

    # Verify DB record deleted
    result = await db_session.execute(select(File).where(File.id == stale_file.id))
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_reaper_keeps_fresh_uploading_files(db_session):
    tenant = Tenant(name="test")
    db_session.add(tenant)
    await db_session.flush()

    fresh_file = File(
        tenant_id=tenant.id, filename="fresh.pdf", content_type="pdf",
        gcs_path="tenants/x/files/fresh/fresh.pdf", file_size=0,
        status=FileStatus.UPLOADING,
    )
    db_session.add(fresh_file)
    await db_session.commit()

    await reap_stuck_files(db_session)

    result = await db_session.execute(select(File).where(File.id == fresh_file.id))
    assert result.scalar_one_or_none() is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_upload_reaper.py -v`
Expected: FAIL

- [ ] **Step 3: Extend reap_stuck_files**

Add to `src/agentdrive/services/queue.py`, inside `reap_stuck_files`, after the pending files enqueue block. Also update the docstring:

```python
async def reap_stuck_files(session: AsyncSession) -> list[UUID]:
    """Reset stuck PROCESSING files, enqueue PENDING files, clean up stale UPLOADING files.

    Returns list of file IDs that were enqueued.
    """
    # ... existing Step 1 and Step 2 ...

    # Step 3: Clean up stale UPLOADING files (>24 hours)
    from agentdrive.services.storage import StorageService

    upload_threshold = datetime.now(timezone.utc) - timedelta(hours=24)
    result = await session.execute(
        select(File).where(
            File.status == FileStatus.UPLOADING,
            File.created_at < upload_threshold,
        )
    )
    stale_uploads = result.scalars().all()
    if stale_uploads:
        storage = StorageService()
        for f in stale_uploads:
            logger.warning(f"Reaper: deleting stale uploading file {f.id} ({f.filename})")
            try:
                if storage.blob_exists(f.gcs_path):
                    storage.delete(f.gcs_path)
            except Exception:
                logger.exception(f"Failed to delete GCS blob for stale upload {f.id}")
            await session.delete(f)
        await session.commit()
        logger.info(f"Reaper: cleaned up {len(stale_uploads)} stale uploading files")

    return enqueued
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_upload_reaper.py -v`
Expected: All PASS

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/agentdrive/services/queue.py tests/test_upload_reaper.py
git commit -m "feat: extend reaper to clean up stale UPLOADING files"
```

---

### Task 5: Update MCP Tool for Large Files

**Files:**
- Modify: `src/agentdrive/mcp/server.py`
- Create: `tests/test_mcp_upload.py`

- [ ] **Step 1: Write test for size-based dispatch**

```python
# tests/test_mcp_upload.py
import json
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock

import pytest

from agentdrive.mcp.server import call_tool


@pytest.mark.asyncio
async def test_mcp_small_file_uses_direct_upload(tmp_path):
    small_file = tmp_path / "small.txt"
    small_file.write_text("hello" * 100)

    mock_response = MagicMock()
    mock_response.json.return_value = {"id": "abc", "status": "pending"}

    with patch("agentdrive.mcp.server.httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        MockClient.return_value.__aenter__.return_value = mock_client
        mock_client.post.return_value = mock_response

        await call_tool("upload_file", {"path": str(small_file)})
        # Direct upload: POST /v1/files
        mock_client.post.assert_called_once()
        assert mock_client.post.call_args[0][0] == "/v1/files"


@pytest.mark.asyncio
async def test_mcp_large_file_uses_signed_url(tmp_path):
    large_file = tmp_path / "large.pdf"
    large_file.write_bytes(b"\x00" * (33 * 1024 * 1024))

    mock_url_resp = MagicMock()
    mock_url_resp.json.return_value = {
        "file_id": "abc-123", "upload_url": "https://storage.googleapis.com/signed",
        "expires_at": "2026-03-25T12:00:00Z",
    }
    mock_url_resp.status_code = 200

    mock_put_resp = MagicMock()
    mock_put_resp.status_code = 200

    mock_complete_resp = MagicMock()
    mock_complete_resp.json.return_value = {"id": "abc-123", "status": "pending"}

    with patch("agentdrive.mcp.server.httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        MockClient.return_value.__aenter__.return_value = mock_client
        mock_client.post.side_effect = [mock_url_resp, mock_complete_resp]
        mock_client.put.return_value = mock_put_resp

        await call_tool("upload_file", {"path": str(large_file)})

        assert mock_client.post.call_count == 2
        assert mock_client.put.call_count == 1
        # Verify the PUT used the signed URL
        put_args = mock_client.put.call_args
        assert put_args[0][0] == "https://storage.googleapis.com/signed"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_mcp_upload.py -v`
Expected: FAIL

- [ ] **Step 3: Update MCP upload_file tool**

Modify the `upload_file` handler in `src/agentdrive/mcp/server.py`. Key change: use `content=f` (file object) instead of `content=f.read()` for streaming, and increase timeout for large uploads:

```python
        if name == "upload_file":
            file_path = Path(arguments["path"])
            if not file_path.exists():
                return [TextContent(type="text", text=f"Error: File not found: {file_path}")]

            file_size = file_path.stat().st_size
            data = {}
            if "collection" in arguments:
                data["collection"] = arguments["collection"]

            if file_size <= 32 * 1024 * 1024:
                # Direct upload for small files
                with open(file_path, "rb") as f:
                    files = {"file": (file_path.name, f, "application/octet-stream")}
                    response = await client.post("/v1/files", files=files, data=data)
                return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
            else:
                # Signed URL flow for large files
                url_body = {
                    "filename": file_path.name,
                    "content_type": "application/octet-stream",
                    "file_size": file_size,
                }
                if "collection" in arguments:
                    url_body["collection_id"] = arguments["collection"]

                url_response = await client.post("/v1/files/upload-url", json=url_body)
                if url_response.status_code != 200:
                    return [TextContent(type="text", text=f"Error requesting upload URL: {url_response.text}")]

                url_data = url_response.json()
                upload_url = url_data["upload_url"]
                file_id = url_data["file_id"]

                # Stream upload directly to GCS (no full file in memory)
                with open(file_path, "rb") as f:
                    put_response = await client.put(
                        upload_url, content=f,  # Streams file, does NOT load into memory
                        headers={"Content-Type": "application/octet-stream"},
                        timeout=3600.0,  # 1 hour for large uploads
                    )
                if put_response.status_code not in (200, 201):
                    return [TextContent(type="text", text=f"Error uploading to GCS: {put_response.status_code}")]

                # Complete the upload
                complete_response = await client.post(f"/v1/files/{file_id}/complete")
                return [TextContent(type="text", text=json.dumps(complete_response.json(), indent=2))]
```

**Note on `collection_id`:** The MCP tool's `collection` argument may be a collection name or UUID depending on the caller. The `UploadUrlRequest` schema expects `collection_id` as a UUID. The MCP tool should pass whatever the user provides — if it's a name, the endpoint will return a validation error. This matches the existing direct upload which also takes `collection` as a UUID Form field.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_mcp_upload.py -v`
Expected: All PASS

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/agentdrive/mcp/server.py tests/test_mcp_upload.py
git commit -m "feat: update MCP upload tool to use signed URLs for large files"
```

---

### Task 6: Integration Test + Regression Verification

**Files:**
- Create: `tests/test_integration_upload.py`

- [ ] **Step 1: Write regression test for direct upload**

```python
# tests/test_integration_upload.py
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_direct_upload_still_works(client: AsyncClient):
    response = await client.post(
        "/v1/files",
        files={"file": ("test.txt", b"hello world", "text/plain")},
    )
    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "pending"
    assert data["filename"] == "test.txt"


@pytest.mark.asyncio
async def test_direct_upload_rejects_oversized(client: AsyncClient):
    big_data = b"\x00" * (33 * 1024 * 1024)
    response = await client.post(
        "/v1/files",
        files={"file": ("big.bin", big_data, "application/octet-stream")},
    )
    assert response.status_code == 413
```

- [ ] **Step 2: Run all tests**

Run: `uv run pytest tests/ -v`
Expected: All PASS

- [ ] **Step 3: Lint check**

Run: `uv run ruff check src/agentdrive/ --select F401,F841`
Expected: Clean

- [ ] **Step 4: Commit**

```bash
git add tests/test_integration_upload.py
git commit -m "test: integration tests for upload flow regression"
```
