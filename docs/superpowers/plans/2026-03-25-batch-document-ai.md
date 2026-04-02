# Batch Document AI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Document AI batch processing for PDFs >30 pages, with true multi-batch support via `batch_id` FK on chunks.

**Architecture:** PDFs ≤30 pages use existing sync online API. PDFs 31-500 pages submit one `batch_process_documents()` request (reads from GCS, writes output to GCS). PDFs >500 pages are split into ≤500-page chunks, each submitted as a separate batch request, each producing its own `FileBatch` record. The `FileBatch` model from sub-project 1 gets upgraded to real multi-batch support with `batch_id` on `Chunk` and `ParentChunk`, enabling per-batch enrichment and embedding.

**Note on sync vs async:** `batch_process_documents()` returns a Google Cloud LRO. We call `operation.result(timeout=...)` which blocks the worker thread until completion. This is acceptable since workers are background tasks. The method is named `_process_batch_api` (not async) to reflect this.

**Tech Stack:** Python 3.12, google-cloud-documentai (batch API), google-cloud-storage, SQLAlchemy (async), Alembic, pytest

**Spec:** `docs/superpowers/specs/2026-03-25-batch-document-ai-design.md`

**Depends on:** Sub-project 1 (incremental pipeline) must be completed first.

---

### Task 1: Add `batch_id` FK to Chunk and ParentChunk + Migration

**Files:**
- Modify: `src/agentdrive/models/chunk.py`
- Create: `alembic/versions/005_add_batch_id_to_chunks.py`
- Modify: `tests/conftest.py`
- Create: `tests/test_batch_id.py`

- [ ] **Step 1: Write test for batch_id on Chunk and ParentChunk**

```python
# tests/test_batch_id.py
import pytest
from agentdrive.models.chunk import Chunk, ParentChunk
from agentdrive.models.file import File
from agentdrive.models.file_batch import FileBatch
from agentdrive.models.tenant import Tenant
from agentdrive.models.types import BatchStatus


@pytest.mark.asyncio
async def test_chunk_has_batch_id(db_session):
    tenant = Tenant(name="test")
    db_session.add(tenant)
    await db_session.flush()

    file = File(
        tenant_id=tenant.id, filename="test.pdf", content_type="pdf",
        gcs_path="test/path", file_size=100,
    )
    db_session.add(file)
    await db_session.flush()

    batch = FileBatch(
        file_id=file.id, batch_index=0,
        chunking_status=BatchStatus.COMPLETED, chunk_count=1,
    )
    db_session.add(batch)
    await db_session.flush()

    parent = ParentChunk(file_id=file.id, batch_id=batch.id, content="Test", token_count=5)
    db_session.add(parent)
    await db_session.flush()

    chunk = Chunk(
        file_id=file.id, parent_chunk_id=parent.id, batch_id=batch.id,
        chunk_index=0, content="Child", context_prefix="", token_count=5, content_type="text",
    )
    db_session.add(chunk)
    await db_session.flush()

    assert chunk.batch_id == batch.id
    assert parent.batch_id == batch.id


@pytest.mark.asyncio
async def test_batch_id_nullable_for_backcompat(db_session):
    tenant = Tenant(name="test")
    db_session.add(tenant)
    await db_session.flush()

    file = File(
        tenant_id=tenant.id, filename="test.pdf", content_type="pdf",
        gcs_path="test/path", file_size=100,
    )
    db_session.add(file)
    await db_session.flush()

    parent = ParentChunk(file_id=file.id, content="No batch", token_count=5)
    db_session.add(parent)
    await db_session.flush()
    assert parent.batch_id is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_batch_id.py -v`
Expected: FAIL — `batch_id` not a valid column

- [ ] **Step 3: Add batch_id to Chunk and ParentChunk models**

Modify `src/agentdrive/models/chunk.py` — add to both classes:

```python
    batch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("file_batches.id"), nullable=True)
```

Add relationship to both: `batch = relationship("FileBatch")`

- [ ] **Step 4: Create Alembic migration**

```python
# alembic/versions/005_add_batch_id_to_chunks.py
"""Add batch_id FK to chunks and parent_chunks

Revision ID: 005
Revises: 004
Create Date: 2026-03-25
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '005'
down_revision: Union[str, Sequence[str], None] = '004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('parent_chunks', sa.Column('batch_id', sa.UUID(), sa.ForeignKey('file_batches.id'), nullable=True))
    op.add_column('chunks', sa.Column('batch_id', sa.UUID(), sa.ForeignKey('file_batches.id'), nullable=True))
    op.create_index('ix_parent_chunks_batch_id', 'parent_chunks', ['batch_id'])
    op.create_index('ix_chunks_batch_id', 'chunks', ['batch_id'])


def downgrade() -> None:
    op.drop_index('ix_chunks_batch_id', 'chunks')
    op.drop_index('ix_parent_chunks_batch_id', 'parent_chunks')
    op.drop_column('chunks', 'batch_id')
    op.drop_column('parent_chunks', 'batch_id')
```

- [ ] **Step 5: Update conftest.py to add batch_id columns**

Add to `db_engine` fixture after existing column additions:

