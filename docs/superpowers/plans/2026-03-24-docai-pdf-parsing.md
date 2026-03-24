# Document AI PDF Parsing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace broken Docling PDF parser with Google Cloud Document AI Layout Parser, eliminating runtime HF model downloads, heavy Docker dependencies, and production failures.

**Architecture:** `PdfChunker` sends raw PDF bytes to Document AI's `process_document()` API, converts the structured response to markdown via `_doc_ai_to_markdown()` (using `document_layout.blocks` for heading detection), and feeds it into the existing `MarkdownChunker`. No changes to ingest.py, enrichment, or embedding pipeline.

**Tech Stack:** Python 3.12, google-cloud-documentai SDK, FastAPI, pytest

**Spec:** `docs/superpowers/specs/2026-03-24-docai-pdf-parsing-design.md`

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `src/agentdrive/config.py` | Add `docai_processor_id`, `docai_location`, `gcp_project_id` |
| Modify | `pyproject.toml` | Swap `docling` for `google-cloud-documentai` |
| Modify | `src/agentdrive/chunking/pdf.py` | Replace Docling with Document AI client + markdown converter |
| Create | `tests/test_pdf_chunker.py` | Unit tests for chunker + markdown converter |

---

### Task 1: Add Document AI config and swap dependency

**Files:**
- Modify: `src/agentdrive/config.py`
- Modify: `pyproject.toml:21`

- [ ] **Step 1: Add config settings**

In `src/agentdrive/config.py`, add before `model_config = {` (line 20):

```python
    docai_processor_id: str = ""
    docai_location: str = "us"
    gcp_project_id: str = ""
```

- [ ] **Step 2: Swap dependency in pyproject.toml**

Change line 21 from:
```toml
    "docling>=2.15.0",
```
To:
```toml
    "google-cloud-documentai>=2.0.0,<3.0",
```

- [ ] **Step 3: Install the new dependency**

Run: `uv pip install -e ".[dev]"`

Verify: `uv run python -c "from google.cloud import documentai_v1; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add src/agentdrive/config.py pyproject.toml
git commit -m "feat: add Document AI config, swap docling for google-cloud-documentai"
```

---

### Task 2: Write markdown converter tests and implementation

**Dependency:** Task 1 must be completed first — `google-cloud-documentai` must be installed before this task rewrites `pdf.py`.

**Files:**
- Create: `tests/test_pdf_chunker.py`
- Modify: `src/agentdrive/chunking/pdf.py`

**Key design note:** Document AI Layout Parser returns structured content via `document.document_layout.blocks[]`. Each block has a `text_block.type_` field indicating its type (`heading-1`, `heading-2`, `paragraph`, `title`, `list-item`, etc.) and `text_block.text` for content. Blocks can be nested (headings contain child blocks). Tables are in `table_block`. We use this structure — NOT `document.pages[].paragraphs` — to correctly detect headings for markdown output.

- [ ] **Step 1: Write tests for the markdown converter**

Create `tests/test_pdf_chunker.py`:

```python
from unittest.mock import MagicMock, patch

import pytest


def _make_text_block(text: str, type_: str = "paragraph"):
    """Make a mock text_block with type and text."""
    block = MagicMock()
    block.text_block.text = text
    block.text_block.type_ = type_
    block.text_block.blocks = []
    block.table_block = None
    return block


def _make_table_block(headers: list[str], rows: list[list[str]]):
    """Make a mock table_block."""
    block = MagicMock()
    block.text_block = None

    header_row = MagicMock()
    header_row.cells = []
    for h in headers:
        cell = MagicMock()
        cell.blocks = [_make_text_block(h)]
        header_row.cells.append(cell)

    body_rows = []
    for row in rows:
        body_row = MagicMock()
        body_row.cells = []
        for val in row:
            cell = MagicMock()
            cell.blocks = [_make_text_block(val)]
            body_row.cells.append(cell)
        body_rows.append(body_row)

    table = MagicMock()
    table.header_rows = [header_row]
    table.body_rows = body_rows

    block.table_block = table
    return block


def _make_document(blocks):
    """Make a mock Document with document_layout.blocks."""
    doc = MagicMock()
    doc.document_layout.blocks = blocks
    return doc


class TestDocAiToMarkdown:
    def test_paragraph(self):
        from agentdrive.chunking.pdf import _doc_ai_to_markdown

        doc = _make_document([
            _make_text_block("This is a paragraph.", "paragraph"),
        ])
        result = _doc_ai_to_markdown(doc)
        assert "This is a paragraph." in result
        assert not result.startswith("#")

    def test_heading_levels(self):
        from agentdrive.chunking.pdf import _doc_ai_to_markdown

        doc = _make_document([
            _make_text_block("Main Title", "title"),
            _make_text_block("Section One", "heading-1"),
            _make_text_block("Subsection", "heading-2"),
        ])
        result = _doc_ai_to_markdown(doc)
        assert "# Main Title" in result
        assert "## Section One" in result
        assert "### Subsection" in result

    def test_list_items(self):
        from agentdrive.chunking.pdf import _doc_ai_to_markdown

        doc = _make_document([
            _make_text_block("First item", "list-item"),
            _make_text_block("Second item", "list-item"),
        ])
        result = _doc_ai_to_markdown(doc)
        assert "- First item" in result
        assert "- Second item" in result

    def test_table(self):
        from agentdrive.chunking.pdf import _doc_ai_to_markdown

        doc = _make_document([
            _make_table_block(
                headers=["Name", "Age"],
                rows=[["Alice", "30"], ["Bob", "25"]],
            ),
        ])
        result = _doc_ai_to_markdown(doc)
        assert "| Name | Age |" in result
        assert "|---|---|" in result
        assert "| Alice | 30 |" in result
        assert "| Bob | 25 |" in result

    def test_empty_document(self):
        from agentdrive.chunking.pdf import _doc_ai_to_markdown

        doc = _make_document([])
        result = _doc_ai_to_markdown(doc)
        assert result == ""

    def test_mixed_content(self):
        from agentdrive.chunking.pdf import _doc_ai_to_markdown

        doc = _make_document([
            _make_text_block("Report Title", "title"),
            _make_text_block("This is the introduction.", "paragraph"),
            _make_table_block(
                headers=["Col1", "Col2"],
                rows=[["Val1", "Val2"]],
            ),
            _make_text_block("Summary", "heading-1"),
            _make_text_block("Final thoughts.", "paragraph"),
        ])
        result = _doc_ai_to_markdown(doc)
        assert "# Report Title" in result
        assert "This is the introduction." in result
        assert "| Col1 | Col2 |" in result
        assert "## Summary" in result
        assert "Final thoughts." in result

    def test_skips_header_footer(self):
        from agentdrive.chunking.pdf import _doc_ai_to_markdown

        doc = _make_document([
            _make_text_block("Page 1 of 10", "header"),
            _make_text_block("Actual content.", "paragraph"),
            _make_text_block("Copyright 2025", "footer"),
        ])
        result = _doc_ai_to_markdown(doc)
        assert "Actual content." in result
        assert "Page 1 of 10" not in result
        assert "Copyright 2025" not in result
```

- [ ] **Step 2: Run tests — verify they fail**

Run: `uv run pytest tests/test_pdf_chunker.py::TestDocAiToMarkdown -v -x`
Expected: FAIL — `ImportError: cannot import name '_doc_ai_to_markdown'`

- [ ] **Step 3: Write the markdown converter and PdfChunker**

Replace the entire contents of `src/agentdrive/chunking/pdf.py`:

```python
import logging

from google.cloud import documentai_v1 as documentai

from agentdrive.chunking.base import BaseChunker, ParentChildChunks
from agentdrive.chunking.markdown import MarkdownChunker
from agentdrive.config import settings

logger = logging.getLogger(__name__)

# Map Document AI block types to markdown prefixes
_HEADING_MAP = {
    "title": "# ",
    "heading-1": "## ",
    "heading-2": "### ",
    "heading-3": "#### ",
    "heading-4": "##### ",
    "heading-5": "###### ",
    "heading-6": "###### ",
}

_SKIP_TYPES = {"header", "footer"}


def _table_to_markdown(table_block) -> str:
    """Convert a Document AI TableBlock to markdown table syntax."""
    rows = []

    for header_row in table_block.header_rows:
        cells = []
        for cell in header_row.cells:
            cell_text = " ".join(
                b.text_block.text.strip() for b in cell.blocks if b.text_block
            )
            cells.append(cell_text)
        rows.append("| " + " | ".join(cells) + " |")
        rows.append("| " + " | ".join("---" for _ in cells) + " |")

    for body_row in table_block.body_rows:
        cells = []
        for cell in body_row.cells:
            cell_text = " ".join(
                b.text_block.text.strip() for b in cell.blocks if b.text_block
            )
            cells.append(cell_text)
        rows.append("| " + " | ".join(cells) + " |")

    return "\n".join(rows)


def _process_block(block, parts: list[str]) -> None:
    """Recursively process a Document AI block into markdown parts."""
    if block.table_block:
        md_table = _table_to_markdown(block.table_block)
        if md_table:
            parts.append(md_table)
        return

    if not block.text_block:
        return

    type_ = block.text_block.type_
    text = block.text_block.text.strip()

    if not text or type_ in _SKIP_TYPES:
        return

    prefix = _HEADING_MAP.get(type_, "")
    if type_ == "list-item":
        parts.append(f"- {text}")
    elif prefix:
        parts.append(f"{prefix}{text}")
    else:
        parts.append(text)

    # Process nested blocks (e.g., content under a heading)
    for child in block.text_block.blocks:
        _process_block(child, parts)


def _doc_ai_to_markdown(document) -> str:
    """Convert Document AI Layout Parser response to markdown."""
    parts: list[str] = []

    for block in document.document_layout.blocks:
        _process_block(block, parts)

    return "\n\n".join(parts)


class PdfChunker(BaseChunker):
    def __init__(self) -> None:
        self._markdown_chunker = MarkdownChunker()

    def supported_types(self) -> list[str]:
        return ["pdf"]

    def chunk(self, content: str, filename: str, metadata: dict | None = None) -> list[ParentChildChunks]:
        return []

    def chunk_bytes(self, data: bytes, filename: str, metadata: dict | None = None) -> list[ParentChildChunks]:
        processor_name = (
            f"projects/{settings.gcp_project_id}"
            f"/locations/{settings.docai_location}"
            f"/processors/{settings.docai_processor_id}"
        )

        client = documentai.DocumentProcessorServiceClient()
        raw_document = documentai.RawDocument(content=data, mime_type="application/pdf")
        request = documentai.ProcessRequest(name=processor_name, raw_document=raw_document)

        result = client.process_document(request=request)
        document = result.document

        markdown = _doc_ai_to_markdown(document)
        if not markdown.strip():
            logger.warning(f"PDF {filename}: Document AI produced empty markdown")
            return []

        return self._markdown_chunker.chunk(markdown, filename, metadata)
```

- [ ] **Step 4: Run converter tests — verify they pass**

Run: `uv run pytest tests/test_pdf_chunker.py::TestDocAiToMarkdown -v -x`
Expected: All 7 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/agentdrive/chunking/pdf.py tests/test_pdf_chunker.py
git commit -m "feat: replace Docling with Document AI Layout Parser in PdfChunker"
```

---

### Task 3: Write PdfChunker integration tests

**Files:**
- Modify: `tests/test_pdf_chunker.py`

- [ ] **Step 1: Add chunker-level tests**

Add to `tests/test_pdf_chunker.py`:

```python
from agentdrive.chunking.pdf import PdfChunker


