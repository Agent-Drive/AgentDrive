# Remove Collections — Search-Only Architecture

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the collections system entirely so files are uploaded with zero organizational metadata and retrieved exclusively via search.

**Architecture:** Drop the `collections` table and `collection_id` FK from `files`. Remove all collection-related API endpoints, MCP tools, and search filters. Flatten local file cache to a single directory keyed by file ID.

**Tech Stack:** Python, FastAPI, SQLAlchemy, Alembic, Pydantic, MCP SDK, pytest

**Spec:** `docs/superpowers/specs/2026-04-02-remove-collections-search-only-design.md`

---

### Task 1: Alembic Migration — Drop Collections

**Files:**
- Create: `alembic/versions/006_drop_collections.py`

- [ ] **Step 1: Create the migration file**

```python
"""Drop collections table and collection_id from files."""
from alembic import op

revision: str = "006"
down_revision: str = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("idx_files_collection", table_name="files")
    op.drop_constraint("files_collection_id_fkey", table_name="files", type_="foreignkey")
    op.drop_column("files", "collection_id")
    op.drop_index("idx_collections_tenant", table_name="collections")
    op.drop_table("collections")


def downgrade() -> None:
    raise NotImplementedError("No downgrade — collections are permanently removed")
```

- [ ] **Step 2: Verify migration syntax**

Run: `cd /Users/rafey/Development/Rafey/AgentDrive && uv run python -c "import alembic.versions" 2>&1 || echo "OK - just checking syntax"`

The migration won't run until we have a live DB — we'll validate it later.

- [ ] **Step 3: Commit**

```bash
git add alembic/versions/006_drop_collections.py
git commit -m "feat: add migration to drop collections table and collection_id"
```

---

### Task 2: Remove Collection Model and Update File + Tenant Models

**Files:**
- Delete: `src/agentdrive/models/collection.py`
- Modify: `src/agentdrive/models/__init__.py`
- Modify: `src/agentdrive/models/file.py:12,25` — remove `collection_id` and `collection` relationship
- Modify: `src/agentdrive/models/tenant.py:14` — remove `collections` relationship

- [ ] **Step 1: Delete collection model**

```bash
rm src/agentdrive/models/collection.py
```

- [ ] **Step 2: Update `src/agentdrive/models/__init__.py`**

Remove the Collection import and export. The file should become:

```python
from agentdrive.models.api_key import ApiKey
from agentdrive.models.base import Base
from agentdrive.models.chunk import Chunk, ParentChunk
from agentdrive.models.chunk_alias import ChunkAlias
from agentdrive.models.file import File
from agentdrive.models.file_batch import FileBatch
from agentdrive.models.file_summary import FileSummary
from agentdrive.models.tenant import Tenant
from agentdrive.models.types import BatchStatus, ContentType, FileStatus

__all__ = [
    "ApiKey",
    "Base",
    "BatchStatus",
    "Chunk",
    "ChunkAlias",
    "ContentType",
    "File",
    "FileBatch",
    "FileSummary",
    "FileStatus",
    "ParentChunk",
    "Tenant",
]
```

- [ ] **Step 3: Update `src/agentdrive/models/file.py`**

Remove line 12 (`collection_id`) and line 25 (`collection` relationship). The file should become:

```python
import uuid
from sqlalchemy import BigInteger, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from agentdrive.models.base import Base, TimestampMixin, UUIDPrimaryKey
from agentdrive.models.types import FileStatus


class File(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "files"
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(Text, nullable=False)
    gcs_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default=FileStatus.PENDING)
    extra_metadata: Mapped[dict] = mapped_column("metadata", JSONB, server_default="{}")
    total_batches: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    completed_batches: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    current_phase: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    tenant = relationship("Tenant", back_populates="files")
    chunks = relationship("Chunk", back_populates="file", cascade="all, delete-orphan")
    parent_chunks = relationship("ParentChunk", back_populates="file", cascade="all, delete-orphan")
    batches = relationship("FileBatch", back_populates="file", cascade="all, delete-orphan")
    summary = relationship("FileSummary", back_populates="file", uselist=False, cascade="all, delete-orphan")
```

