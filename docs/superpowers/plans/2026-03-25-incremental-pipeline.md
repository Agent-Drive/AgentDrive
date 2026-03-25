# Incremental Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure the ingestion pipeline from hold-everything-in-memory to incremental/streaming processing with four-phase architecture and two-pass enrichment.

**Architecture:** The pipeline becomes four sequential phases: (1) chunk with per-batch DB commits, (2) generate document + section summaries, (3) enrich chunks using summaries + local context and generate table aliases, (4) embed chunks + aliases in batches. Each phase is resumable via status tracking in a new `FileBatch` model. Sub-project 1 creates exactly one batch per file; true multi-batch splitting (with `batch_id` FK on chunks) comes in sub-project 2 when Document AI batch API is added.

**Tech Stack:** Python 3.12, SQLAlchemy (async), Alembic, FastAPI, Google Cloud Storage, Google Document AI, Anthropic API, Voyage AI, pytest

**Spec:** `docs/superpowers/specs/2026-03-25-incremental-pipeline-design.md`

---

### Task 1: Add FileBatch and FileSummary Models + Migration

**Files:**
- Create: `src/agentdrive/models/file_batch.py`
- Create: `src/agentdrive/models/file_summary.py`
- Modify: `src/agentdrive/models/__init__.py`
- Modify: `src/agentdrive/models/file.py`
- Modify: `src/agentdrive/models/types.py`
- Create: `alembic/versions/004_file_batches_and_summaries.py`
- Create: `tests/test_models_batch.py`
- Modify: `tests/conftest.py`

- [ ] **Step 1: Write test for FileBatch model**

```python
# tests/test_models_batch.py
import pytest
import pytest_asyncio
from agentdrive.models.file_batch import FileBatch
from agentdrive.models.file_summary import FileSummary
from agentdrive.models.file import File
from agentdrive.models.tenant import Tenant
from agentdrive.models.types import BatchStatus


@pytest.mark.asyncio
async def test_create_file_batch(db_session):
    tenant = Tenant(name="test")
    db_session.add(tenant)
    await db_session.flush()

    file = File(
        tenant_id=tenant.id,
        filename="test.pdf",
        content_type="pdf",
        gcs_path="tenants/x/files/y/test.pdf",
        file_size=1000,
    )
    db_session.add(file)
    await db_session.flush()

    batch = FileBatch(
        file_id=file.id,
        batch_index=0,
        page_range="1-30",
        chunk_count=0,
    )
    db_session.add(batch)
    await db_session.flush()

    assert batch.id is not None
    assert batch.chunking_status == BatchStatus.PENDING
    assert batch.enrichment_status == BatchStatus.PENDING
    assert batch.embedding_status == BatchStatus.PENDING


@pytest.mark.asyncio
async def test_create_file_summary(db_session):
    tenant = Tenant(name="test")
    db_session.add(tenant)
    await db_session.flush()

    file = File(
        tenant_id=tenant.id,
        filename="test.pdf",
        content_type="pdf",
        gcs_path="tenants/x/files/y/test.pdf",
        file_size=1000,
    )
    db_session.add(file)
    await db_session.flush()

    summary = FileSummary(
        file_id=file.id,
        document_summary="This is a test document about widgets.",
        section_summaries=[
            {"heading": "Introduction", "summary": "Overview of widgets"},
            {"heading": "Pricing", "summary": "Widget pricing details"},
        ],
    )
    db_session.add(summary)
    await db_session.flush()

    assert summary.id is not None
    assert summary.document_summary == "This is a test document about widgets."
    assert len(summary.section_summaries) == 2


@pytest.mark.asyncio
async def test_file_progress_fields(db_session):
    tenant = Tenant(name="test")
    db_session.add(tenant)
    await db_session.flush()

    file = File(
        tenant_id=tenant.id,
        filename="test.pdf",
        content_type="pdf",
        gcs_path="tenants/x/files/y/test.pdf",
        file_size=1000,
    )
    db_session.add(file)
    await db_session.flush()

    assert file.total_batches == 0
    assert file.completed_batches == 0
    assert file.current_phase is None
    assert file.retry_count == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_models_batch.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'agentdrive.models.file_batch'`

- [ ] **Step 3: Add BatchStatus to types.py**

Add to `src/agentdrive/models/types.py`:

```python
class BatchStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
```

- [ ] **Step 4: Create FileBatch model**

```python
# src/agentdrive/models/file_batch.py
import uuid

from sqlalchemy import ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from agentdrive.models.base import Base, TimestampMixin, UUIDPrimaryKey
from agentdrive.models.types import BatchStatus


class FileBatch(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "file_batches"

    file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("files.id", ondelete="CASCADE"), nullable=False
    )
    batch_index: Mapped[int] = mapped_column(Integer, nullable=False)
    page_range: Mapped[str | None] = mapped_column(Text, nullable=True)
    chunking_status: Mapped[str] = mapped_column(
        Text, nullable=False, default=BatchStatus.PENDING
    )
    enrichment_status: Mapped[str] = mapped_column(
        Text, nullable=False, default=BatchStatus.PENDING
    )
    embedding_status: Mapped[str] = mapped_column(
        Text, nullable=False, default=BatchStatus.PENDING
    )
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    file = relationship("File", back_populates="batches")
```

- [ ] **Step 5: Create FileSummary model**

```python
# src/agentdrive/models/file_summary.py
import uuid

from sqlalchemy import ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from agentdrive.models.base import Base, TimestampMixin, UUIDPrimaryKey


class FileSummary(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "file_summaries"

    file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("files.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    document_summary: Mapped[str] = mapped_column(Text, nullable=False)
    section_summaries: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")

    file = relationship("File", back_populates="summary")
```

- [ ] **Step 6: Add progress fields and relationships to File model**

Modify `src/agentdrive/models/file.py` — add `Integer` to the sqlalchemy import. Add after existing fields:

```python
    total_batches: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    completed_batches: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    current_phase: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
```

Add relationships:

```python
    batches = relationship("FileBatch", back_populates="file", cascade="all, delete-orphan")
    summary = relationship("FileSummary", back_populates="file", uselist=False, cascade="all, delete-orphan")
```

- [ ] **Step 7: Update models __init__.py**

Add to `src/agentdrive/models/__init__.py`:

```python
from agentdrive.models.file_batch import FileBatch
from agentdrive.models.file_summary import FileSummary
```

Add `BatchStatus`, `FileBatch`, `FileSummary` to `__all__`.

- [ ] **Step 8: Create Alembic migration**

