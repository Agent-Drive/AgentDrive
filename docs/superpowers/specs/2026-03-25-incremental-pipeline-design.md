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

**Files changed:** `services/storage.py`, `chunking/pdf.py`

### 2. Incremental Chunk Processing & DB Commits

**Current:** All chunks accumulated in SQLAlchemy session → single commit at end.

**New:** Process and commit in batches aligned with Document AI's 30-page page splits. The pipeline runs in three phases:

```
Phase 1 — Chunking (incremental):
  For each 30-page batch:
    Document AI → markdown → parent/child chunks → commit to DB → free memory

Phase 2 — Summarization (one shot):
  Read all committed chunks → generate doc summary + section summaries → save

Phase 3 — Enrichment + Embedding (incremental):
  For each batch of chunks:
    Enrich with [doc summary + section summary + neighbors] → embed → commit
```

Each phase commits incrementally. For small docs (≤30 pages), Phase 1 is a single batch — functionally identical to current behavior.

**Batch tracking:** New `FileBatch` model:

```
FileBatch
  ├── file_id
  ├── batch_index (0, 1, 2...)
  ├── page_range (e.g., "1-30", "31-60")
  ├── status (pending / processing / completed / failed)
  └── chunk_count
```

**Files changed:** `services/ingest.py`, `models/` (new FileBatch), `embedding/pipeline.py`, `alembic/` (migration)

### 3. Two-Pass Enrichment

**Current:** Full document text (~100-120K tokens for large docs) sent as cached context with every enrichment call. Attention quality degrades on long contexts.

**New:** Two passes:

**Pass 1 — Summarization:**
Full document text → LLM → document summary (~500 tokens) + section summaries (~200 tokens each).

**Pass 2 — Per-chunk enrichment:**
Each chunk enriched with `[doc summary + section summary + ±3 neighbor chunks]` → LLM → context prefix. ~3-5K tokens per call regardless of document size.

**Quality comparison:**

| Scenario | Current (full context) | Two-pass (summaries + local) |
|----------|----------------------|------------------------------|
| Small docs | Full doc in context | Summary + local — comparable quality |
| Large docs | Degraded (attention dilution on 120K tokens) | Focused context — **better quality** |
| Token cost | O(chunks x doc_size) | O(doc_size + chunks x 5K) — much cheaper |

**Files changed:** `enrichment/contextual.py`

### 4. File Status & Progress Tracking

**Current:** `pending → processing → ready / failed`

**New:** File statuses unchanged. Add progress metadata to file records:

```
total_batches: int
completed_batches: int
current_phase: "chunking" | "summarizing" | "enriching" | null
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

For small docs: `total_batches: 1`, progress flips quickly. Clients checking `status == "ready"` see no change.

**Files changed:** `schemas/` (add fields to status response), `models/` (file metadata fields)

### 5. Error Handling & Resume

**Current:** Any failure → file marked "failed", full restart required.

**New:** Granular failure and resume at the batch/phase level:

```
Failure in Phase 1 (chunking):
  Completed batches: committed, chunks saved
  Resume: retry from the failed batch, skip completed ones

Failure in Phase 2 (summarization):
  All chunks committed from Phase 1
  Resume: regenerate summary (one LLM call)

Failure in Phase 3 (enrichment/embedding):
  Enriched chunks committed, unenriched chunks still in DB
  Resume: enrich remaining chunks only
```

**Resume mechanism:** `process_file()` inspects existing state:

```python
batches = get_batches(file_id)
if no batches:
    start from Phase 1
elif all batches completed and no summary:
    start from Phase 2
elif summary exists and unenriched chunks remain:
    start from Phase 3
elif all chunks enriched and unembedded chunks remain:
    resume embedding
```

**Retry policy:** Max 3 retries before permanent failure (configurable via `config.py`).

**Files changed:** `services/ingest.py`, `services/queue.py`

## Boundary: What Changes vs. What Doesn't

```
Changed:
  services/ingest.py        Phase-based pipeline, incremental commits
  services/storage.py       Add download_stream(), temp file support
  chunking/pdf.py           Accept stream/temp file instead of bytes
  enrichment/contextual.py  Two-pass: summarize then enrich with local context
  embedding/pipeline.py     Process per-batch instead of all-at-end
  models/                   Add FileBatch model, file progress metadata
  schemas/                  Add batch progress to file status response
  alembic/                  Migration for file_batch table + file metadata fields
  config.py                 Add max_retries config

NOT changed:
  routers/                  No API changes (upload still 32MB)
  chunking/registry.py      Chunker interface unchanged
  chunking/markdown.py      Unchanged
  chunking/hierarchy.py     Unchanged
  search/                   Unchanged (already filters by file status)
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
- **Unit tests:** Resume logic (simulate failures at each phase, verify correct restart point)
- **Integration tests:** Full pipeline with incremental commits (verify chunks appear in DB after each batch)
- **Integration tests:** FileBatch tracking (verify progress metadata updates correctly)
- **Regression tests:** Small doc ingestion produces identical results to current pipeline
- **External APIs mocked:** Anthropic, Voyage AI, Document AI, GCS (per existing test conventions)