- [ ] **Step 4: Update `src/agentdrive/models/tenant.py`**

Remove line 14 (`collections` relationship). The file should become:

```python
from sqlalchemy import Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from agentdrive.models.base import Base, TimestampMixin, UUIDPrimaryKey


class Tenant(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "tenants"
    name: Mapped[str] = mapped_column(Text, nullable=False)
    workos_user_id: Mapped[str | None] = mapped_column(Text, unique=True)
    settings: Mapped[dict] = mapped_column(JSONB, server_default="{}")

    files = relationship("File", back_populates="tenant")
    api_keys = relationship("ApiKey", back_populates="tenant")
```

- [ ] **Step 5: Commit**

```bash
git add -u src/agentdrive/models/
git commit -m "refactor: remove Collection model, drop collection_id from File and Tenant"
```

---

### Task 3: Remove Collection Schemas and Update File/Search Schemas

**Files:**
- Delete: `src/agentdrive/schemas/collections.py`
- Modify: `src/agentdrive/schemas/files.py:10,34,38` — remove collection fields
- Modify: `src/agentdrive/schemas/search.py:1,8` — remove collections param

- [ ] **Step 1: Delete collection schemas**

```bash
rm src/agentdrive/schemas/collections.py
```

- [ ] **Step 2: Update `src/agentdrive/schemas/files.py`**

Remove `collection_id` from `UploadUrlRequest` (line 10), `collection_id` and `collection_name` from `FileDetailResponse` (lines 34, 38). The file should become:

```python
import uuid
from datetime import datetime
from pydantic import BaseModel, Field


class UploadUrlRequest(BaseModel):
    filename: str
    content_type: str = "application/octet-stream"
    file_size: int


class UploadUrlResponse(BaseModel):
    file_id: uuid.UUID
    upload_url: str
    expires_at: datetime


class FileUploadResponse(BaseModel):
    id: uuid.UUID
    filename: str
    content_type: str
    file_size: int
    status: str
    model_config = {"from_attributes": True}


class FileDetailResponse(BaseModel):
    id: uuid.UUID
    filename: str
    content_type: str
    file_size: int
    status: str
    metadata: dict = Field(validation_alias="extra_metadata")
    created_at: datetime
    updated_at: datetime
    chunk_count: int | None = None
    total_batches: int = 0
    completed_batches: int = 0
    current_phase: str | None = None
    model_config = {"from_attributes": True, "populate_by_name": True}


class FileListResponse(BaseModel):
    files: list[FileDetailResponse]
    total: int
```

Note: Keep `import uuid` at the top since `UploadUrlResponse` and other models use it.

- [ ] **Step 3: Update `src/agentdrive/schemas/search.py`**

Remove `uuid` import and `collections` field. The file should become:

```python
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
```

- [ ] **Step 4: Commit**

```bash
git add -u src/agentdrive/schemas/
git commit -m "refactor: remove collection fields from file and search schemas"
```

---

### Task 4: Remove Collections Router and Update Files/Search Routers

**Files:**
- Delete: `src/agentdrive/routers/collections.py`
- Modify: `src/agentdrive/main.py:9,31` — remove collections import and router
- Modify: `src/agentdrive/routers/files.py:29,41,73,125,132,171,175-177,184` — remove collection references
- Modify: `src/agentdrive/routers/search.py:36` — remove collections param

- [ ] **Step 1: Delete collections router**

```bash
rm src/agentdrive/routers/collections.py
```

- [ ] **Step 2: Update `src/agentdrive/main.py`**

Remove `collections` from the import on line 9, and remove `app.include_router(collections.router)` on line 31. The file should become:

```python
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse

from agentdrive.config import settings
from agentdrive.db.session import async_session_factory
from agentdrive.routers import api_keys, auth, files, search
from agentdrive.services.queue import reap_stuck_files, start_workers, stop_workers


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with async_session_factory() as session:
        await reap_stuck_files(session)
    start_workers()
    yield
    await stop_workers()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Agent Drive",
        version="0.1.0",
        description="Agent-native file intelligence layer",
        lifespan=lifespan,
    )
    app.include_router(api_keys.router)
    app.include_router(auth.router)
    app.include_router(files.router)
    app.include_router(search.router)

    @app.get("/health")
    async def health():
        return {"status": "ok", "environment": settings.environment}

    @app.get("/install.sh", response_class=PlainTextResponse)
    async def install_script():
        script_path = Path("scripts/install.sh")
        if not script_path.is_file():
            script_path = Path(__file__).resolve().parent.parent.parent / "scripts" / "install.sh"
        if not script_path.is_file():
            return PlainTextResponse("install script not found", status_code=404)
        return PlainTextResponse(script_path.read_text())

    return app


app = create_app()
```

- [ ] **Step 3: Update `src/agentdrive/routers/files.py`**

Remove: `collection` form param from `upload_file` (line 29), `collection_id=collection` from FileModel creation (line 41), `collection_id=body.collection_id` from large upload (line 73), `selectinload(FileModel.collection)` from `get_file` (line 125), `collection_name` assignment (line 132), `collection` param from `list_files` (line 171), collection filter logic (lines 175-177), and `collection_name` assignment in list (line 184).

The full updated file:

```python
import uuid
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from urllib.parse import quote
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from agentdrive.config import settings
from agentdrive.db.session import get_session
from agentdrive.dependencies import get_current_tenant
from agentdrive.models.file import File as FileModel
from agentdrive.models.tenant import Tenant
from agentdrive.models.types import FileStatus
from agentdrive.schemas.files import (
    FileDetailResponse, FileListResponse, FileUploadResponse,
    UploadUrlRequest, UploadUrlResponse,
)
from agentdrive.services.file_type import detect_content_type
from agentdrive.services.queue import enqueue
from agentdrive.services.storage import StorageService

router = APIRouter(prefix="/v1/files", tags=["files"])


@router.post("", status_code=202, response_model=FileUploadResponse)
async def upload_file(
    file: UploadFile = File(...),
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
):
    data = await file.read()
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="File exceeds 32MB limit")
    content_type = detect_content_type(file.filename or "unknown", file.content_type)
    file_id = uuid.uuid4()
    storage = StorageService()
    gcs_path = storage.upload(tenant.id, file_id, file.filename or "unknown", data, file.content_type or "")
    file_record = FileModel(
        id=file_id, tenant_id=tenant.id,
        filename=file.filename or "unknown", content_type=content_type,
        gcs_path=gcs_path, file_size=len(data), status="pending",
    )
    session.add(file_record)
    await session.commit()
    await session.refresh(file_record)

    enqueue(file_record.id)
    return FileUploadResponse.model_validate(file_record)


@router.post("/upload-url", status_code=201, response_model=UploadUrlResponse)
async def create_upload_url(
    body: UploadUrlRequest,
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
):
    if body.file_size > settings.max_signed_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds {settings.max_signed_upload_bytes} byte limit",
        )
    file_id = uuid.uuid4()
    storage = StorageService()
    gcs_path = storage.generate_path(tenant.id, file_id, body.filename)
    upload_url = storage.generate_signed_upload_url(
        tenant.id, file_id, body.filename,
        content_type=body.content_type,
        expiry_hours=settings.signed_url_expiry_hours,
    )
    file_record = FileModel(
        id=file_id, tenant_id=tenant.id,
        filename=body.filename, content_type=body.content_type,
        gcs_path=gcs_path, file_size=body.file_size,
        status=FileStatus.UPLOADING,
    )
    session.add(file_record)
    await session.commit()
    await session.refresh(file_record)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.signed_url_expiry_hours)
    return UploadUrlResponse(
        file_id=file_record.id,
        upload_url=upload_url,
        expires_at=expires_at,
    )


@router.post("/{file_id}/complete", status_code=200, response_model=FileUploadResponse)
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
        raise HTTPException(status_code=400, detail="Upload not found in storage")
    actual_size = storage.get_blob_size(file_record.gcs_path)
    file_record.file_size = actual_size
    file_record.status = FileStatus.PENDING
    await session.commit()
    await session.refresh(file_record)
    enqueue(file_record.id)
    return FileUploadResponse.model_validate(file_record)


@router.get("/{file_id}", response_model=FileDetailResponse)
async def get_file(
    file_id: uuid.UUID,
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(FileModel)
        .where(FileModel.id == file_id, FileModel.tenant_id == tenant.id)
    )
    file_record = result.scalar_one_or_none()
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")
    return FileDetailResponse.model_validate(file_record)


@router.get("/{file_id}/download")
async def download_file(
    file_id: uuid.UUID,
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(FileModel).where(FileModel.id == file_id, FileModel.tenant_id == tenant.id)
    )
    file_record = result.scalar_one_or_none()
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")

    storage = StorageService()
    try:
        stream = storage.download_stream(file_record.gcs_path)
    except FileNotFoundError:
        raise HTTPException(status_code=502, detail="File blob not found in storage")

    safe_filename = file_record.filename.replace('"', '_')
    headers = {
        "Content-Disposition": f"attachment; filename=\"{safe_filename}\"; filename*=UTF-8''{quote(file_record.filename)}",
    }
    if file_record.file_size:
        headers["Content-Length"] = str(file_record.file_size)

    return StreamingResponse(
        stream,
        media_type=file_record.content_type,
        headers=headers,
    )


@router.get("", response_model=FileListResponse)
async def list_files(
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
):
    query = select(FileModel).where(FileModel.tenant_id == tenant.id)
    query = query.order_by(FileModel.created_at.desc())
    result = await session.execute(query)
    files = result.scalars().all()
    responses = [FileDetailResponse.model_validate(f) for f in files]
    return FileListResponse(
        files=responses,
        total=len(files),
    )


@router.delete("/{file_id}", status_code=204)
async def delete_file(
    file_id: uuid.UUID,
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(FileModel).where(FileModel.id == file_id, FileModel.tenant_id == tenant.id)
    )
    file_record = result.scalar_one_or_none()
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")
    storage = StorageService()
    storage.delete(file_record.gcs_path)
    await session.delete(file_record)
    await session.commit()
```

- [ ] **Step 4: Update `src/agentdrive/routers/search.py`**

Remove `collections=body.collections` from the engine.search call on line 36. Change line 36 to:

```python
    results = await engine.search(
        query=body.query, session=session, tenant_id=tenant.id,
        top_k=body.top_k,
        content_types=body.content_types, include_parent=body.include_parent,
    )
```

- [ ] **Step 5: Commit**

```bash
git add -u src/agentdrive/routers/ src/agentdrive/main.py
git commit -m "refactor: remove collections router, strip collection params from files and search"
```

---

### Task 5: Remove Collection Filters from Search Engine

**Files:**
- Modify: `src/agentdrive/search/engine.py:21,32,34` — remove collections param
- Modify: `src/agentdrive/search/vector.py:23,31-33` — remove collections param and filter
- Modify: `src/agentdrive/search/bm25.py:19,28-30` — remove collections param and filter

- [ ] **Step 1: Update `src/agentdrive/search/engine.py`**

Remove `collections` parameter and its usage. Lines 15-34 should become:

```python
    async def search(
        self,
        query: str,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        top_k: int = 5,
        content_types: list[str] | None = None,
        include_parent: bool = True,
    ) -> list[dict]:
        # Step 1: Embed query
        query_vector_full = self._embedding_client.embed_query(query)
        query_vector_256 = self._embedding_client.truncate(query_vector_full, 256)

        # Step 2: Parallel retrieval
        vector_results = await vector_search(
            query_vector_256, session, tenant_id, top_k=50,
            content_types=content_types,
        )
        bm25_results = await bm25_search(query, session, tenant_id, top_k=50)
```

