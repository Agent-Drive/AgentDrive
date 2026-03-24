# Reducto PDF Parsing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace broken Docling PDF parser with Reducto cloud API, eliminating runtime model downloads, heavy Docker dependencies, and production failures.

**Architecture:** `PdfChunker` calls Reducto's `/parse` API via their Python SDK, passing a GCS signed URL (or uploading bytes as fallback). Reducto returns markdown which feeds into the existing `MarkdownChunker`. No changes to the chunking hierarchy, enrichment, or embedding pipeline.

**Tech Stack:** Python 3.12, reductoai SDK, google-cloud-storage (signed URLs), FastAPI, pytest

**Spec:** `docs/superpowers/specs/2026-03-24-reducto-pdf-parsing-design.md`

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `src/agentdrive/config.py` | Add `reducto_api_key` setting |
| Modify | `src/agentdrive/services/storage.py` | Add `generate_signed_url` method |
| Modify | `src/agentdrive/chunking/pdf.py` | Replace Docling with Reducto SDK call |
| Modify | `src/agentdrive/services/ingest.py` | Generate signed URL, pass via metadata |
| Modify | `pyproject.toml` | Swap `docling` for `reductoai` |
| Create | `tests/test_pdf_chunker.py` | Unit tests for Reducto-based PDF chunker |
| Modify | `tests/test_ingest.py` | Add Reducto mock if needed |

---

### Task 1: Add Reducto config and swap dependency

**Files:**
- Modify: `src/agentdrive/config.py:16-18`
- Modify: `pyproject.toml:21`

- [ ] **Step 1: Add `reducto_api_key` to config.py**

Add after `reaper_threshold_minutes: int = 10` (line 18):

```python
    reducto_api_key: str = ""
```

- [ ] **Step 2: Swap dependency in pyproject.toml**

Change line 21 from:
```toml
    "docling>=2.15.0",
```
To:
```toml
    "reductoai>=0.16.0,<1.0",
```

- [ ] **Step 3: Install the new dependency**

Run: `uv pip install -e ".[dev]"`

Verify: `uv run python -c "from reducto import Reducto; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add src/agentdrive/config.py pyproject.toml
git commit -m "feat: add reducto_api_key config, swap docling for reductoai dependency"
```

---

### Task 2: Add signed URL generation to StorageService

**Files:**
- Modify: `src/agentdrive/services/storage.py`
- Create: `tests/test_storage_signed_url.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_storage_signed_url.py`:

```python
from unittest.mock import MagicMock, patch

from agentdrive.services.storage import StorageService


@patch("agentdrive.services.storage.storage_client")
def test_generate_signed_url(mock_client):
    """generate_signed_url should call blob.generate_signed_url with correct params."""
    mock_blob = MagicMock()
    mock_blob.generate_signed_url.return_value = "https://storage.googleapis.com/signed"
    mock_bucket = MagicMock()
    mock_bucket.blob.return_value = mock_blob
    mock_client.bucket.return_value = mock_bucket

    storage = StorageService()
    url = storage.generate_signed_url("tenants/abc/files/def/test.pdf")

    assert url == "https://storage.googleapis.com/signed"
    mock_bucket.blob.assert_called_once_with("tenants/abc/files/def/test.pdf")
    mock_blob.generate_signed_url.assert_called_once()
    call_kwargs = mock_blob.generate_signed_url.call_args[1]
    assert call_kwargs["version"] == "v4"
    assert call_kwargs["method"] == "GET"
```

- [ ] **Step 2: Run test — verify it fails**

Run: `uv run pytest tests/test_storage_signed_url.py -v -x`
Expected: FAIL — `AttributeError: 'StorageService' object has no attribute 'generate_signed_url'`

- [ ] **Step 3: Implement generate_signed_url**

Add to `src/agentdrive/services/storage.py`, after the `delete` method:

```python
    def generate_signed_url(self, gcs_path: str, expiration_minutes: int = 30) -> str:
        """Generate a V4 signed URL for read access."""
        from datetime import timedelta

        blob = self._bucket.blob(gcs_path)
        return blob.generate_signed_url(
            version="v4",
            expiration=timedelta(minutes=expiration_minutes),
            method="GET",
        )
```

