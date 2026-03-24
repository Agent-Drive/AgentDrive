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
  → extract gcs_path from metadata
  → build GCS URI: gs://{bucket}/{gcs_path}
  → Document AI Layout Parser: process_document(gs_uri)
  → _doc_ai_to_markdown(document) → markdown string
  → MarkdownChunker.chunk(markdown, filename)
```

**Document AI client setup:**
- Use `google.cloud.documentai_v1` SDK, authenticated via ADC (already configured on Cloud Run)
- Requires a processor ID (created once via GCP console, stored as config setting)

**File transfer:** Pass GCS URI (`gs://bucket/path`) directly to Document AI. The Cloud Run service account already has GCS read access. No signed URLs, no extra auth, no double upload.

**Error handling:** Remove the existing `try/except: return []` that silently swallows errors. Let exceptions propagate up to `process_file()` which already handles failures (rollback + set status=FAILED). The queue worker adds a 15-minute timeout on top.

**No temp files needed.** Document AI reads from GCS directly.

### 2. Markdown Converter

A function `_doc_ai_to_markdown(document)` inside `pdf.py` that converts Document AI's Layout Parser response to markdown:

**Type mapping:**
- `heading` / `title` → `#` or `##` (based on detected level)
- `paragraph` → plain text + blank line
- `table` → markdown table syntax (`| col | col |`)
- `list_item` → `- item text`
- `header` / `footer` → skip (not useful for RAG)

**Text extraction:** Document AI returns text via `text_anchor` offsets into `document.text`. The converter extracts text using these offsets — a standard Document AI pattern.

**Table handling:** Document AI returns tables as `Table` objects with `header_rows` and `body_rows`, each containing cells. We iterate rows/cells and build markdown table syntax. For complex merged-cell tables, we flatten to best-effort markdown.

This function is ~50-80 lines. Lives in `pdf.py` alongside the chunker — not complex enough for its own module.

### 3. Changes to ingest.py

Pass `gcs_path` via metadata to the chunker:

```python
# Current
chunk_groups = chunker.chunk_bytes(data, file.filename)

# Proposed
chunk_groups = chunker.chunk_bytes(
    data, file.filename,
    metadata={"gcs_path": file.gcs_path},
)
```

Non-PDF chunkers ignore `metadata`. No ripple effects. Simpler than signed URL approach — just the GCS path.

### 4. Config + Dependencies

**`config.py`:** Add two settings:
```python
docai_processor_id: str = ""
docai_location: str = "us"
```

Env vars: `DOCAI_PROCESSOR_ID`, `DOCAI_LOCATION`.

**`pyproject.toml`:** Swap dependency:
```
- "docling>=2.15.0"
+ "google-cloud-documentai>=2.0.0,<3.0"
```

`google-cloud-storage` is already a dependency, so the GCP auth stack is present.

**Cloud Run:** Add `DOCAI_PROCESSOR_ID` env var. Not sensitive — no secret needed.

**Pre-requisite (one-time):** Create a Layout Parser processor via GCP console or gcloud CLI.

## Testing

**Unit tests for PdfChunker:**
- Happy path: mock Document AI client → returns document with paragraphs + table → markdown → ParentChildChunks
- Empty document: Document AI returns no pages → returns `[]`
- API error: exception propagates (not swallowed)

**Unit tests for `_doc_ai_to_markdown`:**
- Heading → `## text`
- Paragraph → plain text
- Table with headers + rows → markdown table
- Mixed content → correct ordering

**Existing tests:** No changes needed. Ingest tests use `content_type="markdown"` so PdfChunker is never reached.

## Files Changed

| Action | File | Change |
|--------|------|--------|
| Modify | `src/agentdrive/chunking/pdf.py` | Replace Docling with Document AI client + markdown converter |
| Modify | `src/agentdrive/config.py` | Add `docai_processor_id`, `docai_location` |
| Modify | `src/agentdrive/services/ingest.py` | Pass `gcs_path` in metadata to chunker |
| Modify | `pyproject.toml` | Swap `docling` for `google-cloud-documentai` |
| Create | `tests/test_pdf_chunker.py` | Unit tests for Document AI chunker + markdown converter |

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Scope | PDF parsing only | Other chunkers work fine |
| Processor | Layout Parser ($10/1K pages) | Structured blocks (headings, tables, paragraphs) vs raw OCR text. Better quality for markdown conversion. |
| File transfer | GCS URI (`gs://`) | Already on GCP; Cloud Run service account has read access. No signed URLs needed. |
| Markdown converter | Inline function in pdf.py | ~50-80 lines, not complex enough for own module |
| Docling | Remove entirely | Broken in production, heavy deps |
| Error handling | Let exceptions propagate; remove silent catch | Existing pipeline handles failures |
| Async | Stays synchronous | `chunk_bytes` is sync, called from sync context in `process_file` |

## Pricing

- Layout Parser: $10/1K pages ($0.01/page)
- At 1K pages/month: $10/month
- At 10K pages/month: $100/month
- Already on GCP billing — no new vendor relationship
