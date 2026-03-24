# Reducto PDF Parsing Design

## Problem

Docling PDF parsing is broken in production. The `DocumentConverter` downloads layout models from Hugging Face at runtime, and Cloud Run's shared IP gets rate-limited (429). PDFs have never successfully processed on the deployed server. Additionally, Docling pulls heavy dependencies (PyTorch, HF Hub, OpenCV) that bloat the Docker image and cause cold start issues.

## Solution

Replace Docling with Reducto's cloud API for PDF parsing. Reducto handles OCR, layout detection, and table extraction, returning clean markdown that feeds into the existing `MarkdownChunker`. This is a 4-file change with no modifications to the chunking, enrichment, or embedding pipeline.

## Design

### 1. PDF Chunker — Reducto Integration

Replace the Docling call in `PdfChunker.chunk_bytes()` with a Reducto API call:

```
chunk_bytes(data, filename, metadata)
  → extract gcs_path from metadata
  → StorageService.generate_signed_url(gcs_path)
  → Reducto client.parse.run(input=signed_url)
  → concatenate result chunk contents into single markdown string
  → MarkdownChunker.chunk(markdown, filename)
```

The Reducto client is synchronous (`reducto.Reducto`), wrapped in `asyncio.to_thread` if needed. This is the same pattern as Docling (synchronous in an async pipeline) — not a regression.

**Reducto parse configuration:**
- `formatting.table_output_format`: `"dynamic"` (markdown for simple tables, HTML for complex)
- `settings.ocr_system`: `"standard"` (1 credit/page)
- No Reducto-side chunking configuration needed — we concatenate all returned content into a single markdown string and let our `MarkdownChunker` handle segmentation

**Error handling:** Exceptions propagate up to `process_file()` which already handles failures (rollback + set status=FAILED). The queue worker adds a 15-minute timeout on top. The Reducto SDK has built-in retries (2x with exponential backoff) for transient errors (429, 5xx).

**Metadata passing:** `gcs_path` is passed to the chunker via the existing `metadata` dict parameter: `chunker.chunk_bytes(data, file.filename, metadata={"gcs_path": file.gcs_path})`. Non-PDF chunkers already accept and ignore this parameter.

### 2. StorageService — Signed URL Generation

Add a new method to `StorageService`:

```python
def generate_signed_url(self, gcs_path: str, expiration_minutes: int = 30) -> str:
    bucket = self._client.bucket(settings.gcs_bucket)
    blob = bucket.blob(gcs_path)
    return blob.generate_signed_url(
        version="v4",
        expiration=timedelta(minutes=expiration_minutes),
        method="GET",
    )
```

30-minute expiration — generous for Reducto's 6-15 second processing time. Read-only, short-lived.

### 3. Config + Dependencies

**`config.py`:** Add `reducto_api_key: str = ""`. Env var: `REDUCTO_API_KEY`.

**`pyproject.toml`:** Swap `docling` for `reductoai>=0.16.0`. This is a massive dependency reduction — Docling pulls PyTorch, HF Hub, model weights, OpenCV. Reducto is a thin `httpx` wrapper.

**Cloud Run:** Add `REDUCTO_API_KEY` to service secrets.

**Dockerfile:** May be able to remove Docling-specific system deps (`libgl1`, etc.). Check during implementation.

### 4. Changes to ingest.py

One line change — pass `gcs_path` to the chunker:

```python
# Current
chunk_groups = chunker.chunk_bytes(data, file.filename)

# Proposed
chunk_groups = chunker.chunk_bytes(data, file.filename, metadata={"gcs_path": file.gcs_path})
```

Non-PDF chunkers ignore `metadata`. No ripple effects.

## Testing

**Unit tests for PdfChunker:**
- Happy path: mock Reducto client → returns chunks → markdown → MarkdownChunker produces ParentChildChunks
- Empty result: Reducto returns no chunks → returns `[]`
- API error: Reducto raises exception → propagates (not swallowed like Docling)
- Signed URL: verify `generate_signed_url` called with correct `gcs_path`

**Existing tests:** No changes needed. `test_files.py` mocks `enqueue`. `test_ingest.py` mocks enrichment/embedding. The Reducto client is mocked at the `pdf.py` level.

## Files Changed

| Action | File | Change |
|--------|------|--------|
| Modify | `src/agentdrive/chunking/pdf.py` | Replace Docling with Reducto SDK call |
| Modify | `src/agentdrive/services/storage.py` | Add `generate_signed_url` method |
| Modify | `src/agentdrive/config.py` | Add `reducto_api_key` setting |
| Modify | `src/agentdrive/services/ingest.py` | Pass `gcs_path` in metadata to chunker |
| Modify | `pyproject.toml` | Swap `docling` for `reductoai` |
| Create | `tests/test_pdf_chunker.py` | Unit tests for Reducto-based PDF chunker |

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Scope | PDF parsing only | Other chunkers work fine; Reducto complements, not replaces |
| File transfer | GCS signed URL | File already in GCS; avoids double upload |
| Reducto chunking | Ignore / concatenate | Our MarkdownChunker builds parent-child hierarchy; Reducto chunks are flat |
| Table format | `dynamic` | Auto-switches markdown/HTML based on table complexity |
| OCR mode | `standard` | 1 credit/page; `agentic` (2x cost) available for complex docs later |
| Docling | Remove entirely | Broken in production, heavy deps, no value as fallback |
| Error handling | Let exceptions propagate | Existing pipeline handles failures; SDK retries transient errors |
| Async | `asyncio.to_thread` wrapper | Same pattern as Docling; avoids changing BaseChunker interface |

## Pricing

- Free tier: 100 credits/month (~30 pages) — enough for testing
- Standard: $350/mo for 15K pages, $0.015/page overage
- At current scale, cost is negligible