```python
# alembic/versions/004_file_batches_and_summaries.py
"""Add file_batches, file_summaries tables and file progress fields

Revision ID: 004
Revises: 19f589d55e82
Create Date: 2026-03-25
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = '004'
down_revision: Union[str, Sequence[str], None] = '19f589d55e82'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'file_batches',
        sa.Column('id', sa.UUID(), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('file_id', sa.UUID(), sa.ForeignKey('files.id', ondelete='CASCADE'), nullable=False),
        sa.Column('batch_index', sa.Integer(), nullable=False),
        sa.Column('page_range', sa.Text(), nullable=True),
        sa.Column('chunking_status', sa.Text(), nullable=False, server_default='pending'),
        sa.Column('enrichment_status', sa.Text(), nullable=False, server_default='pending'),
        sa.Column('embedding_status', sa.Text(), nullable=False, server_default='pending'),
        sa.Column('chunk_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_file_batches_file_id', 'file_batches', ['file_id'])

    op.create_table(
        'file_summaries',
        sa.Column('id', sa.UUID(), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('file_id', sa.UUID(), sa.ForeignKey('files.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('document_summary', sa.Text(), nullable=False),
        sa.Column('section_summaries', JSONB(), nullable=False, server_default='[]'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )

    op.add_column('files', sa.Column('total_batches', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('files', sa.Column('completed_batches', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('files', sa.Column('current_phase', sa.Text(), nullable=True))
    op.add_column('files', sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
    op.drop_column('files', 'retry_count')
    op.drop_column('files', 'current_phase')
    op.drop_column('files', 'completed_batches')
    op.drop_column('files', 'total_batches')
    op.drop_table('file_summaries')
    op.drop_index('ix_file_batches_file_id', 'file_batches')
    op.drop_table('file_batches')
```

- [ ] **Step 9: Update conftest.py to create new tables in test DB**

Add to the `db_engine` fixture in `tests/conftest.py`, after the `api_keys` table creation:

```python
        await conn.execute(sa_text(
            "CREATE TABLE IF NOT EXISTS file_batches ("
            "id uuid PRIMARY KEY DEFAULT gen_random_uuid(), "
            "file_id uuid REFERENCES files(id) ON DELETE CASCADE, "
            "batch_index integer NOT NULL, "
            "page_range text, "
            "chunking_status text NOT NULL DEFAULT 'pending', "
            "enrichment_status text NOT NULL DEFAULT 'pending', "
            "embedding_status text NOT NULL DEFAULT 'pending', "
            "chunk_count integer NOT NULL DEFAULT 0, "
            "created_at timestamptz DEFAULT now(), "
            "updated_at timestamptz DEFAULT now())"
        ))
        await conn.execute(sa_text(
            "CREATE TABLE IF NOT EXISTS file_summaries ("
            "id uuid PRIMARY KEY DEFAULT gen_random_uuid(), "
            "file_id uuid REFERENCES files(id) ON DELETE CASCADE UNIQUE, "
            "document_summary text NOT NULL, "
            "section_summaries jsonb NOT NULL DEFAULT '[]', "
            "created_at timestamptz DEFAULT now(), "
            "updated_at timestamptz DEFAULT now())"
        ))
        # Add progress columns to files
        for col, default in [
            ('total_batches', '0'), ('completed_batches', '0'),
            ('current_phase', None), ('retry_count', '0')
        ]:
            dtype = 'text' if col == 'current_phase' else 'integer'
            nullable = 'NULL' if col == 'current_phase' else f"NOT NULL DEFAULT {default}"
            await conn.execute(sa_text(
                f"ALTER TABLE files ADD COLUMN IF NOT EXISTS {col} {dtype} {nullable}"
            ))
```

- [ ] **Step 10: Run tests to verify they pass**

Run: `uv run pytest tests/test_models_batch.py -v`
Expected: All 3 tests PASS

- [ ] **Step 11: Run full test suite for regressions**

Run: `uv run pytest tests/ -v`
Expected: All existing tests PASS

- [ ] **Step 12: Commit**

```bash
git add src/agentdrive/models/file_batch.py src/agentdrive/models/file_summary.py \
  src/agentdrive/models/__init__.py src/agentdrive/models/file.py \
  src/agentdrive/models/types.py alembic/versions/004_file_batches_and_summaries.py \
  tests/test_models_batch.py tests/conftest.py
git commit -m "feat: add FileBatch, FileSummary models and file progress fields"
```

---

### Task 2: Streaming Download + chunk_file Interface

**Files:**
- Modify: `src/agentdrive/services/storage.py`
- Modify: `src/agentdrive/chunking/base.py`
- Modify: `src/agentdrive/chunking/pdf.py`
- Modify: `src/agentdrive/chunking/registry.py`
- Create: `tests/test_streaming_download.py`

- [ ] **Step 1: Write test for download_to_tempfile**

```python
# tests/test_streaming_download.py
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agentdrive.services.storage import StorageService


def test_download_to_tempfile():
    """StorageService.download_to_tempfile writes GCS content to a temp file and returns its path."""
    mock_blob = MagicMock()
    mock_blob.download_to_filename = MagicMock()

    with patch("agentdrive.services.storage.storage_client") as mock_gcs_client:
        mock_gcs_client.bucket.return_value = MagicMock()
        service = StorageService()
        service._bucket.blob.return_value = mock_blob

        path = service.download_to_tempfile("tenants/x/files/y/test.pdf")

        assert isinstance(path, Path)
        assert path.suffix == ".pdf"
        mock_blob.download_to_filename.assert_called_once_with(str(path))
        # Clean up temp file
        if path.exists():
            os.unlink(path)


def test_download_to_tempfile_preserves_extension():
    with patch("agentdrive.services.storage.storage_client") as mock_gcs_client:
        mock_gcs_client.bucket.return_value = MagicMock()
        service = StorageService()
        service._bucket.blob.return_value = MagicMock()

        path = service.download_to_tempfile("tenants/x/files/y/report.xlsx")
        assert path.suffix == ".xlsx"
        if path.exists():
            os.unlink(path)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_streaming_download.py -v`
Expected: FAIL — `AttributeError: type object 'StorageService' has no attribute 'download_to_tempfile'`

- [ ] **Step 3: Implement download_to_tempfile**

Add to `src/agentdrive/services/storage.py`:

```python
import tempfile
from pathlib import Path
```

Add method to `StorageService`:

```python
    def download_to_tempfile(self, gcs_path: str) -> Path:
        """Download GCS object to a temp file on disk. Caller must clean up."""
        suffix = Path(gcs_path).suffix or ""
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        tmp.close()
        blob = self._bucket.blob(gcs_path)
        blob.download_to_filename(tmp.name)
        return Path(tmp.name)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_streaming_download.py -v`
Expected: PASS

- [ ] **Step 5: Write test for chunk_file on BaseChunker**

Add to `tests/test_streaming_download.py`:

```python
from agentdrive.chunking.base import BaseChunker, ChunkResult, ParentChildChunks


class StubChunker(BaseChunker):
    def chunk(self, content, filename, metadata=None):
        return [ParentChildChunks(
            parent=ChunkResult(content=content, context_prefix="", token_count=1, content_type="text"),
            children=[],
        )]

    def supported_types(self):
        return ["text"]


def test_base_chunker_chunk_file_delegates_to_chunk_bytes(tmp_path):
    """Default chunk_file reads file and delegates to chunk_bytes."""
    p = tmp_path / "test.txt"
    p.write_text("hello world")

    chunker = StubChunker()
    result = chunker.chunk_file(p, "test.txt")
    assert len(result) == 1
    assert result[0].parent.content == "hello world"
```

- [ ] **Step 6: Run test to verify it fails**