- [ ] **Step 4: Run test — verify it passes**

Run: `uv run pytest tests/test_storage_signed_url.py -v -x`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/agentdrive/services/storage.py tests/test_storage_signed_url.py
git commit -m "feat: add generate_signed_url to StorageService"
```

---

### Task 3: Rewrite PdfChunker to use Reducto — tests first

**Dependency:** Task 1 must be completed first — `reductoai` must be installed before this task rewrites `pdf.py` to `from reducto import Reducto`. If the dependency isn't installed, the entire `ChunkerRegistry` fails to import, breaking all tests and app startup.

**Files:**
- Create: `tests/test_pdf_chunker.py`
- Modify: `src/agentdrive/chunking/pdf.py`

- [ ] **Step 1: Write test for happy path**

Create `tests/test_pdf_chunker.py`:

```python
from unittest.mock import MagicMock, patch

import pytest

from agentdrive.chunking.pdf import PdfChunker


@patch("agentdrive.chunking.pdf.Reducto")
def test_pdf_chunker_happy_path(mock_reducto_cls):
    """PdfChunker should call Reducto, get markdown, and produce ParentChildChunks."""
    # Mock Reducto response with one chunk containing markdown
    mock_chunk = MagicMock()
    mock_chunk.content = "# Test Document\n\nThis is a test paragraph with enough content to produce chunks."

    mock_result = MagicMock()
    mock_result.result.chunks = [mock_chunk]

    mock_client = MagicMock()
    mock_client.parse.run.return_value = mock_result
    mock_reducto_cls.return_value = mock_client

    chunker = PdfChunker()
    groups = chunker.chunk_bytes(
        b"fake pdf bytes",
        "test.pdf",
        metadata={"signed_url": "https://storage.googleapis.com/signed"},
    )

    # Verify Reducto was called with the signed URL
    mock_client.parse.run.assert_called_once()
    call_kwargs = mock_client.parse.run.call_args[1]
    assert call_kwargs["input"] == "https://storage.googleapis.com/signed"

    # Verify we got chunks back (MarkdownChunker processes the markdown)
    assert len(groups) >= 0  # May be 0 if markdown is too short for chunking


@patch("agentdrive.chunking.pdf.Reducto")
def test_pdf_chunker_empty_result(mock_reducto_cls):
    """PdfChunker should return empty list when Reducto returns no content."""
    mock_result = MagicMock()
    mock_result.result.chunks = []

    mock_client = MagicMock()
    mock_client.parse.run.return_value = mock_result
    mock_reducto_cls.return_value = mock_client

    chunker = PdfChunker()
    groups = chunker.chunk_bytes(
        b"fake pdf bytes",
        "empty.pdf",
        metadata={"signed_url": "https://storage.googleapis.com/signed"},
    )

    assert groups == []


@patch("agentdrive.chunking.pdf.Reducto")
def test_pdf_chunker_api_error_propagates(mock_reducto_cls):
    """PdfChunker should NOT swallow exceptions — let them propagate."""
    mock_client = MagicMock()
    mock_client.parse.run.side_effect = RuntimeError("Reducto API failed")
    mock_reducto_cls.return_value = mock_client

    chunker = PdfChunker()
    with pytest.raises(RuntimeError, match="Reducto API failed"):
        chunker.chunk_bytes(
            b"fake pdf bytes",
            "bad.pdf",
            metadata={"signed_url": "https://storage.googleapis.com/signed"},
        )


@patch("agentdrive.chunking.pdf.Reducto")
def test_pdf_chunker_falls_back_to_upload_without_signed_url(mock_reducto_cls):
    """When no signed_url in metadata, chunker should upload bytes directly."""
    mock_upload = MagicMock()
    mock_upload.file_id = "reducto://abc123"

    mock_chunk = MagicMock()
    mock_chunk.content = "# Uploaded Document\n\nContent from direct upload."

    mock_result = MagicMock()
    mock_result.result.chunks = [mock_chunk]

    mock_client = MagicMock()
    mock_client.upload.return_value = mock_upload
    mock_client.parse.run.return_value = mock_result
    mock_reducto_cls.return_value = mock_client

    chunker = PdfChunker()
    chunker.chunk_bytes(b"fake pdf bytes", "test.pdf", metadata={})

    # Verify upload was called as fallback
    mock_client.upload.assert_called_once()
    # Verify parse used the file_id from upload
    call_kwargs = mock_client.parse.run.call_args[1]
    assert call_kwargs["input"] == "reducto://abc123"
