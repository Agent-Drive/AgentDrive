# Incremental Pipeline + Streaming Download + Two-Pass Enrichment

**Sub-project 1 of 3** for [Issue #17: Support large documents (500+ pages, 50MB+)](https://github.com/Agent-Drive/AgentDrive/issues/17)

## Context

The current ingestion pipeline holds entire files in memory and processes them synchronously. Every stage — download, chunking, enrichment, embedding, DB commit — accumulates data in memory before proceeding. This creates hard limits on document size and risks OOM on large files.

This sub-project restructures the pipeline internals to process documents incrementally. It does **not** change the upload size limit (sub-project 3) or switch to Document AI's batch API (sub-project 2).

## Sub-project Roadmap

```
Sub-project 1 (this spec): Incremental pipeline + streaming + two-pass enrichment
Sub-project 2:             Batch Document AI for large PDFs (async GCS-to-GCS)
Sub-project 3:             Resumable upload via GCS signed URLs (raise 32MB limit)
```

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Scope | PDFs only | Primary large-doc format; other types rarely hit limits |
| Document AI | Keep sync online API (≤30pg) | Batch API deferred to sub-project 2 |
| Enrichment | Two-pass (summary + local context) | Best quality at scale; bounded token cost |
| DB commits | Incremental for all documents | One code path; no behavioral difference for small docs |
| Upload | No changes | Deferred to sub-project 3 |

## Design

### 1. Streaming Download

**Current:** `data = storage.download(gcs_path)` — full file loaded into memory as bytes.

**New:** `StorageService.download_stream(gcs_path)` returns a file-like stream. For PDFs (which need random access for pypdf), the stream is written to a temporary file on disk. Temp file is cleaned up after chunking.

```
Before:  GCS ──full bytes──→ RAM ──→ chunker
After:   GCS ──stream──→ temp file on disk ──→ PdfReader ──→ 30-page batches
                          (cleaned up after)
```

This moves memory cost from RAM to disk. Cloud Run has 2GB RAM but can mount larger temp storage.

**Chunker interface change:** `PdfChunker` gets a new method `chunk_file(path: Path, ...)` alongside the existing `chunk_bytes(data: bytes, ...)`. The registry dispatches to `chunk_file` when a temp file path is available, falling back to `chunk_bytes` for non-PDF chunkers. The `BaseChunker` interface adds `chunk_file` as an optional method with a default implementation that reads the file into bytes and delegates to `chunk_bytes` — so existing chunkers require no changes.

**Files changed:** `services/storage.py`, `chunking/pdf.py`, `chunking/registry.py` (add `chunk_file` dispatch), `chunking/base.py` (add optional `chunk_file` with default)

### 2. Incremental Chunk Processing & DB Commits

**Current:** All chunks accumulated in SQLAlchemy session → single commit at end.

**New:** Process and commit in batches aligned with Document AI's 30-page page splits. The pipeline runs in four phases:

```
Phase 1 — Chunking (incremental):
  For each 30-page batch:
    Document AI → markdown → parent/child chunks → commit to DB → free memory

Phase 2 — Summarization (one shot):
  Read all committed chunks → generate doc summary + section summaries
  → save to FileSummary record → commit

Phase 3 — Enrichment + Table Aliases (incremental):
  For each FileBatch:
    Load batch's chunks → enrich with [doc summary + section summary + ±3 neighbors]
    → generate table aliases for table chunks → commit → mark batch enrichment_status = completed

Phase 4 — Embedding (incremental):
  For each FileBatch:
    Load batch's chunks + aliases → embed in sub-batches of 64 → commit
    → mark batch embedding_status = completed
```

Each phase commits incrementally. For small docs (≤30 pages), Phase 1 is a single batch — functionally identical to current behavior. For non-PDF files, Phase 1 creates a single `FileBatch` with no `page_range` — the overhead is one extra DB row per file.

**Batch tracking:** New `FileBatch` model:

```
FileBatch
  ├── id
  ├── file_id
  ├── batch_index (0, 1, 2...)
  ├── page_range (e.g., "1-30", "31-60"; null for non-PDFs)
  ├── chunking_status (pending / processing / completed / failed)
  ├── enrichment_status (pending / processing / completed / failed)
  ├── embedding_status (pending / processing / completed / failed)
  └── chunk_count
```

Phase 3 and Phase 4 reuse the same `FileBatch` records created in Phase 1 — each batch tracks its own enrichment and embedding status independently. This means resume granularity is per-batch per-phase.

**Transaction isolation:** Partially-committed chunks are visible in the DB during processing. This is safe because search filters on `file.status == 'ready'` — files in `processing` status are excluded from search results. This is a **correctness dependency**: any new query path must respect this filter.

**Files changed:** `services/ingest.py`, `models/` (new FileBatch), `embedding/pipeline.py`, `alembic/` (migration)

### 3. Two-Pass Enrichment

**Current:** Full document text (~100-120K tokens for large docs) sent as cached context with every enrichment call. Attention quality degrades on long contexts.

**New:** Two passes:

**Pass 1 — Summarization (Phase 2):**
Full document text → LLM → document summary (~500 tokens) + section summaries (~200 tokens each).

Stored in a new `FileSummary` model:

```
FileSummary
  ├── id
  ├── file_id (unique — one summary per file)
  ├── document_summary (text, ~500 tokens)
  └── section_summaries (JSONB, list of {heading, summary} objects)
```

**Pass 2 — Per-chunk enrichment (Phase 3):**
Each chunk enriched with `[doc summary + relevant section summary + ±3 neighbor chunks]` → LLM → context prefix. ~3-5K tokens per call regardless of document size.

**Table aliases:** After enrichment within each batch, `generate_table_aliases()` runs on table chunks in that batch. This preserves the existing table QA feature within the new pipeline.

**Quality comparison:**

| Scenario | Current (full context) | Two-pass (summaries + local) |
|----------|----------------------|------------------------------|
| Small docs | Full doc in context | Summary + local — comparable quality |
| Large docs | Degraded (attention dilution on 120K tokens) | Focused context — **better quality** |
| Token cost | O(chunks x doc_size) | O(doc_size + chunks x 5K) — much cheaper |

**Files changed:** `enrichment/contextual.py`, `models/` (new FileSummary)

### 4. File Status & Progress Tracking

**Current:** `pending → processing → ready / failed`

**New:** File statuses unchanged. Add progress metadata to file records:

```
total_batches: int
completed_batches: int
current_phase: "chunking" | "summarizing" | "enriching" | "embedding" | null
```

Exposed via existing `GET /files/{id}/status` — no new endpoints:

```json
{
  "status": "processing",
  "total_batches": 17,
  "completed_batches": 12,
  "current_phase": "enriching"
}
```

`completed_batches` reflects the current phase — during chunking it counts chunked batches, during enrichment it counts enriched batches, etc.

For small docs: `total_batches: 1`, progress flips quickly. Clients checking `status == "ready"` see no change.

**Files changed:** `schemas/` (add fields to status response), `models/` (file metadata fields)

### 5. Error Handling & Resume

**Current:** Any failure → file marked "failed", full restart required.

**New:** Granular failure and resume at the batch/phase level.

**Resume mechanism:** `process_file()` inspects existing state to determine where to resume:

```python
batches = get_batches(file_id)
summary = get_summary(file_id)

if not batches:
    # No work done yet — start from Phase 1
    start Phase 1 (chunking)

elif any batch has chunking_status != completed:
    # Phase 1 incomplete — resume chunking from first non-completed batch
    resume Phase 1

elif not summary:
    # All batches chunked but no summary — start Phase 2
    start Phase 2 (summarization)

elif any batch has enrichment_status != completed:
    # Phase 3 incomplete — resume enrichment from first non-completed batch
    resume Phase 3

elif any batch has embedding_status != completed:
    # Phase 4 incomplete — resume embedding from first non-completed batch
    resume Phase 4

else:
    # Everything done — mark file as ready
    set file.status = "ready"
```

**Resume trigger:** When a file fails, it is marked `status = "failed"`. The existing re-enqueue mechanism (manual or via API) resets the file to `status = "processing"` and places it back on the queue. The worker calls `process_file()`, which inspects batch/summary state and resumes from the correct point. The reaper handles stuck `processing` files as before — resetting them to `pending` for re-pickup.

**Retry policy:** Max 3 retries before permanent failure (configurable via `config.py`). Retry count stored on the File model.

**Files changed:** `services/ingest.py`, `services/queue.py`, `models/` (retry_count on File)

## Boundary: What Changes vs. What Doesn't

```
Changed:
  services/ingest.py        Phase-based pipeline, incremental commits, resume logic
  services/storage.py       Add download_stream(), temp file support
  services/queue.py         Resume-aware re-enqueue
  chunking/pdf.py           Accept file path instead of bytes
  chunking/base.py          Add optional chunk_file() with default implementation
  chunking/registry.py      Dispatch to chunk_file when path available
  enrichment/contextual.py  Two-pass: summarize then enrich with local context
  embedding/pipeline.py     Process per-batch instead of all-at-end
  models/                   Add FileBatch, FileSummary; add progress + retry fields to File
  schemas/                  Add batch progress to file status response
  alembic/                  Migration for new tables + file fields
  config.py                 Add max_retries config

NOT changed:
  routers/                  No API changes (upload still 32MB)
  chunking/markdown.py      Unchanged
  chunking/hierarchy.py     Unchanged
  search/                   Unchanged (filters by file.status == 'ready' — correctness dependency)
  mcp/                      Unchanged
  dependencies.py           Unchanged
```

## Non-Goals

- Upload size limit changes (sub-project 3)
- Document AI batch API (sub-project 2)
- Changes to search, MCP, or auth
- New API endpoints
- Support for non-PDF large documents (future generalization)

## Testing Strategy

- **Unit tests:** Two-pass enrichment (summary generation, per-chunk enrichment with local context)
- **Unit tests:** Resume logic (simulate failures at each phase, verify correct restart point using batch statuses)
- **Unit tests:** Table alias generation within Phase 3 batch processing
- **Integration tests:** Full pipeline with incremental commits (verify chunks appear in DB after each batch commit)
- **Integration tests:** FileBatch status transitions across all four phases
- **Integration tests:** Resume from each phase (create partial state, verify pipeline picks up correctly)
- **Regression tests:** Small doc ingestion produces identical results to current pipeline
- **Regression tests:** Non-PDF file ingestion works with single-batch FileBatch
- **External APIs mocked:** Anthropic, Voyage AI, Document AI, GCS (per existing test conventions)
- **Correctness check:** Verify search excludes chunks from files with status != 'ready'