```python
        await conn.execute(sa_text(
            "ALTER TABLE parent_chunks ADD COLUMN IF NOT EXISTS batch_id uuid REFERENCES file_batches(id)"
        ))
        await conn.execute(sa_text(
            "ALTER TABLE chunks ADD COLUMN IF NOT EXISTS batch_id uuid REFERENCES file_batches(id)"
        ))
```

- [ ] **Step 6: Run tests**

Run: `uv run pytest tests/test_batch_id.py -v`
Expected: All PASS

- [ ] **Step 7: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All PASS (batch_id is nullable)

- [ ] **Step 8: Commit**

```bash
git add src/agentdrive/models/chunk.py alembic/versions/005_add_batch_id_to_chunks.py \
  tests/test_batch_id.py tests/conftest.py
git commit -m "feat: add batch_id FK to Chunk and ParentChunk for multi-batch support"
```

---

### Task 2: GCS Output Management Methods

**Files:**
- Modify: `src/agentdrive/services/storage.py`
- Create: `tests/test_gcs_output.py`

- [ ] **Step 1: Write tests**

```python
# tests/test_gcs_output.py
from unittest.mock import MagicMock, patch
from agentdrive.services.storage import StorageService


def test_list_blobs():
    mock_blob1 = MagicMock()
    mock_blob1.name = "tmp/docai/abc/output-0.json"
    mock_blob2 = MagicMock()
    mock_blob2.name = "tmp/docai/abc/output-1.json"

    with patch("agentdrive.services.storage.storage_client") as mock_client:
        mock_client.bucket.return_value = MagicMock()
        service = StorageService()
        service._bucket.list_blobs.return_value = [mock_blob1, mock_blob2]

        names = service.list_blobs("tmp/docai/abc/")
        assert names == ["tmp/docai/abc/output-0.json", "tmp/docai/abc/output-1.json"]


def test_delete_prefix():
    mock_blob1 = MagicMock()
    mock_blob2 = MagicMock()

    with patch("agentdrive.services.storage.storage_client") as mock_client:
        mock_client.bucket.return_value = MagicMock()
        service = StorageService()
        service._bucket.list_blobs.return_value = [mock_blob1, mock_blob2]

        service.delete_prefix("tmp/docai/abc/")
        mock_blob1.delete.assert_called_once()
        mock_blob2.delete.assert_called_once()


def test_docai_output_prefix():
    with patch("agentdrive.services.storage.storage_client"):
        service = StorageService()
        assert service.docai_output_prefix("abc-123") == "tmp/docai/abc-123/"


def test_gcs_uri():
    with patch("agentdrive.services.storage.storage_client") as mock_client:
        mock_bucket = MagicMock()
        mock_bucket.name = "my-bucket"
        mock_client.bucket.return_value = mock_bucket
        service = StorageService()
        assert service.gcs_uri("some/path.pdf") == "gs://my-bucket/some/path.pdf"


def test_upload_bytes():
    with patch("agentdrive.services.storage.storage_client") as mock_client:
        mock_bucket = MagicMock()
        mock_client.bucket.return_value = mock_bucket
        mock_blob = MagicMock()
        mock_bucket.blob.return_value = mock_blob

        service = StorageService()
        service.upload_bytes("tmp/splits/test.pdf", b"fake pdf bytes", "application/pdf")
        mock_blob.upload_from_string.assert_called_once_with(b"fake pdf bytes", content_type="application/pdf")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_gcs_output.py -v`
Expected: FAIL — methods don't exist

- [ ] **Step 3: Implement GCS methods**

Add to `src/agentdrive/services/storage.py`:

```python
    def list_blobs(self, prefix: str) -> list[str]:
        """List all blob names under a GCS prefix."""
        return [blob.name for blob in self._bucket.list_blobs(prefix=prefix)]

    def delete_prefix(self, prefix: str) -> None:
        """Delete all blobs under a GCS prefix."""
        for blob in self._bucket.list_blobs(prefix=prefix):
            blob.delete()

    def docai_output_prefix(self, file_id: str) -> str:
        """Return deterministic GCS prefix for Document AI batch output."""
        return f"tmp/docai/{file_id}/"

    def gcs_uri(self, path: str) -> str:
        """Return full gs:// URI for a path in this bucket."""
        return f"gs://{self._bucket.name}/{path}"

    def upload_bytes(self, gcs_path: str, data: bytes, content_type: str) -> None:
        """Upload raw bytes to a GCS path."""
        blob = self._bucket.blob(gcs_path)
        blob.upload_from_string(data, content_type=content_type)

    def delete_blob(self, gcs_path: str) -> None:
        """Delete a single blob by path. Alias for delete() with clearer naming."""
        self.delete(gcs_path)
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_gcs_output.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/agentdrive/services/storage.py tests/test_gcs_output.py
git commit -m "feat: add GCS output management methods for Document AI batch processing"
```

---

### Task 3: Batch Document AI Processing in PdfChunker

The chunker's `chunk_file` becomes a dual-path dispatcher. For >500 pages, it returns batch-segmented results so the ingest pipeline can create multiple `FileBatch` records.