```

- [ ] **Step 2: Run tests — verify they fail**

Run: `uv run pytest tests/test_pdf_chunker.py -v -x`
Expected: FAIL — import errors (PdfChunker still imports Docling)

- [ ] **Step 3: Rewrite pdf.py**

Replace the entire contents of `src/agentdrive/chunking/pdf.py`:

```python
import logging

from reducto import Reducto

from agentdrive.chunking.base import BaseChunker, ParentChildChunks
from agentdrive.chunking.markdown import MarkdownChunker
from agentdrive.config import settings

logger = logging.getLogger(__name__)


class PdfChunker(BaseChunker):
    def __init__(self) -> None:
        self._markdown_chunker = MarkdownChunker()

    def supported_types(self) -> list[str]:
        return ["pdf"]

    def chunk(self, content: str, filename: str, metadata: dict | None = None) -> list[ParentChildChunks]:
        return []

    def chunk_bytes(self, data: bytes, filename: str, metadata: dict | None = None) -> list[ParentChildChunks]:
        client = Reducto(api_key=settings.reducto_api_key)
        metadata = metadata or {}

        # Use signed URL if available, otherwise upload bytes directly
        signed_url = metadata.get("signed_url")
        if signed_url:
            input_source = signed_url
        else:
            logger.info(f"PDF {filename}: no signed_url in metadata, uploading bytes directly")
            upload_response = client.upload(file=(filename, data, "application/pdf"))
            input_source = upload_response.file_id

        # ocr_system defaults to "standard" in Reducto (1 credit/page) — no need to set explicitly
        result = client.parse.run(
            input=input_source,
            formatting={"table_output_format": "dynamic"},
        )

        # Concatenate all chunk contents into a single markdown string
        chunks = result.result.chunks
        if not chunks:
            logger.warning(f"PDF {filename}: Reducto returned no chunks")
            return []

        markdown = "\n\n".join(chunk.content for chunk in chunks)
        if not markdown.strip():
            logger.warning(f"PDF {filename}: Reducto returned empty markdown")
            return []

        return self._markdown_chunker.chunk(markdown, filename, metadata)
```

- [ ] **Step 4: Run tests — verify they pass**

Run: `uv run pytest tests/test_pdf_chunker.py -v -x`
Expected: All 4 tests pass.

- [ ] **Step 5: Run existing tests to check for regressions**

Run: `uv run pytest tests/ -v -x --ignore=tests/test_pdf_chunker.py`

Note: If `test_ingest.py` fails because Docling imports are gone, that's expected and will be fixed in Task 5. For now, verify `test_files.py`, `test_queue.py`, and other tests still pass.

- [ ] **Step 6: Commit**

```bash
git add src/agentdrive/chunking/pdf.py tests/test_pdf_chunker.py
git commit -m "feat: replace Docling with Reducto SDK in PdfChunker"
```

---

### Task 4: Update ingest.py to pass signed URL via metadata

**Files:**
- Modify: `src/agentdrive/services/ingest.py:31-35`

- [ ] **Step 1: Update process_file to generate signed URL**

In `src/agentdrive/services/ingest.py`, change lines 31-35 from:

```python
        storage = StorageService()
        data = storage.download(file.gcs_path)

        chunker = registry.get_chunker(file.content_type)
        chunk_groups = chunker.chunk_bytes(data, file.filename)
```

To:

```python
        storage = StorageService()
        data = storage.download(file.gcs_path)

        # Generate signed URL for chunkers that use external APIs (e.g., PdfChunker → Reducto)
        signed_url = storage.generate_signed_url(file.gcs_path)

        chunker = registry.get_chunker(file.content_type)
        chunk_groups = chunker.chunk_bytes(
            data, file.filename,
            metadata={"gcs_path": file.gcs_path, "signed_url": signed_url},
        )