Run: `uv run pytest tests/test_streaming_download.py::test_base_chunker_chunk_file_delegates_to_chunk_bytes -v`
Expected: FAIL — `AttributeError: 'StubChunker' object has no attribute 'chunk_file'`

- [ ] **Step 7: Add chunk_file to BaseChunker**

Add to `src/agentdrive/chunking/base.py`:

```python
from pathlib import Path
```

Add method to `BaseChunker` after `chunk_bytes`:

```python
    def chunk_file(self, path: Path, filename: str, metadata: dict | None = None) -> list[ParentChildChunks]:
        """Process a file on disk. Override for formats that benefit from file access. Default reads into bytes."""
        data = path.read_bytes()
        return self.chunk_bytes(data, filename, metadata)
```

- [ ] **Step 8: Run test to verify it passes**

Run: `uv run pytest tests/test_streaming_download.py -v`
Expected: All tests PASS

- [ ] **Step 9: Write test for PdfChunker.chunk_file**

Add to `tests/test_streaming_download.py`:

```python
from agentdrive.chunking.pdf import PdfChunker


def test_pdf_chunker_chunk_file_uses_file_path(tmp_path):
    """PdfChunker.chunk_file opens PDF from path, not via chunk_bytes."""
    pdf_path = tmp_path / "test.pdf"
    from pypdf import PdfWriter
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    with open(pdf_path, "wb") as f:
        writer.write(f)

    chunker = PdfChunker()
    # Patch chunk_bytes to raise — proving chunk_file doesn't delegate to it
    with patch.object(chunker, 'chunk_bytes', side_effect=AssertionError("should not call chunk_bytes")):
        with patch.object(chunker, '_process_batch', return_value="# Test\n\nContent"):
            result = chunker.chunk_file(pdf_path, "test.pdf")
            assert len(result) > 0
```

- [ ] **Step 10: Run test to verify it fails**

Run: `uv run pytest tests/test_streaming_download.py::test_pdf_chunker_chunk_file_uses_file_path -v`
Expected: FAIL — raises `AssertionError` because `BaseChunker.chunk_file` delegates to `chunk_bytes`

- [ ] **Step 11: Override chunk_file in PdfChunker**

Add to `PdfChunker` in `src/agentdrive/chunking/pdf.py`:

```python
from pathlib import Path
```

Add method:

```python
    def chunk_file(self, path: Path, filename: str, metadata: dict | None = None) -> list[ParentChildChunks]:
        """Process PDF from a file path on disk instead of in-memory bytes."""
        processor_name = (
            f"projects/{settings.gcp_project_id}"
            f"/locations/{settings.docai_location}"
            f"/processors/{settings.docai_processor_id}"
        )

        reader = PdfReader(str(path))
        total_pages = len(reader.pages)

        if total_pages <= _MAX_PAGES_PER_BATCH:
            data = path.read_bytes()
            markdown = self._process_batch(data, processor_name)
        else:
            logger.info(f"PDF {filename}: {total_pages} pages, splitting into batches of {_MAX_PAGES_PER_BATCH}")
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
            markdown = "\n\n".join(markdown_parts)

        if not markdown.strip():
            logger.warning(f"PDF {filename}: Document AI produced empty markdown")
            return []

        return self._markdown_chunker.chunk(markdown, filename, metadata)
```

- [ ] **Step 12: Update ChunkerRegistry to expose chunk_file dispatch**

Add a helper method to `src/agentdrive/chunking/registry.py`:

```python
from pathlib import Path
from agentdrive.chunking.base import ParentChildChunks
```

Add method to `ChunkerRegistry`:

```python
    def chunk_file(self, content_type: str, path: Path, filename: str, metadata: dict | None = None) -> list[ParentChildChunks]:
        """Dispatch to chunker's chunk_file method."""
        chunker = self.get_chunker(content_type)
        return chunker.chunk_file(path, filename, metadata)
```

- [ ] **Step 13: Run all tests to verify they pass**

Run: `uv run pytest tests/test_streaming_download.py -v`
Expected: All tests PASS

- [ ] **Step 14: Run full test suite for regressions**

Run: `uv run pytest tests/ -v`
Expected: All existing tests PASS

- [ ] **Step 15: Commit**

```bash
git add src/agentdrive/services/storage.py src/agentdrive/chunking/base.py \
  src/agentdrive/chunking/pdf.py src/agentdrive/chunking/registry.py \
  tests/test_streaming_download.py
git commit -m "feat: add streaming download and chunk_file interface for disk-based PDF processing"
```

---

### Task 3: Two-Pass Enrichment (Summarize + Local Context)

**Files:**
- Modify: `src/agentdrive/enrichment/client.py`
- Modify: `src/agentdrive/enrichment/contextual.py`
- Create: `tests/test_two_pass_enrichment.py`

- [ ] **Step 1: Write test for document summarization**

```python
# tests/test_two_pass_enrichment.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from agentdrive.enrichment.contextual import generate_document_summary


@pytest.mark.asyncio
async def test_generate_document_summary():
    """generate_document_summary returns doc summary + section summaries."""
    with patch("agentdrive.enrichment.contextual.EnrichmentClient") as MockClient:
        instance = MockClient.return_value
        instance.generate_summary = AsyncMock(return_value={
            "document_summary": "A contract between Acme and Beta Corp.",
            "section_summaries": [{"heading": "Liability", "summary": "Caps liability at $5M"}],
        })

        result = await generate_document_summary("Full document text here...")

        assert result["document_summary"] == "A contract between Acme and Beta Corp."
        assert len(result["section_summaries"]) == 1
        instance.generate_summary.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_two_pass_enrichment.py::test_generate_document_summary -v`
Expected: FAIL — `cannot import name 'generate_document_summary'`

- [ ] **Step 3: Write test for local-context enrichment**

```python
# Add to tests/test_two_pass_enrichment.py
from agentdrive.chunking.base import ChunkResult, ParentChildChunks
from agentdrive.enrichment.contextual import enrich_chunks_with_summaries


@pytest.mark.asyncio
async def test_enrich_chunks_with_summaries():
    """enrich_chunks_with_summaries uses doc summary + neighbors instead of full doc."""
    chunk_groups = [
        ParentChildChunks(
            parent=ChunkResult(content="Section about pricing", context_prefix="", token_count=10, content_type="text"),
            children=[
                ChunkResult(content="Widget costs $50", context_prefix="", token_count=5, content_type="text"),
            ],
        ),
        ParentChildChunks(
            parent=ChunkResult(content="Section about delivery", context_prefix="", token_count=10, content_type="text"),
            children=[
                ChunkResult(content="Ships in 3 days", context_prefix="", token_count=5, content_type="text"),
            ],
        ),
    ]

    doc_summary = "A product catalog for Acme Corp widgets."
    section_summaries = [
        {"heading": "Pricing", "summary": "Widget pricing details"},
        {"heading": "Delivery", "summary": "Shipping timelines"},
    ]

    with patch("agentdrive.enrichment.contextual.EnrichmentClient") as MockClient:
        instance = MockClient.return_value
        instance.generate_context_with_summary = AsyncMock(return_value="Enriched prefix")

        result = await enrich_chunks_with_summaries(
            chunk_groups, doc_summary, section_summaries
        )

        # All chunks should have enriched prefix
        for group in result:
            assert group.parent.context_prefix == "Enriched prefix"
            for child in group.children:
                assert child.context_prefix == "Enriched prefix"
```