**Key design:** `chunk_file` returns `list[ParentChildChunks]` as before for ≤500 pages. For >500 pages, we add a new method `chunk_file_batched` that returns `list[tuple[str, list[ParentChildChunks]]]` — a list of `(page_range, chunk_groups)` tuples, one per batch. The ingest pipeline calls `chunk_file_batched` when it detects a large PDF.

**Files:**
- Modify: `src/agentdrive/chunking/pdf.py`
- Modify: `src/agentdrive/chunking/base.py`
- Modify: `src/agentdrive/chunking/registry.py`
- Modify: `src/agentdrive/config.py`
- Create: `tests/test_batch_docai.py`

- [ ] **Step 1: Write test for dual-path dispatch**

```python
# tests/test_batch_docai.py
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from pypdf import PdfWriter

from agentdrive.chunking.pdf import PdfChunker


def _make_pdf(tmp_path: Path, num_pages: int) -> Path:
    pdf_path = tmp_path / f"test_{num_pages}pg.pdf"
    writer = PdfWriter()
    for _ in range(num_pages):
        writer.add_blank_page(width=72, height=72)
    with open(pdf_path, "wb") as f:
        writer.write(f)
    return pdf_path


def test_small_pdf_uses_sync_api(tmp_path):
    """PDFs ≤30 pages use sync online API."""
    pdf_path = _make_pdf(tmp_path, 5)
    chunker = PdfChunker()

    with patch.object(chunker, '_process_batch', return_value="# Title\n\nContent") as mock_sync:
        result = chunker.chunk_file(pdf_path, "test.pdf")
        mock_sync.assert_called_once()
        assert len(result) > 0


def test_medium_pdf_uses_batch_api(tmp_path):
    """PDFs 31-500 pages use batch API."""
    pdf_path = _make_pdf(tmp_path, 50)
    chunker = PdfChunker()

    with patch.object(chunker, '_process_batch', side_effect=AssertionError("should not call sync")), \
         patch.object(chunker, '_process_batch_api', return_value="# Batch\n\nContent") as mock_batch:
        result = chunker.chunk_file(pdf_path, "test.pdf", gcs_path="tenants/x/files/y/test.pdf", file_id="test-id")
        mock_batch.assert_called_once()
        assert len(result) > 0


def test_large_pdf_returns_batched_results(tmp_path):
    """PDFs >500 pages return per-batch results via chunk_file_batched."""
    pdf_path = _make_pdf(tmp_path, 600)
    chunker = PdfChunker()

    with patch.object(chunker, '_process_batch_api', return_value="# Split\n\nContent") as mock_batch:
        results = chunker.chunk_file_batched(
            pdf_path, "test.pdf", gcs_path="tenants/x/files/y/test.pdf", file_id="abc-123"
        )
        # 600 pages → 2 batches (500 + 100)
        assert len(results) == 2
        assert results[0][0] == "1-500"
        assert results[1][0] == "501-600"
        assert mock_batch.call_count == 2


def test_no_gcs_path_falls_back_to_sync(tmp_path):
    """Large PDF without gcs_path falls back to sync batches."""
    pdf_path = _make_pdf(tmp_path, 50)
    chunker = PdfChunker()

    with patch.object(chunker, '_process_batch', return_value="# Sync\n\nContent") as mock_sync:
        result = chunker.chunk_file(pdf_path, "test.pdf")  # No gcs_path
        assert mock_sync.called
        assert len(result) > 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_batch_docai.py -v`
Expected: FAIL — `_process_batch_api` and `chunk_file_batched` don't exist

- [ ] **Step 3: Add gcs_path to BaseChunker.chunk_file**

Modify `src/agentdrive/chunking/base.py`:

```python
    def chunk_file(self, path: Path, filename: str, metadata: dict | None = None, gcs_path: str | None = None, file_id: str | None = None) -> list[ParentChildChunks]:
        """Process a file on disk. Override for formats that benefit from file access."""
        data = path.read_bytes()
        return self.chunk_bytes(data, filename, metadata)
```

- [ ] **Step 4: Add docai_batch_timeout_seconds to config**

Add to `src/agentdrive/config.py`:

```python
    docai_batch_timeout_seconds: int = 1800  # 30 minutes
```

- [ ] **Step 5: Implement _process_batch_api in PdfChunker**

Add imports to `src/agentdrive/chunking/pdf.py`:

```python
import json
from pathlib import Path
from agentdrive.services.storage import StorageService
```

Note: `Path` may already be imported if sub-project 1 added it. Verify before adding a duplicate.

Add constant:

```python
_MAX_PAGES_PER_BATCH_API = 500
```

Add method to `PdfChunker`:

```python
    def _process_batch_api(self, gcs_path: str, processor_name: str, file_id: str) -> str:
        """Process a PDF via Document AI batch API. Blocks until complete. Returns markdown."""
        storage = StorageService()
        output_prefix = storage.docai_output_prefix(file_id)

        client = documentai.DocumentProcessorServiceClient()

        input_config = documentai.BatchDocumentsInputConfig(
            gcs_documents=documentai.GcsDocuments(
                documents=[
                    documentai.GcsDocument(
                        gcs_uri=storage.gcs_uri(gcs_path),
                        mime_type="application/pdf",
                    )
                ]
            )
        )
        output_config = documentai.DocumentOutputConfig(
            gcs_output_config=documentai.DocumentOutputConfig.GcsOutputConfig(
                gcs_uri=storage.gcs_uri(output_prefix),
            )
        )
        request = documentai.BatchProcessRequest(
            name=processor_name,
            input_documents=input_config,
            document_output_config=output_config,
        )

        logger.info(f"Submitting batch Document AI request for {gcs_path}")
        operation = client.batch_process_documents(request=request)
        operation.result(timeout=settings.docai_batch_timeout_seconds)

        # Read output documents from GCS
        output_blobs = storage.list_blobs(output_prefix)
        markdown_parts = []
        for blob_name in output_blobs:
            if blob_name.endswith(".json"):
                blob_bytes = storage.download(blob_name)
                document = documentai.Document.from_json(blob_bytes.decode("utf-8"))
                md = _doc_ai_to_markdown(document)
                if md.strip():
                    markdown_parts.append(md)

        # Cleanup
        storage.delete_prefix(output_prefix)
        logger.info(f"Batch Document AI complete for {gcs_path}: {len(markdown_parts)} output docs")
        return "\n\n".join(markdown_parts)
```

- [ ] **Step 6: Update chunk_file for dual-path dispatch**

Replace `chunk_file` in `PdfChunker`:

```python
    def chunk_file(self, path: Path, filename: str, metadata: dict | None = None, gcs_path: str | None = None, file_id: str | None = None) -> list[ParentChildChunks]:
        """Process PDF: sync for ≤30pg, batch API for 31-500pg, fallback to sync if no gcs_path."""
        processor_name = (
            f"projects/{settings.gcp_project_id}"
            f"/locations/{settings.docai_location}"
            f"/processors/{settings.docai_processor_id}"
        )

        reader = PdfReader(str(path))
        total_pages = len(reader.pages)

        if total_pages <= _MAX_PAGES_PER_BATCH:
            # Sync path: fast, no overhead
            data = path.read_bytes()
            markdown = self._process_batch(data, processor_name)
        elif gcs_path is None or file_id is None:
            # No GCS path or file_id — fall back to sync with 30-page splitting
            logger.warning(f"PDF {filename}: {total_pages} pages but no gcs_path/file_id — sync fallback")
            markdown = self._sync_split_fallback(path, reader, total_pages, processor_name)
        elif total_pages <= _MAX_PAGES_PER_BATCH_API:
            # Single batch API request
            markdown = self._process_batch_api(gcs_path, processor_name, file_id)
        else:
            # >500 pages: use chunk_file_batched instead (called by ingest pipeline)
            # If called directly, concatenate all batch results
            batched = self.chunk_file_batched(path, filename, gcs_path=gcs_path, file_id=file_id)
            groups = []
            for _, batch_groups in batched:
                groups.extend(batch_groups)
            return groups

        if not markdown.strip():
            logger.warning(f"PDF {filename}: Document AI produced empty markdown")
            return []

        return self._markdown_chunker.chunk(markdown, filename, metadata)

    def chunk_file_batched(
        self, path: Path, filename: str, gcs_path: str, file_id: str,
        metadata: dict | None = None,
    ) -> list[tuple[str, list[ParentChildChunks]]]:
        """Process PDF >500 pages as multiple batches. Returns (page_range, chunks) per batch."""
        processor_name = (
            f"projects/{settings.gcp_project_id}"
            f"/locations/{settings.docai_location}"
            f"/processors/{settings.docai_processor_id}"
        )

        reader = PdfReader(str(path))
        total_pages = len(reader.pages)
        storage = StorageService()
        results = []

        for start in range(0, total_pages, _MAX_PAGES_PER_BATCH_API):
            end = min(start + _MAX_PAGES_PER_BATCH_API, total_pages)
            page_range = f"{start + 1}-{end}"

            # Split PDF
            writer = PdfWriter()
            for page_num in range(start, end):
                writer.add_page(reader.pages[page_num])
            batch_buffer = io.BytesIO()
            writer.write(batch_buffer)

            # Upload split to temp GCS
            temp_gcs_path = f"tmp/splits/{file_id}/pages_{page_range}.pdf"
            storage.upload_bytes(temp_gcs_path, batch_buffer.getvalue(), "application/pdf")

            # Process via batch API
            markdown = self._process_batch_api(temp_gcs_path, processor_name, f"{file_id}-{page_range}")

            # Cleanup temp split
            storage.delete_blob(temp_gcs_path)

            if markdown.strip():
                chunks = self._markdown_chunker.chunk(markdown, filename, metadata)
                results.append((page_range, chunks))
            else:
                logger.warning(f"PDF {filename} batch {page_range}: empty markdown")
                results.append((page_range, []))

        return results

    def _sync_split_fallback(self, path: Path, reader, total_pages: int, processor_name: str) -> str:
        """Fallback: split and process synchronously when no GCS path available."""
        markdown_parts = []
        for start in range(0, total_pages, _MAX_PAGES_PER_BATCH):
            writer = PdfWriter()
            for page_num in range(start, min(start + _MAX_PAGES_PER_BATCH, total_pages)):
                writer.add_page(reader.pages[page_num])
            batch_buffer = io.BytesIO()
            writer.write(batch_buffer)
            batch_md = self._process_batch(batch_buffer.getvalue(), processor_name)
            if batch_md.strip():
                markdown_parts.append(batch_md)
        return "\n\n".join(markdown_parts)
```

