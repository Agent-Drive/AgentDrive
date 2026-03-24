# Ingestion Queue Design

## Problem

Uploading 15+ files simultaneously exhausts the SQLAlchemy connection pool (`QueuePool limit of size 5 overflow 10 reached`). Each upload spawns a `BackgroundTask` running `process_file()`, which holds a DB session for minutes during enrichment and embedding. No concurrency bound, no timeout, no recovery for files stuck in `processing` after a crash.

## Solution

Replace unbounded `BackgroundTask` concurrency with an in-process `asyncio.Queue` + bounded worker pool, a startup reaper for stuck files, and a timeout on each ingestion task.

## Prerequisites

### Add `updated_at` column to `TimestampMixin`

The reaper needs `updated_at` to identify stuck files. Currently `TimestampMixin` only has `created_at`. Add:

```python
updated_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True),
    server_default=func.now(),
    onupdate=func.now(),
    nullable=False,
)
```

Requires an Alembic migration. All models using `TimestampMixin` (files, chunks, etc.) get the column.

### Pin connection pool settings in `session.py`

Explicitly set pool size so worker math doesn't silently break if SQLAlchemy defaults change:

```python
engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_size=5,
    max_overflow=10,
)
```

### Add settings to `config.py`

```python
ingestion_workers: int = 3
ingestion_timeout_seconds: int = 900
reaper_threshold_minutes: int = 10
```

## Design

### 1. Ingestion Queue & Workers

**New file**: `src/agentdrive/services/queue.py`

Module-level state:
- `_queue: asyncio.Queue[UUID]` — unbounded FIFO queue of file IDs (UUIDs are 16 bytes each; unbounded is fine even for large bursts)
- `_workers: list[asyncio.Task]` — worker coroutine handles

Public API:
- `enqueue(file_id: UUID)` — puts file_id on the queue
- `start_workers(n: int = settings.ingestion_workers)` — spawns N worker tasks
- `stop_workers()` — cancels all workers, awaits graceful shutdown

Each worker loops forever:
1. `file_id = await _queue.get()`
2. Opens a new DB session via `async_session_factory()`
3. **Idempotency guard**: fetches the file, skips if status is not `PENDING` (handles duplicate enqueue from reaper + upload race)
4. Runs `process_file(file_id, session)` wrapped in `asyncio.wait_for(timeout=settings.ingestion_timeout_seconds)`
5. Handles timeout/error (see section 3)
6. `_queue.task_done()` in `finally`

**Concurrency limit: 3 workers (default, configurable).** Leaves 12 of 15 pool connections for request handling. 3 files x 5 concurrent Anthropic calls = 15 LLM calls, which is reasonable.

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

No periodic reaper — only runs at startup. During normal operation, the timeout ensures files don't get stuck permanently.

### 3. Timeout & Error Handling

```python
async def _worker():
    while True:
        file_id = await _queue.get()
        try:
            async with async_session_factory() as session:
                # Idempotency guard
                file = await session.get(File, file_id)
                if not file or file.status != FileStatus.PENDING:
                    continue

                try:
                    await asyncio.wait_for(
                        process_file(file_id, session),
                        timeout=settings.ingestion_timeout_seconds,
                    )
                except asyncio.TimeoutError:
                    await session.rollback()
                    file = await session.get(File, file_id)
                    file.status = FileStatus.FAILED
                    file.extra_metadata = {
                        **(file.extra_metadata or {}),
                        "error": "Ingestion timed out after 15 minutes",
                    }
                    await session.commit()
                    logger.error(f"File {file_id} timed out")
                except Exception:
                    await session.rollback()
                    file = await session.get(File, file_id)
                    if file and file.status != FileStatus.FAILED:
                        file.status = FileStatus.FAILED
                        file.extra_metadata = {
                            **(file.extra_metadata or {}),
                            "error": "Unexpected ingestion error",
                        }
                        await session.commit()
                    logger.exception(f"Unexpected error for {file_id}")
        finally:
            _queue.task_done()
```

Key details:
- `asyncio.wait_for` cancels the coroutine on timeout, interrupting any pending API call
- The session is created **outside** the `wait_for` scope, so it survives cancellation and remains usable after rollback
- Rollback clears partial flushes from the cancelled `process_file`
- Error reason stored in `extra_metadata` for API visibility (guarded against `None`)
- Both `TimeoutError` and generic `Exception` set status to `FAILED` — no file left in `processing` during normal operation
- `process_file`'s existing try/except handles normal errors; the outer handlers are safety nets

### 4. Graceful Shutdown

`stop_workers()` cancels all worker tasks immediately. A file mid-`process_file` will be left in `processing` status. The startup reaper on the next boot handles recovery (after the 10-minute threshold). This is acceptable because:
- Normal deploys on Cloud Run have a grace period, but ingestion can take minutes — waiting for completion is impractical
- The reaper threshold means at most a 10-minute delay before retry on next startup
- No data loss: partial chunks are uncommitted and rolled back; the file is re-processed from scratch

### 5. Integration Points

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

## Testing Strategy

### Unit tests (`tests/test_queue.py`)

- **Worker processes file**: enqueue a file_id, assert `process_file` is called with correct args
- **Concurrency bound**: enqueue 10 files, assert only N run concurrently (mock `process_file` with a slow coroutine, check active count)
- **Timeout sets FAILED**: mock `process_file` to hang, assert file status becomes FAILED with error in `extra_metadata`
- **Idempotency guard**: enqueue a file with status=READY, assert `process_file` is NOT called
- **Outer exception handler**: mock `process_file` to raise, assert file status becomes FAILED

### Unit tests for reaper

- **Resets stuck files**: create files with status=PROCESSING and old `updated_at`, run reaper, assert status=PENDING
- **Re-queues pending files**: create PENDING files, run reaper, assert `enqueue` called for each
- **Ignores recent processing files**: create PROCESSING file with recent `updated_at`, assert NOT reset

### Integration changes

- Existing upload tests in `test_files.py` mock `process_file` — they need to mock `enqueue` instead (or mock `process_file` at the `queue` module level)
- The test `conftest.py` does NOT run the lifespan, so workers won't start during tests — this is correct, tests should control the queue explicitly

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Queue type | In-process `asyncio.Queue` | No new infra; reaper covers durability gap; single Cloud Run instance |
| Concurrency | 3 workers (configurable) | Leaves 12 of 15 pool connections for requests |
| Reaper threshold | 10 minutes (configurable) | 2x worst-case ingestion time |
| Timeout | 15 minutes (configurable) | Generous for large PDFs; tight enough to not block queue |
| Periodic reaper | No | Timeout prevents stuck files during operation; reaper only needed after crash |
| Queue depth limit | Unbounded | UUIDs are 16 bytes; even 10K files = 160KB. Not worth the complexity of backpressure. |
| Shutdown strategy | Cancel immediately | Reaper recovers on next boot; waiting for completion impractical for multi-minute tasks |
| Duplicate enqueue | Idempotency guard in worker | Worker skips files not in PENDING status; simple, no coordination needed |

## Future Migration Path

When multi-instance scaling is needed, replace `asyncio.Queue` with Google Cloud Tasks. The `process_file` function stays the same — only the dispatch mechanism changes. The reaper becomes unnecessary as Cloud Tasks provides at-least-once delivery and DLQ.
