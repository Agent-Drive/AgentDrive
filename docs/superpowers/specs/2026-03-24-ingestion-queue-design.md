# Ingestion Queue Design

## Problem

Uploading 15+ files simultaneously exhausts the SQLAlchemy connection pool (`QueuePool limit of size 5 overflow 10 reached`). Each upload spawns a `BackgroundTask` running `process_file()`, which holds a DB session for minutes during enrichment and embedding. No concurrency bound, no timeout, no recovery for files stuck in `processing` after a crash.

## Solution

Replace unbounded `BackgroundTask` concurrency with an in-process `asyncio.Queue` + bounded worker pool, a startup reaper for stuck files, and a timeout on each ingestion task.

## Design

### 1. Ingestion Queue & Workers

**New file**: `src/agentdrive/services/queue.py`

Module-level state:
- `_queue: asyncio.Queue[UUID]` — unbounded FIFO queue of file IDs
- `_workers: list[asyncio.Task]` — worker coroutine handles

Public API:
- `enqueue(file_id: UUID)` — puts file_id on the queue
- `start_workers(n: int = 3)` — spawns N worker tasks
- `stop_workers()` — cancels all workers, awaits graceful shutdown

Each worker loops forever:
1. `file_id = await _queue.get()`
2. Opens a new DB session via `async_session_factory()`
3. Runs `process_file(file_id, session)` wrapped in `asyncio.wait_for(timeout=900)`
4. Handles timeout/error (see section 3)
5. `_queue.task_done()` in `finally`

**Concurrency limit: 3 workers.** Leaves 12 of 15 pool connections for request handling. 3 files x 5 concurrent Anthropic calls = 15 LLM calls, which is reasonable.

### 2. Startup Reaper

Runs during app lifespan startup, before workers begin consuming:

1. Query files where `status = 'processing'` AND `updated_at < now() - interval '10 minutes'`
2. Reset each to `status = 'pending'`
3. Query ALL files where `status = 'pending'`
4. `enqueue(file_id)` for each

This handles two cases:
- Files stuck in `processing` after a crash (step 1-2)
- Files uploaded but never ingested, e.g., crash between upload and background task start (step 3-4)

Lives in `services/queue.py` as `reap_stuck_files(session: AsyncSession)`.

No periodic reaper — only runs at startup. During normal operation, the 15-minute timeout ensures files don't get stuck permanently.

### 3. Timeout & Error Handling

```python
async def _worker():
    while True:
        file_id = await _queue.get()
        try:
            async with async_session_factory() as session:
                try:
                    await asyncio.wait_for(
                        process_file(file_id, session),
                        timeout=900,
                    )
                except asyncio.TimeoutError:
                    await session.rollback()
                    file = await session.get(File, file_id)
                    file.status = FileStatus.FAILED
                    file.extra_metadata = {
                        **file.extra_metadata,
                        "error": "Ingestion timed out after 15 minutes",
                    }
                    await session.commit()
                    logger.error(f"File {file_id} timed out")
                except Exception:
                    logger.exception(f"Unexpected error for {file_id}")
        finally:
            _queue.task_done()
```

- `asyncio.wait_for` cancels the coroutine on timeout, interrupting any pending API call
- Rollback clears partial flushes from the cancelled `process_file`
- Error reason stored in `extra_metadata` for API visibility
- `process_file`'s existing try/except handles normal errors and sets `status=FAILED`; the outer timeout is a safety net for hung external calls

### 4. Integration Points

**`main.py`**: Add lifespan context manager:
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    async with async_session_factory() as session:
        await reap_stuck_files(session)
    start_workers()
    yield
    await stop_workers()
```

**`routers/files.py`**: Replace `BackgroundTasks` parameter and inline `run_ingest` closure with `enqueue(file_record.id)`.

**`services/ingest.py`**: No changes. `process_file()` continues to work as-is.

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Queue type | In-process `asyncio.Queue` | No new infra; reaper covers durability gap; single Cloud Run instance |
| Concurrency | 3 workers | Leaves 12 of 15 pool connections for requests |
| Reaper threshold | 10 minutes | 2x worst-case ingestion time |
| Timeout | 15 minutes | Generous for large PDFs; tight enough to not block queue |
| Periodic reaper | No | Timeout prevents stuck files during operation; reaper only needed after crash |

## Future Migration Path

When multi-instance scaling is needed, replace `asyncio.Queue` with Google Cloud Tasks. The `process_file` function stays the same — only the dispatch mechanism changes. The reaper becomes unnecessary as Cloud Tasks provides at-least-once delivery and DLQ.