- [ ] **Step 7: Update ChunkerRegistry to pass gcs_path**

Modify `src/agentdrive/chunking/registry.py`:

```python
    def chunk_file(self, content_type: str, path: Path, filename: str, metadata: dict | None = None, gcs_path: str | None = None, file_id: str | None = None) -> list[ParentChildChunks]:
        chunker = self.get_chunker(content_type)
        return chunker.chunk_file(path, filename, metadata, gcs_path=gcs_path, file_id=file_id)
```

- [ ] **Step 8: Write test for _doc_ai_to_markdown with batch output format**

```python
# Add to tests/test_batch_docai.py
from agentdrive.chunking.pdf import _doc_ai_to_markdown
from unittest.mock import MagicMock


def test_doc_ai_to_markdown_with_batch_output():
    """_doc_ai_to_markdown works with Document proto from batch output."""
    # Simulate a Document with document_layout.blocks
    mock_block = MagicMock()
    mock_block.table_block = None
    mock_block.text_block.type_ = "paragraph"
    mock_block.text_block.text = "Batch output paragraph"
    mock_block.text_block.blocks = []

    mock_doc = MagicMock()
    mock_doc.document_layout.blocks = [mock_block]

    result = _doc_ai_to_markdown(mock_doc)
    assert "Batch output paragraph" in result
```

- [ ] **Step 9: Run tests**

Run: `uv run pytest tests/test_batch_docai.py -v`
Expected: All PASS

- [ ] **Step 10: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All PASS

- [ ] **Step 11: Commit**

```bash
git add src/agentdrive/chunking/pdf.py src/agentdrive/chunking/base.py \
  src/agentdrive/chunking/registry.py src/agentdrive/config.py \
  tests/test_batch_docai.py
git commit -m "feat: add batch Document AI processing with dual-path dispatch"
```

---

### Task 4: Scope Embedding Functions to batch_id

**Files:**
- Modify: `src/agentdrive/embedding/pipeline.py`
- Create: `tests/test_batch_embedding.py`

- [ ] **Step 1: Write test for batch-scoped embedding**

```python
# tests/test_batch_embedding.py
import pytest
from unittest.mock import patch, MagicMock

from agentdrive.models.chunk import Chunk, ParentChunk
from agentdrive.models.file import File
from agentdrive.models.file_batch import FileBatch
from agentdrive.models.tenant import Tenant
from agentdrive.models.types import BatchStatus
from agentdrive.embedding.pipeline import embed_file_chunks


@pytest.mark.asyncio
async def test_embed_with_batch_id_scopes_to_batch(db_session):
    """embed_file_chunks with batch_id only embeds that batch's chunks."""
    tenant = Tenant(name="test")
    db_session.add(tenant)
    await db_session.flush()

    file = File(
        tenant_id=tenant.id, filename="test.pdf", content_type="pdf",
        gcs_path="test/path", file_size=100,
    )
    db_session.add(file)
    await db_session.flush()

    batch1 = FileBatch(file_id=file.id, batch_index=0, chunking_status=BatchStatus.COMPLETED, chunk_count=1)
    batch2 = FileBatch(file_id=file.id, batch_index=1, chunking_status=BatchStatus.COMPLETED, chunk_count=1)
    db_session.add_all([batch1, batch2])
    await db_session.flush()

    p1 = ParentChunk(file_id=file.id, batch_id=batch1.id, content="P1", token_count=5)
    p2 = ParentChunk(file_id=file.id, batch_id=batch2.id, content="P2", token_count=5)
    db_session.add_all([p1, p2])
    await db_session.flush()

    c1 = Chunk(file_id=file.id, parent_chunk_id=p1.id, batch_id=batch1.id,
               chunk_index=0, content="Batch 1", context_prefix="", token_count=5, content_type="text")
    c2 = Chunk(file_id=file.id, parent_chunk_id=p2.id, batch_id=batch2.id,
               chunk_index=1, content="Batch 2", context_prefix="", token_count=5, content_type="text")
    db_session.add_all([c1, c2])
    await db_session.commit()

    with patch("agentdrive.embedding.pipeline.EmbeddingClient") as MockClient:
        instance = MockClient.return_value
        instance.embed.return_value = [[0.1] * 1024]
        instance.truncate.return_value = [0.1] * 256

        count = await embed_file_chunks(file.id, db_session, batch_id=batch1.id)
        assert count == 1  # Only batch 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_batch_embedding.py -v`
Expected: FAIL — unexpected keyword argument `batch_id`

- [ ] **Step 3: Add optional batch_id to embed functions**

Modify `src/agentdrive/embedding/pipeline.py`:

For `embed_file_chunks`:
```python
async def embed_file_chunks(file_id: uuid.UUID, session: AsyncSession, batch_id: uuid.UUID | None = None) -> int:
    client = EmbeddingClient()
    query = select(Chunk).where(Chunk.file_id == file_id).order_by(Chunk.chunk_index)
    if batch_id is not None:
        query = query.where(Chunk.batch_id == batch_id)
    result = await session.execute(query)
    # ... rest unchanged
```

For `embed_file_aliases`:
```python
async def embed_file_aliases(file_id: uuid.UUID, session: AsyncSession, batch_id: uuid.UUID | None = None) -> int:
    from agentdrive.models.chunk_alias import ChunkAlias
    client = EmbeddingClient()
    query = select(ChunkAlias).where(ChunkAlias.file_id == file_id)
    if batch_id is not None:
        query = query.join(Chunk, ChunkAlias.chunk_id == Chunk.id).where(Chunk.batch_id == batch_id)
    result = await session.execute(query)
    # ... rest unchanged
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_batch_embedding.py -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All PASS (batch_id=None preserves old behavior)

- [ ] **Step 6: Commit**

```bash
git add src/agentdrive/embedding/pipeline.py tests/test_batch_embedding.py
git commit -m "feat: add batch_id scoping to embedding functions"
```

---

### Task 5: Update Ingest Pipeline for Multi-Batch + Per-Batch Phases

**Files:**
- Modify: `src/agentdrive/services/ingest.py`
- Create: `tests/test_multi_batch_ingest.py`

- [ ] **Step 1: Write test for batch_id being set on chunks**

```python
# tests/test_multi_batch_ingest.py
import pytest
from pathlib import Path
from unittest.mock import patch

from agentdrive.chunking.base import ChunkResult, ParentChildChunks
from agentdrive.models.chunk import Chunk, ParentChunk
from agentdrive.models.file import File
from agentdrive.models.file_batch import FileBatch
from agentdrive.models.file_summary import FileSummary
from agentdrive.models.tenant import Tenant
from agentdrive.models.types import BatchStatus, FileStatus
from agentdrive.services.ingest import process_file
from sqlalchemy import select


def _make_groups(n):
    return [
        ParentChildChunks(
            parent=ChunkResult(content=f"Parent {i}", context_prefix="", token_count=10, content_type="text"),
            children=[ChunkResult(content=f"Child {i}", context_prefix="", token_count=5, content_type="text")],
        ) for i in range(n)
    ]


@pytest.mark.asyncio
async def test_phase1_sets_batch_id(db_session):
    tenant = Tenant(name="test")
    db_session.add(tenant)
    await db_session.flush()

    file = File(
        tenant_id=tenant.id, filename="test.pdf", content_type="pdf",
        gcs_path="tenants/x/files/y/test.pdf", file_size=1000,
    )
    db_session.add(file)
    await db_session.commit()

    with patch("agentdrive.services.ingest.StorageService") as MockStorage, \
         patch("agentdrive.services.ingest.registry") as mock_registry, \
         patch("agentdrive.services.ingest.generate_document_summary") as mock_summary, \
         patch("agentdrive.services.ingest.enrich_chunks_with_summaries") as mock_enrich, \
         patch("agentdrive.services.ingest.generate_table_aliases") as mock_aliases, \
         patch("agentdrive.services.ingest.embed_file_chunks") as mock_ec, \
         patch("agentdrive.services.ingest.embed_file_aliases") as mock_ea:

        MockStorage.return_value.download_to_tempfile.return_value = Path("/tmp/fake.pdf")
        mock_registry.chunk_file.return_value = _make_groups(3)
        mock_summary.return_value = {"document_summary": "Test", "section_summaries": []}
        mock_enrich.return_value = _make_groups(3)
        mock_aliases.return_value = []
        mock_ec.return_value = 0
        mock_ea.return_value = 0

        await process_file(file.id, db_session)

    chunks_result = await db_session.execute(select(Chunk).where(Chunk.file_id == file.id))
    for chunk in chunks_result.scalars().all():
        assert chunk.batch_id is not None

    parents_result = await db_session.execute(select(ParentChunk).where(ParentChunk.file_id == file.id))
    for parent in parents_result.scalars().all():
        assert parent.batch_id is not None