- [ ] **Step 2: Update `src/agentdrive/search/vector.py`**

Remove `collections` parameter and the collection filter WHERE clause. Lines 18-33 should become:

```python
async def vector_search(
    query_embedding: list[float],
    session: AsyncSession,
    tenant_id: uuid.UUID,
    top_k: int = 50,
    content_types: list[str] | None = None,
) -> list[SearchResult]:
    embedding_str = "[" + ",".join(str(v) for v in query_embedding) + "]"

    where_clauses = ["f.tenant_id = :tenant_id", "f.status = 'ready'"]
    params: dict = {"tenant_id": str(tenant_id), "embedding": embedding_str, "top_k": top_k}

    if content_types:
        where_clauses.append("c.content_type = ANY(:content_types)")
        params["content_types"] = content_types
```

- [ ] **Step 3: Update `src/agentdrive/search/bm25.py`**

Remove `collections` parameter and the collection filter WHERE clause. Lines 14-30 should become:

```python
async def bm25_search(
    query: str,
    session: AsyncSession,
    tenant_id: uuid.UUID,
    top_k: int = 50,
) -> list[SearchResult]:
    where_clauses = [
        "f.tenant_id = :tenant_id",
        "f.status = 'ready'",
        "to_tsvector('english', c.content) @@ plainto_tsquery('english', :query)",
    ]
    params: dict = {"tenant_id": str(tenant_id), "query": query, "top_k": top_k}
```

- [ ] **Step 4: Commit**

```bash
git add -u src/agentdrive/search/
git commit -m "refactor: remove collection filters from vector and BM25 search"
```

---

### Task 6: Update Backend MCP Server

**Files:**
- Modify: `src/agentdrive/mcp/server.py` — remove 3 collection tools, strip collection from upload/search/list

- [ ] **Step 1: Update `src/agentdrive/mcp/server.py`**

In `list_tools()`: remove the `collection` property from `upload_file` (line 39), `search` (line 45), and `list_files` (line 53). Remove the `create_collection` tool (lines 55-59), `list_collections` tool (lines 60-61), and `delete_collection` tool (lines 66-69). Tool count goes from 13 to 10.

In `call_tool()`: remove collection data handling from `upload_file` (lines 115-117), `search` (lines 157-158), and `list_files` (lines 165-167). Remove the `create_collection` handler (lines 170-175), `list_collections` handler (lines 176-178), and `delete_collection` handler (lines 184-188). In the `download_file` handler, remove `"collection": entry["collection"]` from the cached response (line 222) and `"collection": meta.get("collection_name")` from the save_file metadata (line 250).

The full tool list should be (10 tools):
- `upload_file` (path only)
- `search` (query, top_k)
- `get_file_status`
- `list_files` (no params)
- `delete_file`
- `get_chunk`
- `download_file`
- `create_api_key`
- `list_api_keys`
- `revoke_api_key`

- [ ] **Step 2: Commit**

```bash
git add src/agentdrive/mcp/server.py
git commit -m "refactor: remove collection tools and params from backend MCP server"
```

---

### Task 7: Update MCP Package Server

**Files:**
- Modify: `packages/mcp/src/agentdrive_mcp/server.py` — same changes as backend MCP server

- [ ] **Step 1: Update `packages/mcp/src/agentdrive_mcp/server.py`**

Apply identical changes as Task 6:

In `list_tools()`: remove `collection` property from `upload_file` (line 48), `search` (line 54), `list_files` (line 62). Remove `create_collection` tool (lines 64-68), `list_collections` tool (lines 69-70), `delete_collection` tool (lines 75-78). Tool count: 13 → 10.