```

- [ ] **Step 2: Update test_ingest.py mock for generate_signed_url**

The existing ingest tests mock `StorageService` as a `MagicMock`. The new `generate_signed_url` call will auto-return a `MagicMock` object (not a string), which propagates into chunk metadata. Add an explicit return value to each test that creates a `mock_storage`:

```python
mock_storage.generate_signed_url.return_value = "https://mock-signed-url.com"
```

Add this line in every test in `test_ingest.py` where `mock_storage` is set up (look for `mock_storage_cls.return_value = mock_storage` patterns).

Note: The existing ingest tests use `content_type="markdown"`, so `PdfChunker` is never reached — the `MarkdownChunker` handles these. The signed URL mock is still needed because `generate_signed_url` is called for ALL file types in `ingest.py`, even though only `PdfChunker` uses it.

- [ ] **Step 3: Run all tests**

Run: `uv run pytest tests/ -v -x`
Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
git add src/agentdrive/services/ingest.py tests/test_ingest.py
git commit -m "feat: pass GCS signed URL to chunkers via metadata"
```

---

### Task 5: Clean up — Dockerfile, conftest, verify full suite

**Files:**
- Modify: `Dockerfile` (if Docling system deps exist)
- Modify: `tests/conftest.py` (add Reducto mock if needed)
- Modify: `tests/test_ingest.py` (update mocks if needed)

- [ ] **Step 1: Check Dockerfile for Docling-specific deps**

Read `Dockerfile`. Currently it only has `libpq-dev` and `gcc` — no Docling-specific system deps. No change needed. But verify after `docling` is removed that `pip install .` still succeeds.

- [ ] **Step 2: Check if test_ingest.py needs Reducto mocking**

Read `tests/test_ingest.py`. If any test triggers `PdfChunker.chunk_bytes`, it will call the Reducto SDK for real. Check whether:
- Tests use PDF content type (triggering PdfChunker)
- The `conftest.py` autouse fixtures mock at the chunker level

If PDF chunking is reached in ingest tests, add a mock:

```python
# In conftest.py or test_ingest.py
@pytest.fixture(autouse=True)
def mock_reducto(monkeypatch):
    """Prevent real Reducto API calls during tests."""
    mock_client = MagicMock()
    mock_chunk = MagicMock()
    mock_chunk.content = "# Mock PDF\n\nMock content."
    mock_result = MagicMock()
    mock_result.result.chunks = [mock_chunk]
    mock_client.parse.run.return_value = mock_result
    monkeypatch.setattr("agentdrive.chunking.pdf.Reducto", lambda **kwargs: mock_client)
```

Also mock `StorageService.generate_signed_url` if it's called in ingest tests:

```python
monkeypatch.setattr(
    "agentdrive.services.ingest.StorageService.generate_signed_url",
    lambda self, path: "https://mock-signed-url.com",
)
```

- [ ] **Step 3: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All tests pass.

- [ ] **Step 4: Run linting if available**

Run: `uv run ruff check src/ tests/` (skip if ruff not installed)

- [ ] **Step 5: Commit any test/mock fixes**

```bash
git add tests/ Dockerfile
git commit -m "fix: add Reducto and signed URL mocks for test suite"
```

---

### Task 6: Update .env.example and Cloud Run config

**Files:**
- Modify: `.env.example`
- Modify: `cloud-run/service.yaml` (if it exists)

- [ ] **Step 1: Add REDUCTO_API_KEY to .env.example**

Add:
```
REDUCTO_API_KEY=your-reducto-api-key
```

- [ ] **Step 2: Check if cloud-run/service.yaml needs updating**

If `cloud-run/service.yaml` exists and lists secrets, add `REDUCTO_API_KEY`. If it's managed externally (e.g., via `gcloud` commands), document the required secret in the commit message.

- [ ] **Step 3: Commit**

```bash
git add .env.example cloud-run/
git commit -m "chore: add REDUCTO_API_KEY to env config and Cloud Run secrets"
```