@pytest.mark.asyncio
async def test_per_batch_enrichment_skips_completed(db_session):
    """Phase 3 skips batches already enriched."""
    tenant = Tenant(name="test")
    db_session.add(tenant)
    await db_session.flush()

    file = File(
        tenant_id=tenant.id, filename="big.pdf", content_type="pdf",
        gcs_path="test/path", file_size=100, status=FileStatus.PROCESSING, total_batches=2,
    )
    db_session.add(file)
    await db_session.flush()

    batch1 = FileBatch(file_id=file.id, batch_index=0,
                       chunking_status=BatchStatus.COMPLETED, enrichment_status=BatchStatus.COMPLETED, chunk_count=1)
    batch2 = FileBatch(file_id=file.id, batch_index=1,
                       chunking_status=BatchStatus.COMPLETED, enrichment_status=BatchStatus.PENDING, chunk_count=1)
    db_session.add_all([batch1, batch2])
    await db_session.flush()

    p1 = ParentChunk(file_id=file.id, batch_id=batch1.id, content="P1", token_count=5)
    p2 = ParentChunk(file_id=file.id, batch_id=batch2.id, content="P2", token_count=5)
    db_session.add_all([p1, p2])
    await db_session.flush()

    c1 = Chunk(file_id=file.id, parent_chunk_id=p1.id, batch_id=batch1.id,
               chunk_index=0, content="C1", context_prefix="already done", token_count=5, content_type="text")
    c2 = Chunk(file_id=file.id, parent_chunk_id=p2.id, batch_id=batch2.id,
               chunk_index=1, content="C2", context_prefix="", token_count=5, content_type="text")
    db_session.add_all([c1, c2])

    summary = FileSummary(file_id=file.id, document_summary="Test", section_summaries=[])
    db_session.add(summary)
    await db_session.commit()

    with patch("agentdrive.services.ingest.StorageService"), \
         patch("agentdrive.services.ingest.registry"):
        await process_file(file.id, db_session)

    await db_session.refresh(c1)
    assert c1.context_prefix == "already done"  # Not re-enriched

    await db_session.refresh(file)
    assert file.status == FileStatus.READY


@pytest.mark.asyncio
async def test_resume_multi_batch_after_failure(db_session):
    """Full resume: Phase 1 done, Phase 2 done, Phase 3 partial — resumes from batch 2."""
    tenant = Tenant(name="test")
    db_session.add(tenant)
    await db_session.flush()

    file = File(
        tenant_id=tenant.id, filename="resume.pdf", content_type="pdf",
        gcs_path="test/path", file_size=100, status=FileStatus.FAILED, total_batches=2,
    )
    db_session.add(file)
    await db_session.flush()

    batch1 = FileBatch(file_id=file.id, batch_index=0,
                       chunking_status=BatchStatus.COMPLETED,
                       enrichment_status=BatchStatus.COMPLETED,
                       embedding_status=BatchStatus.COMPLETED, chunk_count=1)
    batch2 = FileBatch(file_id=file.id, batch_index=1,
                       chunking_status=BatchStatus.COMPLETED,
                       enrichment_status=BatchStatus.PENDING,
                       embedding_status=BatchStatus.PENDING, chunk_count=1)
    db_session.add_all([batch1, batch2])
    await db_session.flush()

    p1 = ParentChunk(file_id=file.id, batch_id=batch1.id, content="P1", token_count=5)
    p2 = ParentChunk(file_id=file.id, batch_id=batch2.id, content="P2", token_count=5)
    db_session.add_all([p1, p2])
    await db_session.flush()

    c1 = Chunk(file_id=file.id, parent_chunk_id=p1.id, batch_id=batch1.id,
               chunk_index=0, content="C1", context_prefix="enriched", token_count=5, content_type="text")
    c2 = Chunk(file_id=file.id, parent_chunk_id=p2.id, batch_id=batch2.id,
               chunk_index=1, content="C2", context_prefix="", token_count=5, content_type="text")
    db_session.add_all([c1, c2])

    summary = FileSummary(file_id=file.id, document_summary="Test", section_summaries=[])
    db_session.add(summary)
    await db_session.commit()

    with patch("agentdrive.services.ingest.StorageService"), \
         patch("agentdrive.services.ingest.registry"):
        await process_file(file.id, db_session)

    await db_session.refresh(file)
    assert file.status == FileStatus.READY
    await db_session.refresh(batch2)
    assert batch2.enrichment_status == BatchStatus.COMPLETED
    assert batch2.embedding_status == BatchStatus.COMPLETED
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_multi_batch_ingest.py -v`
Expected: FAIL

- [ ] **Step 3: Update ingest pipeline**

Modify `src/agentdrive/services/ingest.py`:

**Key changes:**

1. `_phase1_chunking`: Set `batch_id` on all chunks, pass `gcs_path` and `file_id=str(file.id)` to registry
2. `_phase3_enrichment`: Loop per-batch, load only that batch's chunks via `batch_id`
3. `_phase4_embedding`: Loop per-batch, pass `batch_id` to embed functions
4. `_load_chunk_groups`: Accept optional `batch_id` filter
5. `_get_batch` → `_get_batches` (returns list)
6. Resume logic: Check all batches' statuses
7. `completed_batches`: Only updated in Phase 4 (counts fully-completed batches)

In `_phase1_chunking`, add `batch_id=batch.id` to `ParentChunk` and `Chunk` creation, and pass `gcs_path=file.gcs_path` to `registry.chunk_file()`.

In `_phase3_enrichment`:
```python
async def _phase3_enrichment(file: File, summary: FileSummary, session: AsyncSession) -> None:
    batches = await _get_batches(file.id, session)
    for batch in batches:
        if batch.enrichment_status == BatchStatus.COMPLETED:
            continue
        batch.enrichment_status = BatchStatus.PROCESSING
        await session.commit()

        chunk_groups = await _load_chunk_groups(file.id, session, batch_id=batch.id)
        chunk_groups = await enrich_chunks_with_summaries(
            chunk_groups, summary.document_summary, summary.section_summaries)

        db_chunks = list((await session.execute(
            select(Chunk).where(Chunk.batch_id == batch.id).order_by(Chunk.chunk_index)
        )).scalars().all())

        enriched_children = []
        for group in chunk_groups:
            enriched_children.extend(group.children)
        for db_chunk, enriched in zip(db_chunks, enriched_children):
            db_chunk.context_prefix = enriched.context_prefix

        table_aliases = await generate_table_aliases(chunk_groups)
        for alias_data in table_aliases:
            for c in db_chunks:
                if c.content == alias_data["chunk"].content:
                    session.add(ChunkAlias(
                        chunk_id=c.id, file_id=file.id,
                        content=alias_data["question"],
                        token_count=count_tokens(alias_data["question"]),
                    ))
                    break

        batch.enrichment_status = BatchStatus.COMPLETED
        await session.commit()