class TestPdfChunker:
    @patch("agentdrive.chunking.pdf.documentai")
    @patch("agentdrive.chunking.pdf.settings")
    def test_happy_path(self, mock_settings, mock_docai):
        """PdfChunker should call Document AI and produce markdown."""
        # Configure settings
        mock_settings.gcp_project_id = "test-project"
        mock_settings.docai_location = "us"
        mock_settings.docai_processor_id = "abc123"

        # Mock Document AI response
        mock_block = _make_text_block("# Report\n\nThis is the content.", "paragraph")
        mock_document = _make_document([mock_block])

        mock_result = MagicMock()
        mock_result.document = mock_document

        mock_client = MagicMock()
        mock_client.process_document.return_value = mock_result
        mock_docai.DocumentProcessorServiceClient.return_value = mock_client
        mock_docai.RawDocument = MagicMock()
        mock_docai.ProcessRequest = MagicMock()

        chunker = PdfChunker()
        chunker.chunk_bytes(b"fake pdf bytes", "report.pdf")

        # Verify Document AI was called
        mock_client.process_document.assert_called_once()

        # Verify processor name was constructed correctly
        mock_docai.ProcessRequest.assert_called_once()
        call_kwargs = mock_docai.ProcessRequest.call_args[1]
        assert call_kwargs["name"] == "projects/test-project/locations/us/processors/abc123"

    @patch("agentdrive.chunking.pdf.documentai")
    @patch("agentdrive.chunking.pdf.settings")
    def test_empty_document(self, mock_settings, mock_docai):
        """PdfChunker should return empty list for empty Document AI response."""
        mock_settings.gcp_project_id = "test-project"
        mock_settings.docai_location = "us"
        mock_settings.docai_processor_id = "abc123"

        mock_document = _make_document([])
        mock_result = MagicMock()
        mock_result.document = mock_document

        mock_client = MagicMock()
        mock_client.process_document.return_value = mock_result
        mock_docai.DocumentProcessorServiceClient.return_value = mock_client
        mock_docai.RawDocument = MagicMock()
        mock_docai.ProcessRequest = MagicMock()

        chunker = PdfChunker()
        groups = chunker.chunk_bytes(b"fake pdf bytes", "empty.pdf")

        assert groups == []

    @patch("agentdrive.chunking.pdf.documentai")
    @patch("agentdrive.chunking.pdf.settings")
    def test_api_error_propagates(self, mock_settings, mock_docai):
        """PdfChunker should NOT swallow exceptions."""
        mock_settings.gcp_project_id = "test-project"
        mock_settings.docai_location = "us"
        mock_settings.docai_processor_id = "abc123"

        mock_client = MagicMock()
        mock_client.process_document.side_effect = RuntimeError("Document AI failed")
        mock_docai.DocumentProcessorServiceClient.return_value = mock_client
        mock_docai.RawDocument = MagicMock()
        mock_docai.ProcessRequest = MagicMock()

        chunker = PdfChunker()
        with pytest.raises(RuntimeError, match="Document AI failed"):
            chunker.chunk_bytes(b"fake pdf bytes", "bad.pdf")
```

- [ ] **Step 2: Run all pdf chunker tests**

Run: `uv run pytest tests/test_pdf_chunker.py -v`
Expected: All 10 tests pass (7 converter + 3 chunker).

- [ ] **Step 3: Run full test suite**

Run: `uv run pytest tests/ -v -x`
Expected: All tests pass. Existing ingest tests use `content_type="markdown"` so PdfChunker is not reached.

- [ ] **Step 4: Commit**

```bash
git add tests/test_pdf_chunker.py
git commit -m "test: add PdfChunker integration tests for Document AI"
```

---

### Task 4: Update .env.example and Cloud Run config

**Files:**
- Modify: `.env.example`
- Modify: `cloud-run/service.yaml`

- [ ] **Step 1: Add env vars to .env.example**

Add:
```
DOCAI_PROCESSOR_ID=your-processor-id
DOCAI_LOCATION=us
GCP_PROJECT_ID=your-gcp-project-id
```

- [ ] **Step 2: Update cloud-run/service.yaml**

Read `cloud-run/service.yaml`. Add the Document AI env vars alongside existing environment variables. Use placeholder values that the operator fills in after creating the Layout Parser processor:

```yaml
        - name: DOCAI_PROCESSOR_ID
          value: "FILL_AFTER_PROCESSOR_CREATION"
        - name: DOCAI_LOCATION
          value: "us"
        - name: GCP_PROJECT_ID
          value: "FILL_WITH_YOUR_PROJECT_ID"
```

Note: The GCP project ID may already be visible elsewhere in `service.yaml` (e.g., in Cloud SQL annotations). Use the same value. `DOCAI_PROCESSOR_ID` requires creating a Layout Parser processor first via the GCP console.

- [ ] **Step 3: Commit**

```bash
git add .env.example cloud-run/
git commit -m "chore: add Document AI env vars to config and Cloud Run"
```

---

### Task 5: Verify full test suite and cleanup

**Files:** None (verification only)

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All tests pass.

- [ ] **Step 2: Verify app imports cleanly**

Run: `uv run python -c "from agentdrive.main import app; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Final commit if any fixes needed**

```bash
git add -A
git commit -m "fix: cleanup from Document AI integration"
```