In `call_tool()`: remove collection handling from `upload_file` (lines 124-126), `search` (lines 131-132), `list_files` (lines 139-141). Remove `create_collection` handler (lines 144-149), `list_collections` handler (lines 150-152), `delete_collection` handler (lines 158-162). In `download_file` handler, remove `"collection": entry["collection"]` from cached response (line 196) and `"collection": meta.get("collection_name")` from save_file metadata (line 224).

- [ ] **Step 2: Commit**

```bash
git add packages/mcp/src/agentdrive_mcp/server.py
git commit -m "refactor: remove collection tools and params from MCP package server"
```

---

### Task 8: Flatten Local File Cache

**Files:**
- Modify: `packages/mcp/src/agentdrive_mcp/local_files.py` — flatten path resolution, remove collection from manifest/results

- [ ] **Step 1: Update `resolve_local_path`**

Replace the function at lines 56-70 with a flat path scheme:

```python
def resolve_local_path(
    filename: str,
    file_id: str,
    files_dir: Path = AGENTDRIVE_FILES_DIR,
) -> Path:
    """Build local path: {file_id_short}_{filename}. No subdirectories."""
    short_id = file_id[:8]
    target = files_dir / f"{short_id}_{filename}"
    return target
```

- [ ] **Step 2: Update `save_file`**

Remove `collection` from metadata reading and result dict. Update `resolve_local_path` call to drop collection param. Lines 110-164 should become:

```python
def save_file(
    file_id: str,
    byte_stream: Iterator[bytes],
    metadata: dict,
    files_dir: Path = AGENTDRIVE_FILES_DIR,
) -> dict:
    """Write streamed bytes to local path and update manifest. Returns result dict."""
    filename = metadata["filename"]
    file_size = metadata.get("file_size", 0)
    content_type = metadata.get("content_type", "")
    remote_updated_at = metadata.get("remote_updated_at", "")

    # Check manifest first for existing path (re-download case)
    manifest = read_manifest(files_dir)
    existing = manifest.get("files", {}).get(file_id)
    if existing:
        local_path = files_dir / existing["local_path"]
    else:
        local_path = resolve_local_path(filename, file_id, files_dir)

    # Ensure parent directory exists
    local_path.parent.mkdir(parents=True, exist_ok=True)

    # Atomic write: temp file + rename
    fd, tmp_path_str = tempfile.mkstemp(dir=local_path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            for chunk in byte_stream:
                f.write(chunk)
        Path(tmp_path_str).replace(local_path)
    except Exception:
        Path(tmp_path_str).unlink(missing_ok=True)
        raise

    # Relative path for manifest (relative to files_dir)
    relative_path = str(local_path.relative_to(files_dir))

    # Update manifest
    manifest["files"][file_id] = {
        "local_path": relative_path,
        "filename": filename,
        "remote_updated_at": remote_updated_at,
        "content_type": content_type,
        "file_size": file_size,
    }
    write_manifest(manifest, files_dir)

    return {
        "local_path": str(local_path),
        "filename": filename,
        "file_size": file_size,
        "already_cached": False,
    }
```

- [ ] **Step 3: Commit**

```bash
git add packages/mcp/src/agentdrive_mcp/local_files.py
git commit -m "refactor: flatten local file cache, remove collection from paths and manifest"
```

---

### Task 9: Update Tests — Delete Collection Tests and Fix References

**Files:**
- Delete: `tests/test_collections.py`
- Modify: `tests/test_files.py:117-138` — remove `test_get_file_includes_collection_name`
- Modify: `tests/test_prefix_auth.py:39,45,57,63` — replace `/v1/collections` with `/v1/files`
- Modify: `tests/test_schema_progress.py:13,34` — remove `collection_id` from test data
- Modify: `tests/mcp/test_server.py:22-23,25,31` — remove collection tool assertions, update count

- [ ] **Step 1: Delete collection tests**

```bash
rm tests/test_collections.py
```

- [ ] **Step 2: Update `tests/test_files.py`**

Remove the entire `test_get_file_includes_collection_name` test (lines 115-138). This test creates a Collection, uploads a file to it, and asserts `collection_name` in the response — all of which no longer exist.