- [ ] **Step 4: Add generate_summary and generate_context_with_summary to EnrichmentClient**

Add prompts to `src/agentdrive/enrichment/client.py`:

```python
SUMMARY_PROMPT = """Analyze this document and produce:
1. A document_summary (2-3 sentences describing the document's purpose, parties involved, and subject matter)
2. section_summaries (a list of objects with "heading" and "summary" for each major section)

<document>
{document_text}
</document>

Return valid JSON with this exact structure:
{{"document_summary": "...", "section_summaries": [{{"heading": "...", "summary": "..."}}]}}"""

CONTEXT_WITH_SUMMARY_PROMPT = """Document summary: {doc_summary}

Section context: {section_summary}

Nearby content:
{neighbors}

Here is the chunk we want to situate:
<chunk>
{chunk_text}
</chunk>
Please give a short succinct context to situate this chunk within the overall document for the purposes of improving search retrieval of the chunk. Answer only with the succinct context and nothing else."""
```

Add methods to `EnrichmentClient`:

```python
    async def generate_summary(self, document_text: str) -> dict:
        """Generate document summary and section summaries."""
        try:
            response = await self._client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=2000,
                messages=[
                    {"role": "user", "content": SUMMARY_PROMPT.format(document_text=document_text)}
                ],
            )
            import json
            return json.loads(response.content[0].text.strip())
        except Exception as e:
            logger.warning(f"Summary generation failed: {e}")
            return {"document_summary": "", "section_summaries": []}

    async def generate_context_with_summary(
        self, doc_summary: str, section_summary: str, neighbors: str, chunk_text: str
    ) -> str:
        """Generate context prefix using summaries + local context instead of full document."""
        try:
            response = await self._client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=200,
                messages=[
                    {
                        "role": "user",
                        "content": CONTEXT_WITH_SUMMARY_PROMPT.format(
                            doc_summary=doc_summary,
                            section_summary=section_summary,
                            neighbors=neighbors,
                            chunk_text=chunk_text,
                        ),
                    }
                ],
            )
            return response.content[0].text.strip()
        except Exception as e:
            logger.warning(f"Context generation with summary failed: {e}")
            return ""
```

- [ ] **Step 5: Implement generate_document_summary and enrich_chunks_with_summaries**

Rewrite `src/agentdrive/enrichment/contextual.py`. Preserve the legacy `enrich_chunks` function (it may be referenced by other code paths), add the new functions:

```python
import asyncio
import logging

from agentdrive.chunking.base import ParentChildChunks
from agentdrive.enrichment.client import EnrichmentClient

logger = logging.getLogger(__name__)

MAX_CONCURRENT = 5
NEIGHBOR_RANGE = 3  # +/-3 parent chunks for local context


async def enrich_chunks(
    document_text: str,
    chunk_groups: list[ParentChildChunks],
) -> list[ParentChildChunks]:
    """Enrich all chunks with LLM-generated context prefixes (legacy full-doc method)."""
    client = EnrichmentClient()
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)

    async def enrich_one(chunk_result):
        async with semaphore:
            context = await client.generate_context(document_text, chunk_result.content)
            if context:
                chunk_result.context_prefix = context

    tasks = []
    for group in chunk_groups:
        tasks.append(enrich_one(group.parent))
        for child in group.children:
            tasks.append(enrich_one(child))

    await asyncio.gather(*tasks)
    return chunk_groups


async def generate_document_summary(document_text: str) -> dict:
    """Generate document summary + section summaries (Pass 1 of two-pass enrichment)."""
    client = EnrichmentClient()
    return await client.generate_summary(document_text)


def _find_section_summary(
    chunk_content: str, section_summaries: list[dict]
) -> str:
    """Return concatenated section summaries as context.

    TODO: Implement proper section-to-chunk matching using heading positions.
    Currently returns all summaries, which degrades for documents with many sections.
    """
    if not section_summaries:
        return ""
    return "; ".join(f"{s['heading']}: {s['summary']}" for s in section_summaries)


def _get_neighbors(
    chunk_groups: list[ParentChildChunks], group_index: int
) -> str:
    """Get +/-NEIGHBOR_RANGE parent chunk contents as local context."""
    start = max(0, group_index - NEIGHBOR_RANGE)
    end = min(len(chunk_groups), group_index + NEIGHBOR_RANGE + 1)
    parts = []
    for i in range(start, end):
        if i != group_index:
            parts.append(chunk_groups[i].parent.content[:500])  # Truncate long parents
    return "\n---\n".join(parts)


async def enrich_chunks_with_summaries(
    chunk_groups: list[ParentChildChunks],
    doc_summary: str,
    section_summaries: list[dict],
) -> list[ParentChildChunks]:
    """Enrich all chunks using two-pass method: summaries + local context (Pass 2)."""
    client = EnrichmentClient()
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)

    async def enrich_one(chunk_result, group_index: int):
        async with semaphore:
            section_ctx = _find_section_summary(chunk_result.content, section_summaries)
            neighbors = _get_neighbors(chunk_groups, group_index)
            context = await client.generate_context_with_summary(
                doc_summary, section_ctx, neighbors, chunk_result.content
            )
            if context:
                chunk_result.context_prefix = context

    tasks = []
    for i, group in enumerate(chunk_groups):
        tasks.append(enrich_one(group.parent, i))
        for child in group.children:
            tasks.append(enrich_one(child, i))

    await asyncio.gather(*tasks)
    return chunk_groups
```

- [ ] **Step 6: Run enrichment tests**

Run: `uv run pytest tests/test_two_pass_enrichment.py -v`
Expected: All tests PASS

- [ ] **Step 7: Run full test suite for regressions**

Run: `uv run pytest tests/ -v`
Expected: All tests PASS (existing `enrich_chunks` is preserved, mock in conftest still works)

- [ ] **Step 8: Commit**

```bash
git add src/agentdrive/enrichment/client.py src/agentdrive/enrichment/contextual.py \
  tests/test_two_pass_enrichment.py
git commit -m "feat: add two-pass enrichment with document summaries and local context"
```

---

### Task 4: Update Schema for Progress Fields

**Files:**
- Modify: `src/agentdrive/schemas/files.py`
- Create: `tests/test_schema_progress.py`

- [ ] **Step 1: Write test for progress fields in FileDetailResponse**

```python
# tests/test_schema_progress.py
from agentdrive.schemas.files import FileDetailResponse
import uuid
from datetime import datetime


def test_file_detail_response_includes_progress():
    data = {
        "id": uuid.uuid4(),
        "filename": "test.pdf",
        "content_type": "pdf",
        "file_size": 1000,
        "status": "processing",
        "collection_id": None,
        "extra_metadata": {},
        "created_at": datetime.now(),
        "chunk_count": 0,
        "total_batches": 17,
        "completed_batches": 12,
        "current_phase": "enriching",
    }
    response = FileDetailResponse.model_validate(data)
    assert response.total_batches == 17
    assert response.completed_batches == 12
    assert response.current_phase == "enriching"


def test_file_detail_response_defaults_progress():
    data = {
        "id": uuid.uuid4(),
        "filename": "test.pdf",
        "content_type": "pdf",
        "file_size": 1000,
        "status": "ready",
        "collection_id": None,
        "extra_metadata": {},
        "created_at": datetime.now(),
    }
    response = FileDetailResponse.model_validate(data)
    assert response.total_batches == 0
    assert response.completed_batches == 0
    assert response.current_phase is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_schema_progress.py -v`
