# Resumable Upload via GCS Signed URLs

**Sub-project 3 of 3** for [Issue #17: Support large documents (500+ pages, 50MB+)](https://github.com/Agent-Drive/AgentDrive/issues/17)

**Depends on:** Sub-projects 1 and 2 (incremental pipeline + batch Document AI) should be completed first, but this sub-project has no code dependency on them — it only changes the upload path, not the processing pipeline.

## Context

The current upload endpoint reads the entire file into memory (`data = await file.read()`), validates size (≤32MB), then uploads to GCS. This creates a hard 32MB limit and puts memory pressure on the server for large files.

This sub-project adds a two-step upload flow for large files using GCS resumable upload signed URLs. The client uploads directly to GCS — our server never touches the file bytes.

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Small files (≤32MB) | Keep current direct upload | Simple, no client changes needed |
| Large files (>32MB) | GCS signed resumable URL | Client uploads directly to GCS; server stays lightweight |
| New limit | Configurable, default 5GB | GCS resumable upload supports up to 5TB |
| MCP tool | Update to use signed URL flow for large files | MCP tool reads file from disk, can detect size |
| Auth | Signed URL scoped to specific path + expiry | 1-hour expiry, scoped to exact GCS blob path |

## Design

### 1. Two-Step Upload Flow (New Endpoint)

```
Step 1: Client requests a signed upload URL
  POST /v1/files/upload-url
  Body: { "filename": "large.pdf", "content_type": "application/pdf", "file_size": 100000000, "collection": "..." }
  Response: { "file_id": "...", "upload_url": "https://storage.googleapis.com/...", "expires_at": "..." }

Step 2: Client uploads directly to GCS using the signed URL
  PUT {upload_url}
  Body: <raw file bytes>
  (This goes directly to GCS, not our server)

Step 3: Client notifies our API that upload is complete
  POST /v1/files/{file_id}/complete
  Response: { "id": "...", "status": "pending", ... }
  (Server verifies the file exists in GCS, enqueues for processing)
```

### 2. Signed URL Generation

GCS provides `generate_signed_url()` for resumable uploads:

```python
blob.generate_signed_url(
    version="v4",
    expiration=timedelta(hours=1),
    method="PUT",
    content_type=content_type,
)
```

**Requirements:**
- **Service account JSON key required** — `generate_signed_url(version="v4")` requires service account credentials, NOT user ADC from `gcloud auth application-default login`. Set `GOOGLE_APPLICATION_CREDENTIALS=/path/to/key.json`.
- Service account must have `storage.objects.create` permission on the bucket
- URL is scoped to the exact blob path (tenant-isolated)
- 1-hour expiry (configurable)

### 3. File Record Lifecycle

```
POST /v1/files/upload-url:
  Create File record with status="uploading"
  (New status — not yet enqueued for processing)

POST /v1/files/{file_id}/complete:
  Verify file exists at expected GCS path
  Update File record: status="pending", file_size=actual size from GCS
  Enqueue for processing
```

**New FileStatus:** `UPLOADING` — file record created but bytes not yet in GCS.

### 4. Upload Size Config

```python
max_upload_bytes: int = 32 * 1024 * 1024  # Direct upload limit (unchanged)
max_signed_upload_bytes: int = 5 * 1024 * 1024 * 1024  # 5GB for signed URL uploads
signed_url_expiry_hours: int = 1
```

The direct upload endpoint retains its 32MB limit. The signed URL endpoint validates `file_size` against `max_signed_upload_bytes`.

### 5. MCP Tool Update

The `upload_file` MCP tool currently reads the file and POSTs to `/v1/files`. Update to:

```
1. Check file size on disk
2. If ≤32MB: use current direct upload (unchanged)
3. If >32MB:
   a. POST /v1/files/upload-url to get signed URL
   b. PUT file bytes to signed URL
   c. POST /v1/files/{file_id}/complete
```

This is transparent to the MCP client — the tool still takes a `path` argument.

### 6. Incomplete Upload Cleanup

Files stuck in `status="uploading"` for >24 hours should be cleaned up. Extend the existing reaper:

```
reap_stuck_files():
  existing: reset stuck PROCESSING files
  new: delete UPLOADING files older than 24 hours (+ delete GCS blob if exists)
```

## Boundary: What Changes vs. What Doesn't

```
Changed:
  routers/files.py          Add /upload-url and /complete endpoints
  services/storage.py       Add generate_signed_url() method
  models/types.py           Add UPLOADING status
  schemas/files.py          Add request/response schemas for signed URL flow
  config.py                 Add max_signed_upload_bytes, signed_url_expiry_hours
  mcp/server.py             Update upload_file tool for large files
  services/queue.py         Extend reaper for UPLOADING cleanup

NOT changed:
  services/ingest.py        Processing pipeline unchanged
  chunking/                 Unchanged
  enrichment/               Unchanged
  embedding/                Unchanged
  search/                   Unchanged
  dependencies.py           Auth unchanged (signed URL endpoints still require API key)
```

## Non-Goals

- Client-side resumable upload logic (retries on disconnect) — that's client responsibility
- Multipart upload — signed URL with PUT is simpler
- Direct browser upload from a web UI

## Testing Strategy

- **Unit tests:** Signed URL generation with correct scoping and expiry
- **Unit tests:** Upload completion flow (verify GCS, update status, enqueue)
- **Unit tests:** Rejection of files exceeding max_signed_upload_bytes
- **Unit tests:** Incomplete upload cleanup in reaper
- **Integration tests:** Full two-step flow (mock GCS)
- **Integration tests:** MCP tool selects correct path based on file size
- **Regression tests:** Direct upload (≤32MB) unchanged
- **External APIs mocked:** GCS signed URL generation, blob existence checks
