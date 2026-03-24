# Google Document AI PDF Parsing Design

## Problem

Docling PDF parsing is broken in production. The `DocumentConverter` downloads layout models from Hugging Face at runtime, and Cloud Run's shared IP gets rate-limited (429). PDFs have never successfully processed on the deployed server. Additionally, Docling pulls heavy dependencies (PyTorch, HF Hub, OpenCV) that bloat the Docker image and cause cold start issues.

## Solution

Replace Docling with Google Cloud Document AI's Layout Parser for PDF parsing. Document AI handles OCR, layout detection, and table extraction, returning structured JSON that we convert to markdown and feed into the existing `MarkdownChunker`. AgentDrive is already on GCP, so auth, billing, and infrastructure are already configured.

## Design

### 1. PDF Chunker — Document AI Integration

Replace the Docling call in `PdfChunker.chunk_bytes()` with a Document AI API call:

```
chunk_bytes(data, filename, metadata)
  → Document AI process_document(raw_document=data)
  → _doc_ai_to_markdown(document) → markdown string
  → MarkdownChunker.chunk(markdown, filename)
```

**Document AI client setup:**
- Use `google.cloud.documentai_v1` SDK, authenticated via ADC (already configured on Cloud Run)
- Requires a processor ID (created once via GCP console, stored as config setting)
- Processor resource name: `projects/{project}/locations/{location}/processors/{processor_id}`
- GCP project ID read from environment via `google.auth.default()` or added to config

**File transfer:** Pass raw bytes directly via `raw_document` parameter. The `data` bytes are already downloaded in `ingest.py` before `chunk_bytes` is called — no GCS URI or signed URL needed. This is the simplest approach.

**No changes to ingest.py.** The existing call `chunker.chunk_bytes(data, file.filename)` works as-is.

**Error handling:** Remove the existing `try/except: return []` that silently swallows errors. Let exceptions propagate up to `process_file()` which already handles failures (rollback + set status=FAILED). The queue worker adds a 15-minute timeout on top.

**Online endpoint limits:** `process_document()` (synchronous) supports max 20 pages and 20MB per request. For files exceeding these limits, the chunker should fall back to `batch_process_documents()` with GCS input/output, or fail gracefully with a clear error message. For v1, we accept the 20-page limit and document it — most business PDFs are under 20 pages. Larger PDFs can be addressed later with batch processing.

### 2. Markdown Converter

A function `_doc_ai_to_markdown(document)` inside `pdf.py` (~100-150 lines) that converts Document AI's Layout Parser response to markdown.

**Text extraction:** Document AI stores all text in `document.text`. Each element references spans via `text_anchor.text_segments[].start_index` / `.end_index`. A helper extracts text for any element:

```python
def _get_text(document, text_anchor) -> str:
    return "".join(
        document.text[seg.start_index:seg.end_index]
        for seg in text_anchor.text_segments
    )
```

**Layout elements (from `page.paragraphs`, `page.blocks`):**

| Document AI type | Markdown output |
|-----------------|-----------------|
| heading / title | `#` or `##` (based on detected level) |
| paragraph | plain text + blank line |
| list_item | `- item text` |
| header / footer | skip (not useful for RAG) |

**Table handling:** Document AI returns `page.tables[]` with `header_rows` and `body_rows`, each containing `cells` with `layout.text_anchor`. The converter:
1. Extracts text from each cell
2. Builds markdown table header: `| col1 | col2 |`
3. Adds separator: `|---|---|`
4. Adds body rows: `| val1 | val2 |`
5. For merged cells, flattens to best-effort single-cell text

**Page handling:** Processes pages sequentially, concatenating output. No page break markers needed — the MarkdownChunker handles sectioning.

### 3. Config + Dependencies

**`config.py`:** Add settings:
```python
docai_processor_id: str = ""
docai_location: str = "us"
gcp_project_id: str = ""
```

Env vars: `DOCAI_PROCESSOR_ID`, `DOCAI_LOCATION`, `GCP_PROJECT_ID`.

`gcp_project_id` is needed to construct the processor resource name. On Cloud Run, this can also be read from metadata server, but an explicit config is more reliable and testable.

**`pyproject.toml`:** Swap dependency:
```
- "docling>=2.15.0"
+ "google-cloud-documentai>=2.0.0,<3.0"
```

`google-cloud-storage` is already a dependency, so the GCP auth stack is present.

**Cloud Run:** Add `DOCAI_PROCESSOR_ID` and `GCP_PROJECT_ID` env vars. Not sensitive — no secrets needed.

**Pre-requisite (one-time):** Create a Layout Parser processor via GCP console or gcloud CLI.

## Testing

**Unit tests for PdfChunker (`tests/test_pdf_chunker.py`):**
- Happy path: mock Document AI client → returns document with paragraphs + table → markdown → ParentChildChunks
- Empty document: Document AI returns no pages → returns `[]`
- API error: exception propagates (not swallowed)

**Unit tests for `_doc_ai_to_markdown`:**
- Heading → `## text`
- Paragraph → plain text
- Table with headers + rows → markdown table
- Table with merged/empty cells → best-effort markdown
- Mixed content → correct ordering
- Multi-page document → pages concatenated

**Existing tests:** No changes needed. Ingest tests use `content_type="markdown"` so PdfChunker is never reached.

## Files Changed

| Action | File | Change |
|--------|------|--------|
| Modify | `src/agentdrive/chunking/pdf.py` | Replace Docling with Document AI client + markdown converter |
| Modify | `src/agentdrive/config.py` | Add `docai_processor_id`, `docai_location`, `gcp_project_id` |
| Modify | `pyproject.toml` | Swap `docling` for `google-cloud-documentai` |
| Create | `tests/test_pdf_chunker.py` | Unit tests for Document AI chunker + markdown converter |

Note: `ingest.py` does NOT need changes — the existing `chunk_bytes(data, filename)` call works as-is.

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Scope | PDF parsing only | Other chunkers work fine |
| Processor | Layout Parser ($10/1K pages) | Structured blocks (headings, tables, paragraphs) vs raw OCR text. Better quality for markdown conversion. |
| File transfer | Raw bytes via `raw_document` | Simplest — bytes already in memory from `storage.download()`. No GCS URI or signed URL needed. |
| Markdown converter | Inline function in pdf.py | ~100-150 lines, keeps chunker self-contained |
| Docling | Remove entirely | Broken in production, heavy deps |
| Error handling | Let exceptions propagate; remove silent catch | Existing pipeline handles failures |
| Async | Stays synchronous | `chunk_bytes` is sync. `process_file` is async but calls chunker synchronously — same as Docling. Blocks the event loop but mitigated by queue worker pool (3 workers). |
| Page limit | Accept 20-page limit for v1 | Most business PDFs are under 20 pages. Batch processing for larger PDFs is a future enhancement. |

## Pricing

- Layout Parser: $10/1K pages ($0.01/page)
- At 1K pages/month: $10/month
- At 10K pages/month: $100/month
- Already on GCP billing — no new vendor relationship