Expected: FAIL — `ValidationError: ... total_batches ...`

- [ ] **Step 3: Add progress fields to FileDetailResponse**

Modify `src/agentdrive/schemas/files.py` — add to `FileDetailResponse`:

```python
    total_batches: int = 0
    completed_batches: int = 0
    current_phase: str | None = None
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_schema_progress.py -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/agentdrive/schemas/files.py tests/test_schema_progress.py
git commit -m "feat: add batch progress fields to file detail response schema"
```

---

### Task 5: Rewrite Ingest Pipeline — Phase-Based Architecture

This is the core task. The new `process_file` orchestrates four phases with resume support.

**Important design note:** Sub-project 1 creates exactly one `FileBatch` per file. The phase code does NOT loop over multiple batches — it processes all chunks for the file in each phase. True per-batch processing (with a `batch_id` FK on `Chunk`) will be added in sub-project 2 when Document AI batch API introduces real multi-batch splitting.

**Files:**
- Modify: `src/agentdrive/services/ingest.py`
- Modify: `src/agentdrive/config.py`
- Create: `tests/test_incremental_ingest.py`

- [ ] **Step 1: Write test for full pipeline — small doc**

```python
# tests/test_incremental_ingest.py
import uuid
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from agentdrive.chunking.base import ChunkResult, ParentChildChunks
from agentdrive.models.file import File
from agentdrive.models.file_batch import FileBatch
from agentdrive.models.file_summary import FileSummary
from agentdrive.models.tenant import Tenant
from agentdrive.models.types import BatchStatus, FileStatus
from agentdrive.services.ingest import process_file
from sqlalchemy import select


def _make_chunk_groups(n: int) -> list[ParentChildChunks]:
    """Create n chunk groups for testing."""
    return [
        ParentChildChunks(
            parent=ChunkResult(
                content=f"Parent content {i}",
                context_prefix="",
                token_count=10,
                content_type="text",
            ),
            children=[
                ChunkResult(
                    content=f"Child content {i}",
                    context_prefix="",
                    token_count=5,
                    content_type="text",
                ),
            ],
        )
        for i in range(n)
    ]


@pytest.mark.asyncio
async def test_full_pipeline_creates_batches_and_ready(db_session):
    """Full pipeline: chunk -> summarize -> enrich -> embed -> ready."""
    tenant = Tenant(name="test")
    db_session.add(tenant)
    await db_session.flush()

    file = File(
        tenant_id=tenant.id,
        filename="test.pdf",
        content_type="pdf",
        gcs_path="tenants/x/files/y/test.pdf",
        file_size=1000,
    )
    db_session.add(file)
    await db_session.commit()

    chunk_groups = _make_chunk_groups(3)

    with patch("agentdrive.services.ingest.StorageService") as MockStorage, \
         patch("agentdrive.services.ingest.registry") as mock_registry, \
         patch("agentdrive.services.ingest.generate_document_summary") as mock_summary, \
         patch("agentdrive.services.ingest.enrich_chunks_with_summaries") as mock_enrich, \
         patch("agentdrive.services.ingest.generate_table_aliases") as mock_aliases, \
         patch("agentdrive.services.ingest.embed_file_chunks") as mock_embed_chunks, \
         patch("agentdrive.services.ingest.embed_file_aliases") as mock_embed_aliases:

        MockStorage.return_value.download_to_tempfile.return_value = Path("/tmp/fake.pdf")
        mock_registry.chunk_file.return_value = chunk_groups
        mock_summary.return_value = {"document_summary": "Test doc", "section_summaries": []}
        mock_enrich.return_value = chunk_groups
        mock_aliases.return_value = []
        mock_embed_chunks.return_value = 0
        mock_embed_aliases.return_value = 0

        await process_file(file.id, db_session)

    await db_session.refresh(file)
    assert file.status == FileStatus.READY
    assert file.current_phase is None
    assert file.total_batches == 1

    # Verify batch
    result = await db_session.execute(select(FileBatch).where(FileBatch.file_id == file.id))
    batches = result.scalars().all()
    assert len(batches) == 1
    assert batches[0].chunking_status == BatchStatus.COMPLETED
    assert batches[0].enrichment_status == BatchStatus.COMPLETED
    assert batches[0].embedding_status == BatchStatus.COMPLETED

    # Verify summary
    result = await db_session.execute(select(FileSummary).where(FileSummary.file_id == file.id))
    assert result.scalar_one_or_none() is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_incremental_ingest.py::test_full_pipeline_creates_batches_and_ready -v`
Expected: FAIL — new imports don't exist in `ingest.py`

- [ ] **Step 3: Write test for resume from Phase 2**

```python
# Add to tests/test_incremental_ingest.py
from agentdrive.models.chunk import Chunk, ParentChunk


@pytest.mark.asyncio
async def test_resume_from_phase2_skips_chunking(db_session):
    """If all batches are chunked but no summary exists, resume from Phase 2."""
    tenant = Tenant(name="test")
    db_session.add(tenant)
    await db_session.flush()

    file = File(
        tenant_id=tenant.id,
        filename="test.pdf",
        content_type="pdf",
        gcs_path="tenants/x/files/y/test.pdf",
        file_size=1000,
        status=FileStatus.PROCESSING,
        total_batches=1,
    )
    db_session.add(file)
    await db_session.flush()

    # Simulate Phase 1 already completed
    batch = FileBatch(
        file_id=file.id,
        batch_index=0,
        chunking_status=BatchStatus.COMPLETED,
        chunk_count=1,
    )
    db_session.add(batch)

    parent = ParentChunk(file_id=file.id, content="Test parent", token_count=5)
    db_session.add(parent)
    await db_session.flush()

    chunk = Chunk(
        file_id=file.id,
        parent_chunk_id=parent.id,
        chunk_index=0,
        content="Test child",
        context_prefix="",
        token_count=5,
        content_type="text",
    )
    db_session.add(chunk)
    await db_session.commit()

    with patch("agentdrive.services.ingest.StorageService") as MockStorage, \
         patch("agentdrive.services.ingest.registry") as mock_registry, \
         patch("agentdrive.services.ingest.generate_document_summary") as mock_summary, \
         patch("agentdrive.services.ingest.enrich_chunks_with_summaries") as mock_enrich, \
         patch("agentdrive.services.ingest.generate_table_aliases") as mock_aliases, \
         patch("agentdrive.services.ingest.embed_file_chunks") as mock_embed_chunks, \
         patch("agentdrive.services.ingest.embed_file_aliases") as mock_embed_aliases:

        mock_summary.return_value = {"document_summary": "Test", "section_summaries": []}
        mock_enrich.return_value = [
            ParentChildChunks(
                parent=ChunkResult(content="Test parent", context_prefix="enriched", token_count=5, content_type="text"),
                children=[ChunkResult(content="Test child", context_prefix="enriched", token_count=5, content_type="text")],
            )
        ]
        mock_aliases.return_value = []
        mock_embed_chunks.return_value = 0
        mock_embed_aliases.return_value = 0

        await process_file(file.id, db_session)

    # Should NOT have called chunk_file (Phase 1 skipped)
    mock_registry.chunk_file.assert_not_called()
    # Should have called summary (Phase 2)
    mock_summary.assert_called_once()

    await db_session.refresh(file)
    assert file.status == FileStatus.READY


@pytest.mark.asyncio
async def test_zero_chunks_marks_failed(db_session):
    """File producing zero chunks is marked FAILED, no further phases run."""
    tenant = Tenant(name="test")
    db_session.add(tenant)
    await db_session.flush()

    file = File(
        tenant_id=tenant.id,
        filename="empty.pdf",
        content_type="pdf",
        gcs_path="tenants/x/files/y/empty.pdf",
        file_size=100,
    )
    db_session.add(file)
    await db_session.commit()

    with patch("agentdrive.services.ingest.StorageService") as MockStorage, \
         patch("agentdrive.services.ingest.registry") as mock_registry, \
         patch("agentdrive.services.ingest.generate_document_summary") as mock_summary:

        MockStorage.return_value.download_to_tempfile.return_value = Path("/tmp/fake.pdf")
        mock_registry.chunk_file.return_value = []  # Zero chunks

        await process_file(file.id, db_session)

    await db_session.refresh(file)
    assert file.status == FileStatus.FAILED
    # Summarization should NOT have been called
    mock_summary.assert_not_called()
```

