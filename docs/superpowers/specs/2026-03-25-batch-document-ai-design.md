# Batch Document AI for Large PDFs

**Sub-project 2 of 3** for [Issue #17: Support large documents (500+ pages, 50MB+)](https://github.com/Agent-Drive/AgentDrive/issues/17)

**Depends on:** Sub-project 1 (incremental pipeline) must be completed first.

## Context

Sub-project 1 restructured the pipeline into four phases with incremental commits and a `FileBatch` tracking model. However, Document AI processing still uses the synchronous online API (`process_document()`), which has hard limits:

- **30 pages per request** (we split, but batches are sequential and in-memory)
- **20MB per request payload** (large PDFs with images can exceed this)
- **Synchronous** — each batch blocks the worker while waiting for Document AI

This sub-project switches large PDFs to Document AI's asynchronous `batch_process_documents()` API, which:

- Accepts GCS input/output URIs (no file data flows through our server)
- Supports up to 500 pages per request
- Processes asynchronously — we poll for completion
- Removes the 20MB payload limit (reads directly from GCS)

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| API split | Sync online ≤30pg, async batch >30pg | Keep small docs fast; batch API has ~30-60s startup overhead |
| Input source | GCS URI (file already in GCS from upload) | Zero memory pressure — Document AI reads directly from GCS |
| Output | GCS URI → read JSON from output prefix | Document AI writes results to GCS, we read and convert to markdown |
| Polling | Poll LRO with exponential backoff | Timeout after configurable limit (default 30min) |
| Multi-batch | True multi-batch with `batch_id` FK on chunks | Sub-project 1's single-batch simplification gets upgraded |
| Batch size | One batch request per ≤500 pages | Batch API handles up to 500 pages per request; split only if >500 |

## Design

### 1. Dual-Path PDF Processing

```
chunk_file(path, gcs_path=None):
  total_pages = count pages

  if total_pages <= 30:
    sync online API (fast, unchanged)
    → single markdown string → single FileBatch

  elif total_pages <= 500:
    async batch API (1 request, whole document)
    → single markdown string → single FileBatch

  else (>500 pages):
    split PDF into ≤500-page chunks on disk
    async batch API per chunk (parallel submissions)
    → multiple markdown strings → multiple FileBatches
```

The chunker's `chunk_file` method gains an optional `gcs_path: str | None` parameter. For the sync path (≤30pg), it's ignored. For the async path (>30pg), Document AI reads the file directly from GCS.

For files >500 pages, we split using pypdf (same pattern as current 30-page splitting) into 500-page PDFs, upload each to a temp GCS location, and submit separate batch requests.

### 2. Async Batch Processing

**API shape** (from `google.cloud.documentai_v1`):

```python
# Input: GCS URI of the PDF
input_config = documentai.BatchDocumentsInputConfig(
    gcs_documents=documentai.GcsDocuments(
        documents=[
            documentai.GcsDocument(
                gcs_uri=f"gs://{bucket}/{gcs_path}",
                mime_type="application/pdf",
            )
        ]
    )
)

# Output: GCS prefix where results are written
output_config = documentai.DocumentOutputConfig(
    gcs_output_config=documentai.DocumentOutputConfig.GcsOutputConfig(
        gcs_uri=f"gs://{bucket}/tmp/docai/{file_id}/",
    )
)

# Submit batch request (returns a long-running operation)
request = documentai.BatchProcessRequest(
    name=processor_name,
    input_documents=input_config,
    document_output_config=output_config,
)
operation = client.batch_process_documents(request=request)
```

The operation is a Google Cloud LRO (Long-Running Operation). We wrap it with async polling using exponential backoff.

**New function: `_process_batch_api(gcs_uri, processor_name, output_prefix)`**

```
1. Build BatchProcessRequest with GCS input/output
2. Submit: client.batch_process_documents(request) → operation
3. Poll operation with exponential backoff (5s → 60s cap, 30min timeout)
4. On completion: list output blobs at output_prefix
5. Read each output JSON, extract document, convert to markdown via _doc_ai_to_markdown
6. Cleanup: delete output blobs
7. Return concatenated markdown string
```

### 3. Multi-Batch Integration with FileBatch

Sub-project 1 created one `FileBatch` per file. Now:

```
≤30 pages  → sync path  → 1 FileBatch
≤500 pages → 1 async batch request → 1 FileBatch
800 pages  → 2 async batch requests → 2 FileBatches (1-500, 501-800)
```

**New: `batch_id` FK on Chunk and ParentChunk**

```
Chunk
  + batch_id: UUID (FK → file_batches.id, nullable for backcompat with existing data)

ParentChunk
  + batch_id: UUID (FK → file_batches.id, nullable for backcompat with existing data)
```

This enables true per-batch operations in Phases 3 and 4.

**Phase 1 update for multi-batch:** The ingest pipeline's `_phase1_chunking` changes from "create one batch, commit all chunks" to:

```
For each batch result (markdown string from Document AI):
  1. Create or update FileBatch record (page_range, status=processing)
  2. Parse markdown → chunk → create ParentChunk/Chunk with batch_id
  3. Mark FileBatch.chunking_status = completed
  4. Commit (frees memory)
  → Next batch
```

For ≤500 page files, there's only one batch — functionally identical to sub-project 1.

### 4. GCS Output Management

Document AI batch writes output to a GCS prefix as JSON files. We need:

1. **Output prefix:** `gs://{bucket}/tmp/docai/{file_id}/` — deterministic, file-scoped
2. **Read results:** After batch completes, list blobs under prefix, download each JSON
3. **Parse results:** Each JSON contains a `Document` proto — feed to existing `_doc_ai_to_markdown()`
4. **Cleanup:** Delete all blobs under the prefix after processing

New `StorageService` methods:

```python
def list_blobs(self, prefix: str) -> list[str]:
    """List all blob names under a GCS prefix."""

def delete_prefix(self, prefix: str) -> None:
    """Delete all blobs under a GCS prefix."""
```

### 5. Polling & Timeout

```python
async def _poll_operation(operation, timeout_seconds: int) -> None:
    """Poll a Document AI LRO with exponential backoff."""
    start = time.time()
    delay = 5.0
    max_delay = 60.0

    while time.time() - start < timeout_seconds:
        if operation.done():
            if operation.exception():
                raise operation.exception()
            return
        await asyncio.sleep(delay)
        delay = min(delay * 1.5, max_delay)

    raise TimeoutError(f"Batch operation timed out after {timeout_seconds}s")
```

**Config:** `docai_batch_timeout_seconds: int = 1800` (30 minutes)

### 6. Phase 3/4 Updates for Multi-Batch

With `batch_id` on chunks, Phases 3 and 4 genuinely process per-batch:

```
Phase 3 (enrichment):
  For each FileBatch where enrichment_status != completed:
    Load chunks WHERE batch_id = batch.id
    Enrich with summaries + local context
    Commit
    Mark enrichment_status = completed

Phase 4 (embedding):
  For each FileBatch where embedding_status != completed:
    Load chunks WHERE batch_id = batch.id
    Embed in sub-batches of 64
    Commit
    Mark embedding_status = completed
```

If enrichment fails at batch 3 of 5, batches 1-2 are committed and won't be re-processed on retry.

**Embedding functions need batch scoping:** `embed_file_chunks` and `embed_file_aliases` currently take `file_id` and embed everything for that file. They need an optional `batch_id` parameter to scope the query.

## Boundary: What Changes vs. What Doesn't

```
Changed:
  chunking/pdf.py           Add async batch path, gcs_path parameter, dual-path dispatch
  services/ingest.py        Phase 1 multi-batch loop; Phases 3-4 per-batch with batch_id
  services/storage.py       Add list_blobs(), delete_prefix()
  models/chunk.py           Add batch_id FK to Chunk and ParentChunk
  embedding/pipeline.py     Add optional batch_id parameter to embed functions
  config.py                 Add docai_batch_timeout_seconds
  alembic/                  Migration for batch_id columns

NOT changed:
  routers/                  No API changes
  enrichment/               Two-pass enrichment unchanged (just called per-batch now)
  search/                   Unchanged
  mcp/                      Unchanged
  schemas/                  Unchanged (progress fields from sub-project 1 still work)
  chunking/base.py          chunk_file signature gains gcs_path but default ignores it
```

## Non-Goals

- Upload size limit changes (sub-project 3)
- Non-PDF file types
- Document AI batch API for docs ≤30 pages
- Parallel batch submissions (sequential for simplicity; can optimize later)

## Testing Strategy

- **Unit tests:** Dual-path dispatch (≤30pg → sync, 31-500pg → single async, >500pg → multi async)
- **Unit tests:** Batch operation polling with mock LROs (success, timeout, error)
- **Unit tests:** GCS output reading and cleanup
- **Unit tests:** `_doc_ai_to_markdown` works with batch output JSON format
- **Integration tests:** Multi-batch FileBatch creation with batch_id on chunks
- **Integration tests:** Per-batch enrichment and embedding with batch_id filtering
- **Integration tests:** Resume from failed batch in multi-batch scenario
- **Regression tests:** Small PDF (≤30 pages) behavior unchanged
- **External APIs mocked:** Document AI (both online and batch), GCS