- [ ] **Step 3: Update `tests/test_prefix_auth.py`**

Replace all `/v1/collections` with `/v1/files` in the 4 test functions. The endpoint is just used to test auth — any authenticated endpoint works:

Line 39: `response = await client.get("/v1/files", headers={"Authorization": f"Bearer {raw_key}"})`
Line 45: `response = await client.get("/v1/files", headers={"Authorization": f"Bearer {LEGACY_KEY}"})`
Line 57: `response = await client.get("/v1/files", headers={"Authorization": f"Bearer {raw_key}"})`
Line 63: `response = await client.get("/v1/files", headers={"Authorization": "Bearer sk-ad-totally-fake-key-abc123"})`

- [ ] **Step 4: Update `tests/test_schema_progress.py`**

Remove `"collection_id": None` from both test data dicts (lines 13 and 34). The field no longer exists on `FileDetailResponse`.

- [ ] **Step 5: Update `tests/mcp/test_server.py`**

Remove assertions for `create_collection`, `list_collections`, and `delete_collection` (lines 22-23, 25). Update tool count from 13 to 10 (line 31):

```python
@pytest.mark.asyncio
async def test_list_tools():
    tools = await _list_tools()
    tool_names = [t.name for t in tools]
    assert "upload_file" in tool_names
    assert "search" in tool_names
    assert "get_file_status" in tool_names
    assert "list_files" in tool_names
    assert "delete_file" in tool_names
    assert "get_chunk" in tool_names
    assert "create_api_key" in tool_names
    assert "list_api_keys" in tool_names
    assert "revoke_api_key" in tool_names
    assert "download_file" in tool_names
    assert len(tool_names) == 10
```

- [ ] **Step 6: Commit**

```bash
git add -u tests/
git commit -m "test: remove collection tests, update auth and schema tests"
```

---

### Task 10: Update MCP Package Tests

**Files:**
- Modify: `packages/mcp/tests/test_local_files.py` — update path resolution and save_file tests
- Modify: `packages/mcp/tests/test_download_tool.py` — remove collection from metadata

- [ ] **Step 1: Update `packages/mcp/tests/test_local_files.py`**

**TestPathResolution** (lines 50-66): Update to flat path scheme without collection:

```python
class TestPathResolution:
    def test_resolve_path_flat(self, tmp_path: Path) -> None:
        path = resolve_local_path("report.pdf", "abcd1234", tmp_path)
        assert path == tmp_path / "abcd1234_report.pdf"

    def test_resolve_path_different_ids(self, tmp_path: Path) -> None:
        path1 = resolve_local_path("report.pdf", "abcd1234", tmp_path)
        path2 = resolve_local_path("report.pdf", "efgh5678", tmp_path)
        assert path1 != path2
        assert path1 == tmp_path / "abcd1234_report.pdf"
        assert path2 == tmp_path / "efgh5678_report.pdf"
```

**TestSaveFile** (lines 116-167): Remove `"collection"` key from all metadata dicts and result assertions:

```python
class TestSaveFile:
    def test_save_file_writes_bytes_and_updates_manifest(self, tmp_path: Path) -> None:
        content = b"hello world"
        byte_stream = iter([content])
        metadata = {
            "filename": "notes.txt",
            "file_size": 11,
            "content_type": "text/plain",
            "remote_updated_at": "2025-03-28T12:00:00Z",
        }

        result = save_file("file-abc", byte_stream, metadata, tmp_path)

        # File written to disk
        local_path = Path(result["local_path"])
        assert local_path.exists()
        assert local_path.read_bytes() == content

        # Manifest updated
        manifest = read_manifest(tmp_path)
        assert "file-abc" in manifest["files"]

        # Result dict has expected keys
        assert result["local_path"] == str(local_path)
        assert result["filename"] == "notes.txt"
        assert result["file_size"] == 11
        assert result["already_cached"] is False

    def test_save_file_redownload_reuses_path(self, tmp_path: Path) -> None:
        # First download
        result1 = save_file("file-redownload", iter([b"old content"]), {
            "filename": "reuse.txt",
            "file_size": 11, "content_type": "text/plain",
            "remote_updated_at": "2026-04-01T08:00:00Z",
        }, tmp_path)

        # Re-download same file_id with new content
        result2 = save_file("file-redownload", iter([b"new content"]), {
            "filename": "reuse.txt",
            "file_size": 11, "content_type": "text/plain",
            "remote_updated_at": "2026-04-02T12:00:00Z",
        }, tmp_path)

        # Same path, not collision-suffixed
        assert result1["local_path"] == result2["local_path"]
        # Content overwritten
        assert Path(result2["local_path"]).read_bytes() == b"new content"
        # Manifest updated
        manifest = read_manifest(tmp_path)
        assert manifest["files"]["file-redownload"]["remote_updated_at"] == "2026-04-02T12:00:00Z"
```

- [ ] **Step 2: Update `packages/mcp/tests/test_download_tool.py`**

Remove `"collection"` key from all metadata dicts in save_file calls. Also update the stale test path assertion (line 109) from `"research/stale.txt"` to `"file-stale_stale.txt"` (flat path):

Lines 36-37: `"collection": "docs"` → remove
Line 63: `"collection": None` → remove
Lines 87-88: `"collection": "research"` → remove
Lines 102-103: `"collection": "research"` → remove
Line 109: `assert result["local_path"].endswith("research/stale.txt")` → `assert "file-stale" in result["local_path"]`
Line 131: `"collection": None` → remove

- [ ] **Step 3: Commit**

```bash
git add -u packages/mcp/tests/
git commit -m "test: update MCP package tests for flat file cache without collections"
```

---

### Task 11: Run All Tests and Fix Issues

- [ ] **Step 1: Run backend tests**

```bash
cd /Users/rafey/Development/Rafey/AgentDrive && uv run pytest tests/ -v
```

Expected: All tests pass. If any fail, fix them before proceeding.

- [ ] **Step 2: Run MCP package tests**

```bash
cd /Users/rafey/Development/Rafey/AgentDrive/packages/mcp && uv run pytest tests/ -v
```

Expected: All tests pass.

- [ ] **Step 3: Commit any fixes**

```bash
git add -u && git commit -m "fix: resolve test failures from collection removal"
```

---

### Task 12: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update architecture diagram**

In the Architecture section, remove `collections` from the routers and models descriptions. Update the `routers/` line to:

```
├── routers/             # REST endpoints (files, search)
```

Update the `models/` line to:

```
├── models/              # SQLAlchemy models (tenant, file, chunk, chunk_alias)
```

- [ ] **Step 2: Remove collection-related gotchas if any**

Scan the Gotchas section — no collection-specific gotchas exist currently, but verify.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md architecture after collection removal"
```

---

### Task 13: Final Verification

- [ ] **Step 1: Run full test suite one more time**

```bash
cd /Users/rafey/Development/Rafey/AgentDrive && uv run pytest tests/ -v && cd packages/mcp && uv run pytest tests/ -v
```

- [ ] **Step 2: Verify no remaining collection references in source code**

```bash
cd /Users/rafey/Development/Rafey/AgentDrive && grep -r "collection" src/agentdrive/ --include="*.py" | grep -v "collections.abc" | grep -v "__pycache__"
```

Expected: No results (or only stdlib `collections.abc` imports).

```bash
grep -r "collection" packages/mcp/src/ --include="*.py" | grep -v "__pycache__"
```

Expected: No results.

- [ ] **Step 3: Verify no remaining collection references in tests**

```bash
grep -r "collection" tests/ --include="*.py" | grep -v "collections.abc" | grep -v "__pycache__"
grep -r "collection" packages/mcp/tests/ --include="*.py" | grep -v "__pycache__"
```

Expected: No results.