- [ ] **Step 4: Add max_retries to config**

Add to `src/agentdrive/config.py`:

```python
    max_retries: int = 3
```

- [ ] **Step 5: Rewrite ingest.py with phase-based pipeline**

Replace `src/agentdrive/services/ingest.py`:

```python
import logging
import os
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentdrive.chunking.base import ChunkResult, ParentChildChunks
from agentdrive.chunking.registry import ChunkerRegistry
from agentdrive.chunking.tokens import count_tokens
from agentdrive.embedding.pipeline import embed_file_chunks, embed_file_aliases
from agentdrive.enrichment.contextual import (
    enrich_chunks_with_summaries,
    generate_document_summary,
)
from agentdrive.enrichment.table_questions import generate_table_aliases
from agentdrive.models.chunk import Chunk, ParentChunk
from agentdrive.models.chunk_alias import ChunkAlias
from agentdrive.models.file import File
from agentdrive.models.file_batch import FileBatch
from agentdrive.models.file_summary import FileSummary
from agentdrive.models.types import BatchStatus, FileStatus
from agentdrive.services.storage import StorageService

logger = logging.getLogger(__name__)
registry = ChunkerRegistry()


async def process_file(file_id: uuid.UUID, session: AsyncSession) -> None:
    result = await session.execute(select(File).where(File.id == file_id))
    file = result.scalar_one_or_none()
    if not file:
        logger.error(f"File {file_id} not found")
        return

    file.status = FileStatus.PROCESSING
    await session.commit()

    try:
        # Determine resume point
        batch = await _get_batch(file_id, session)
        summary = await _get_summary(file_id, session)

        chunking_done = batch and batch.chunking_status == BatchStatus.COMPLETED
        enrichment_done = batch and batch.enrichment_status == BatchStatus.COMPLETED
        embedding_done = batch and batch.embedding_status == BatchStatus.COMPLETED

        # Phase 1: Chunking
        if not chunking_done:
            file.current_phase = "chunking"
            await session.commit()
            await _phase1_chunking(file, session)
            # Re-check: phase1 may have marked file as FAILED (0 chunks)
            await session.refresh(file)
            if file.status == FileStatus.FAILED:
                return
            batch = await _get_batch(file_id, session)

        # Phase 2: Summarization
        if not summary:
            file.current_phase = "summarizing"
            await session.commit()
            summary = await _phase2_summarization(file, session)

        # Phase 3: Enrichment + Table Aliases
        batch = await _get_batch(file_id, session)
        if not (batch and batch.enrichment_status == BatchStatus.COMPLETED):
            file.current_phase = "enriching"
            await session.commit()
            await _phase3_enrichment(file, summary, batch, session)

        # Phase 4: Embedding
        batch = await _get_batch(file_id, session)
        if not (batch and batch.embedding_status == BatchStatus.COMPLETED):
            file.current_phase = "embedding"
            await session.commit()
            await _phase4_embedding(file, batch, session)

        # Done
        file.status = FileStatus.READY
        file.current_phase = None
        file.completed_batches = file.total_batches
        await session.commit()
        logger.info(f"File {file_id} processed successfully")

    except Exception as e:
        logger.exception(f"Failed to process file {file_id}: {e}")
        await session.rollback()
        result = await session.execute(select(File).where(File.id == file_id))
        file = result.scalar_one_or_none()
        if file:
            file.status = FileStatus.FAILED
            file.retry_count = (file.retry_count or 0) + 1
            await session.commit()


async def _get_batch(file_id: uuid.UUID, session: AsyncSession) -> FileBatch | None:
    """Get the single batch for a file (sub-project 1 creates exactly one)."""
    result = await session.execute(
        select(FileBatch).where(FileBatch.file_id == file_id)
    )
    return result.scalar_one_or_none()


async def _get_summary(file_id: uuid.UUID, session: AsyncSession) -> FileSummary | None:
    result = await session.execute(
        select(FileSummary).where(FileSummary.file_id == file_id)
    )
    return result.scalar_one_or_none()


async def _phase1_chunking(file: File, session: AsyncSession) -> None:
    """Phase 1: Download file, chunk it, commit chunks and batch record."""
    storage = StorageService()
    temp_path: Path | None = None

    try:
        temp_path = storage.download_to_tempfile(file.gcs_path)
        chunk_groups = registry.chunk_file(file.content_type, temp_path, file.filename)

        if not chunk_groups:
            logger.warning(f"File {file.id} produced 0 chunks — marking as failed")
            file.status = FileStatus.FAILED
            await session.commit()
            return

        # Create single batch record (multi-batch comes in sub-project 2)
        batch = FileBatch(
            file_id=file.id,
            batch_index=0,
            chunking_status=BatchStatus.PROCESSING,
            chunk_count=0,
        )
        session.add(batch)
        await session.flush()

        chunk_index = 0
        for group in chunk_groups:
            parent_record = ParentChunk(
                file_id=file.id,
                content=group.parent.content,
                token_count=group.parent.token_count,
            )
            session.add(parent_record)
            await session.flush()

            for child in group.children:
                chunk_record = Chunk(
                    file_id=file.id,
                    parent_chunk_id=parent_record.id,
                    chunk_index=chunk_index,
                    content=child.content,
                    context_prefix=child.context_prefix,
                    token_count=child.token_count,
                    content_type=child.content_type,
                )
                session.add(chunk_record)
                chunk_index += 1

            await session.flush()

        batch.chunking_status = BatchStatus.COMPLETED
        batch.chunk_count = chunk_index
        file.total_batches = 1
        file.completed_batches = 1
        await session.commit()
        logger.info(f"Phase 1 complete for file {file.id}: {chunk_index} chunks")

    finally:
        if temp_path and temp_path.exists():
            os.unlink(temp_path)


async def _phase2_summarization(file: File, session: AsyncSession) -> FileSummary:
    """Phase 2: Generate document + section summaries from all chunks."""
    result = await session.execute(
        select(ParentChunk)
        .where(ParentChunk.file_id == file.id)
        .order_by(ParentChunk.created_at)
    )
    parents = result.scalars().all()
    document_text = "\n\n".join(p.content for p in parents)

    summary_data = await generate_document_summary(document_text)

    summary = FileSummary(
        file_id=file.id,
        document_summary=summary_data.get("document_summary", ""),
        section_summaries=summary_data.get("section_summaries", []),
    )
    session.add(summary)
    await session.commit()
    logger.info(f"Phase 2 complete for file {file.id}: summary generated")
    return summary


async def _phase3_enrichment(
    file: File, summary: FileSummary, batch: FileBatch, session: AsyncSession
) -> None:
    """Phase 3: Enrich all chunks using summaries + local context, generate table aliases."""
    batch.enrichment_status = BatchStatus.PROCESSING
    await session.commit()

    # Load all chunks as ParentChildChunks for enrichment
    chunk_groups = await _load_chunk_groups(file.id, session)

    # Enrich with two-pass method
    chunk_groups = await enrich_chunks_with_summaries(
        chunk_groups,
        summary.document_summary,
        summary.section_summaries,
    )

    # Write enriched context_prefix back to DB, tracking by chunk_index
    all_chunks_result = await session.execute(
        select(Chunk)
        .where(Chunk.file_id == file.id)
        .order_by(Chunk.chunk_index)
    )
    db_chunks = list(all_chunks_result.scalars().all())

    # Build flat list of enriched children in chunk_index order
    enriched_children = []
    for group in chunk_groups:
        enriched_children.extend(group.children)

    for db_chunk, enriched in zip(db_chunks, enriched_children):
        db_chunk.context_prefix = enriched.context_prefix

    # Generate table aliases
    table_aliases = await generate_table_aliases(chunk_groups)

    # Build chunk content -> DB id mapping for alias assignment
    chunk_content_to_id: dict[tuple[str, int], uuid.UUID] = {}
    for c in db_chunks:
        chunk_content_to_id[(c.content, c.chunk_index)] = c.id

    for alias_data in table_aliases:
        alias_chunk = alias_data["chunk"]
        # Find matching DB chunk by content; fallback to first match
        target_id = None
        for c in db_chunks:
            if c.content == alias_chunk.content:
                target_id = c.id
                break
        if not target_id:
            logger.warning(f"Could not find DB chunk for table alias, skipping")
            continue

        alias_record = ChunkAlias(
            chunk_id=target_id,
            file_id=file.id,
            content=alias_data["question"],
            token_count=count_tokens(alias_data["question"]),
        )
        session.add(alias_record)

    batch.enrichment_status = BatchStatus.COMPLETED
    await session.commit()
    logger.info(f"Phase 3 complete for file {file.id}")


async def _load_chunk_groups(
    file_id: uuid.UUID, session: AsyncSession
) -> list[ParentChildChunks]:
    """Reconstruct ParentChildChunks from DB records."""
    parents_result = await session.execute(
        select(ParentChunk)
        .where(ParentChunk.file_id == file_id)
        .order_by(ParentChunk.created_at)
    )
    parents = parents_result.scalars().all()

    groups = []
    for parent in parents:
        children_result = await session.execute(
            select(Chunk)
            .where(Chunk.parent_chunk_id == parent.id)
            .order_by(Chunk.chunk_index)
        )
        children = children_result.scalars().all()

        groups.append(
            ParentChildChunks(
                parent=ChunkResult(
                    content=parent.content,
                    context_prefix="",
                    token_count=parent.token_count,
                    content_type="text",
                ),
                children=[
                    ChunkResult(
                        content=c.content,
                        context_prefix=c.context_prefix,
                        token_count=c.token_count,
                        content_type=c.content_type,
                    )
                    for c in children
                ],
            )
        )

    return groups


async def _phase4_embedding(
    file: File, batch: FileBatch, session: AsyncSession
) -> None:
    """Phase 4: Embed all chunks and aliases for the file."""
    batch.embedding_status = BatchStatus.PROCESSING
    await session.commit()

    await embed_file_chunks(file.id, session)
    await embed_file_aliases(file.id, session)

    batch.embedding_status = BatchStatus.COMPLETED
    await session.commit()
    logger.info(f"Phase 4 complete for file {file.id}")
```