```

In `_phase4_embedding`:
```python
async def _phase4_embedding(file: File, session: AsyncSession) -> None:
    batches = await _get_batches(file.id, session)
    for batch in batches:
        if batch.embedding_status == BatchStatus.COMPLETED:
            continue
        batch.embedding_status = BatchStatus.PROCESSING
        await session.commit()

        await embed_file_chunks(file.id, session, batch_id=batch.id)
        await embed_file_aliases(file.id, session, batch_id=batch.id)

        batch.embedding_status = BatchStatus.COMPLETED
        await session.commit()

    # Update completed_batches (fully completed = all phases done)
    file.completed_batches = sum(
        1 for b in batches if b.embedding_status == BatchStatus.COMPLETED
    )
    await session.commit()
```

Update `_load_chunk_groups` to accept `batch_id`:
```python
async def _load_chunk_groups(
    file_id: uuid.UUID, session: AsyncSession, batch_id: uuid.UUID | None = None
) -> list[ParentChildChunks]:
    query = select(ParentChunk).where(ParentChunk.file_id == file_id).order_by(ParentChunk.created_at)
    if batch_id is not None:
        query = query.where(ParentChunk.batch_id == batch_id)
    # ... rest same
```

Update resume logic in `process_file` to use `_get_batches` (list) and check `all(b.X_status == COMPLETED for b in batches)`.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_multi_batch_ingest.py -v`
Expected: All PASS

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/agentdrive/services/ingest.py tests/test_multi_batch_ingest.py
git commit -m "feat: multi-batch ingest with batch_id, per-batch enrichment and embedding"
```

---

### Task 6: Integration Test + Regression Verification

**Files:**
- Create: `tests/test_integration_batch_docai.py`

- [ ] **Step 1: Write regression test for small PDF**

```python
# tests/test_integration_batch_docai.py
import pytest
from pathlib import Path
from unittest.mock import patch

from agentdrive.chunking.base import ChunkResult, ParentChildChunks
from agentdrive.models.chunk import Chunk
from agentdrive.models.file import File
from agentdrive.models.file_batch import FileBatch
from agentdrive.models.tenant import Tenant
from agentdrive.models.types import BatchStatus, FileStatus
from agentdrive.services.ingest import process_file
from sqlalchemy import select


@pytest.mark.asyncio
async def test_small_pdf_unchanged(db_session):
    """Small PDF still works end-to-end with batch_id set."""
    tenant = Tenant(name="test")
    db_session.add(tenant)
    await db_session.flush()

    file = File(
        tenant_id=tenant.id, filename="small.pdf", content_type="pdf",
        gcs_path="tenants/x/files/y/small.pdf", file_size=100,
    )
    db_session.add(file)
    await db_session.commit()

    groups = [
        ParentChildChunks(
            parent=ChunkResult(content="Small", context_prefix="", token_count=5, content_type="text"),
            children=[ChunkResult(content="Content", context_prefix="", token_count=3, content_type="text")],
        ),
    ]

    with patch("agentdrive.services.ingest.StorageService") as MockStorage, \
         patch("agentdrive.services.ingest.registry") as mock_registry:
        MockStorage.return_value.download_to_tempfile.return_value = Path("/tmp/fake.pdf")
        mock_registry.chunk_file.return_value = groups
        await process_file(file.id, db_session)

    await db_session.refresh(file)
    assert file.status == FileStatus.READY

    chunks = (await db_session.execute(select(Chunk).where(Chunk.file_id == file.id))).scalars().all()
    assert len(chunks) == 1
    assert chunks[0].batch_id is not None

    batches = (await db_session.execute(select(FileBatch).where(FileBatch.file_id == file.id))).scalars().all()
    assert len(batches) == 1
    assert batches[0].embedding_status == BatchStatus.COMPLETED
```

- [ ] **Step 2: Run all tests**

Run: `uv run pytest tests/ -v`
Expected: All PASS

- [ ] **Step 3: Lint check**

Run: `uv run ruff check src/agentdrive/ --select F401,F841`
Expected: Clean

- [ ] **Step 4: Commit**

```bash
git add tests/test_integration_batch_docai.py
git commit -m "test: integration tests for batch Document AI and small PDF regression"
```