- [ ] **Step 6: Update conftest.py mocks for new ingest imports**

The ingest rewrite imports `enrich_chunks_with_summaries` and `generate_document_summary` instead of `enrich_chunks`. Update the autouse mock in `tests/conftest.py`:

```python
@pytest.fixture(autouse=True)
def mock_enrichment_and_embedding():
    """Prevent real API calls during tests."""
    async def _noop_embed(*args, **kwargs) -> int:
        return 0

    async def _noop_enrich(groups, *args, **kwargs):
        return groups

    async def _noop_aliases(groups):
        return []

    async def _noop_summary(text):
        return {"document_summary": "", "section_summaries": []}

    with patch("agentdrive.services.ingest.embed_file_chunks", side_effect=_noop_embed), \
         patch("agentdrive.services.ingest.embed_file_aliases", side_effect=_noop_embed), \
         patch("agentdrive.services.ingest.enrich_chunks_with_summaries", side_effect=_noop_enrich), \
         patch("agentdrive.services.ingest.generate_document_summary", side_effect=_noop_summary), \
         patch("agentdrive.services.ingest.generate_table_aliases", side_effect=_noop_aliases):
        yield
```

**Note:** The old `enrich_chunks` is no longer imported in `ingest.py`, so the old mock target `agentdrive.services.ingest.enrich_chunks` is gone. Verify no other test files patch through that path. If they do, update them.

- [ ] **Step 7: Run incremental ingest tests**

Run: `uv run pytest tests/test_incremental_ingest.py -v`
Expected: All tests PASS

- [ ] **Step 8: Run full test suite for regressions**

Run: `uv run pytest tests/ -v`
Expected: All tests PASS. If existing tests fail because they patched `enrich_chunks` through `ingest`, update those patches to the new function names.

- [ ] **Step 9: Commit**

```bash
git add src/agentdrive/services/ingest.py src/agentdrive/config.py \
  tests/test_incremental_ingest.py tests/conftest.py
git commit -m "feat: rewrite ingest pipeline with four-phase architecture and resume support"
```

---

### Task 6: Update Queue Worker for Resume Support

**Files:**
- Modify: `src/agentdrive/services/queue.py`
- Create: `tests/test_queue_resume.py`

- [ ] **Step 1: Write test for worker accepting FAILED files for retry**

```python
# tests/test_queue_resume.py
import pytest
from agentdrive.models.file import File
from agentdrive.models.tenant import Tenant
from agentdrive.models.types import FileStatus
from agentdrive.config import settings


def test_max_retries_config():
    """max_retries config defaults to 3."""
    assert settings.max_retries == 3
```

- [ ] **Step 2: Update worker to accept FAILED files with retry_count < max_retries**

Modify `src/agentdrive/services/queue.py` — the worker currently skips files that aren't PENDING. Update the status check:

```python
                if not file or file.status not in (FileStatus.PENDING, FileStatus.FAILED):
                    logger.info(
                        f"Skipping file {file_id} "
                        f"(status={file.status if file else 'not found'})"
                    )
                    continue

                if file.status == FileStatus.FAILED:
                    if (file.retry_count or 0) >= settings.max_retries:
                        logger.warning(
                            f"File {file_id} exceeded max retries ({settings.max_retries}), skipping"
                        )
                        continue
                    logger.info(f"Retrying failed file {file_id} (attempt {(file.retry_count or 0) + 1})")
```

Also remove the duplicate error handling in the worker's `except Exception` block — `process_file` now handles its own error state. Replace the inner try/except with:

```python
                try:
                    await asyncio.wait_for(
                        process_file(file_id, session),
                        timeout=settings.ingestion_timeout_seconds,
                    )
                except asyncio.TimeoutError:
                    await session.rollback()
                    file = await session.get(File, file_id)
                    if file:
                        file.status = FileStatus.FAILED
                        file.retry_count = (file.retry_count or 0) + 1
                        file.extra_metadata = {
                            **(file.extra_metadata or {}),
                            "error": f"Ingestion timed out after {settings.ingestion_timeout_seconds}s",
                        }
                        await session.commit()
                    logger.error(f"File {file_id} timed out")
                except Exception:
                    # process_file handles its own error state;
                    # this catches errors outside process_file (e.g., session creation)
                    logger.exception(f"Unexpected error processing file {file_id}")
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/test_queue_resume.py -v`
Expected: PASS

- [ ] **Step 4: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/agentdrive/services/queue.py tests/test_queue_resume.py
git commit -m "feat: update queue worker to support retry of failed files with resume"
```

---

### Task 7: Integration Test — Full Pipeline End-to-End

**Files:**
- Create: `tests/test_integration_incremental.py`

- [ ] **Step 1: Write integration test for small doc (single batch)**

```python
# tests/test_integration_incremental.py
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


@pytest.mark.asyncio
async def test_full_pipeline_small_doc(db_session):
    """Full pipeline for a small doc: chunk -> summarize -> enrich -> embed -> ready."""
    tenant = Tenant(name="test")
    db_session.add(tenant)
    await db_session.flush()

    file = File(
        tenant_id=tenant.id,
        filename="small.pdf",
        content_type="pdf",
        gcs_path="tenants/x/files/y/small.pdf",
        file_size=500,
    )
    db_session.add(file)
    await db_session.commit()

    chunk_groups = [
        ParentChildChunks(
            parent=ChunkResult(content="About widgets", context_prefix="", token_count=5, content_type="text"),
            children=[
                ChunkResult(content="Widgets cost $50", context_prefix="", token_count=5, content_type="text"),
            ],
        ),
    ]

    with patch("agentdrive.services.ingest.StorageService") as MockStorage, \
         patch("agentdrive.services.ingest.registry") as mock_registry:
        MockStorage.return_value.download_to_tempfile.return_value = Path("/tmp/fake.pdf")
        mock_registry.chunk_file.return_value = chunk_groups
        # autouse conftest mock handles enrich/embed/summary as no-ops

        await process_file(file.id, db_session)

    await db_session.refresh(file)
    assert file.status == FileStatus.READY
    assert file.total_batches == 1
    assert file.current_phase is None

    # Verify chunks in DB
    chunks_result = await db_session.execute(select(Chunk).where(Chunk.file_id == file.id))
    chunks = chunks_result.scalars().all()
    assert len(chunks) == 1
    assert chunks[0].content == "Widgets cost $50"

    # Verify batch tracking
    batches_result = await db_session.execute(select(FileBatch).where(FileBatch.file_id == file.id))
    batches = batches_result.scalars().all()
    assert len(batches) == 1
    assert batches[0].chunking_status == BatchStatus.COMPLETED
    assert batches[0].enrichment_status == BatchStatus.COMPLETED
    assert batches[0].embedding_status == BatchStatus.COMPLETED

    # Verify summary
    summary_result = await db_session.execute(select(FileSummary).where(FileSummary.file_id == file.id))
    summary = summary_result.scalar_one_or_none()
    assert summary is not None


@pytest.mark.asyncio
async def test_full_pipeline_resume_after_failure(db_session):
    """Pipeline resumes from correct phase after a simulated failure."""
    tenant = Tenant(name="test")
    db_session.add(tenant)
    await db_session.flush()

    file = File(
        tenant_id=tenant.id,
        filename="resume.pdf",
        content_type="pdf",
        gcs_path="tenants/x/files/y/resume.pdf",
        file_size=500,
        status=FileStatus.FAILED,
        total_batches=1,
        completed_batches=1,
    )
    db_session.add(file)
    await db_session.flush()

    # Pre-create batch (Phase 1 done)
    batch = FileBatch(
        file_id=file.id,
        batch_index=0,
        chunking_status=BatchStatus.COMPLETED,
        chunk_count=1,
    )
    db_session.add(batch)

    parent = ParentChunk(file_id=file.id, content="Resume test content", token_count=5)
    db_session.add(parent)
    await db_session.flush()

    chunk = Chunk(
        file_id=file.id,
        parent_chunk_id=parent.id,
        chunk_index=0,
        content="Resume child content",
        context_prefix="",
        token_count=5,
        content_type="text",
    )
    db_session.add(chunk)
    await db_session.commit()

    with patch("agentdrive.services.ingest.StorageService"), \
         patch("agentdrive.services.ingest.registry") as mock_registry:
        # registry.chunk_file should NOT be called (Phase 1 done)
        await process_file(file.id, db_session)
        mock_registry.chunk_file.assert_not_called()

    await db_session.refresh(file)
    assert file.status == FileStatus.READY
```

- [ ] **Step 2: Run integration tests**

Run: `uv run pytest tests/test_integration_incremental.py -v`
Expected: All tests PASS

- [ ] **Step 3: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_integration_incremental.py
git commit -m "test: add integration tests for incremental pipeline and resume"
```

---

### Task 8: Regression Verification + Cleanup

**Files:**
- No new files — verification and cleanup only

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 2: Verify search still filters by file status**

Run: `grep -rn "status.*ready\|FileStatus.READY" src/agentdrive/search/`
Expected: Search queries filter on `file.status == 'ready'`, confirming partial chunks won't leak. This is a **correctness dependency** — document in a code comment if not already present.

- [ ] **Step 3: Verify no dead imports or unused code**

Run: `uv run ruff check src/agentdrive/ --select F401,F841`
Expected: No unused import or variable warnings related to our changes.

- [ ] **Step 4: Final commit if any cleanup needed**

```bash
git add -u
git commit -m "chore: cleanup unused imports and fix lint issues"
```
