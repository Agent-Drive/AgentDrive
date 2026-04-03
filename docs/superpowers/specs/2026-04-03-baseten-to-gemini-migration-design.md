# Migration: Baseten → Google AI Studio (Gemini 2.5 Flash)

## Context

The enrichment service uses Baseten to run Gemma 4 26B on a dedicated A100 GPU for contextual chunk enrichment. This costs ~$7.89/hr with per-minute GPU billing regardless of request volume, resulting in unpredictable costs for bursty workloads.

## Decision

Replace Baseten with Google AI Studio's Gemini 2.5 Flash endpoint. This provides:

- **Predictable cost**: Pay-per-token (~$0.15/M input, $0.60/M output) instead of per-minute GPU billing
- **Zero infrastructure**: No GPU management, scale-to-zero is automatic
- **Minimal code change**: Google AI Studio exposes an OpenAI-compatible chat completions API — the existing `openai.AsyncOpenAI` client works as-is

## Scope

### Files changed (6)

| File | Change |
|------|--------|
| `src/agentdrive/config.py` | Rename `baseten_*` fields to `enrichment_*`, update default base URL and model |
| `src/agentdrive/enrichment/client.py` | Point at new `settings.enrichment_*` fields (6 references: 1 api_key, 1 base_url, 4 model) |
| `.env.example` | Remove all `BASETEN_*` lines and comment, add `ENRICHMENT_API_KEY` with new comment |
| `cloud-run/service.yaml` | Remove 3 existing `BASETEN_*` env entries, replace with `ENRICHMENT_*` entries and new secret reference |
| `CLAUDE.md` | Update External APIs table, enrichment gotcha, and architecture tree comment to reference Gemini instead of Baseten |
| `tests/e2e/test_pdf_pipeline.py` | Update Baseten references in docstring (line 1) and assertion message (line 87) |

### Files unchanged

- `src/agentdrive/enrichment/contextual.py` — uses `EnrichmentClient` abstraction, no provider references
- `src/agentdrive/enrichment/table_questions.py` — same
- `src/agentdrive/services/ingest.py` — orchestration layer, no provider references
- Unit/integration test files — mock at OpenAI SDK level, already provider-agnostic

## Config Design

### config.py

```python
enrichment_api_key: str = ""                # from env ENRICHMENT_API_KEY
enrichment_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
enrichment_model: str = "gemini-2.5-flash"
```

### .env.example

Remove `BASETEN_API_KEY`, `BASETEN_BASE_URL`, `BASETEN_MODEL` and their comment. Replace with:

```
ENRICHMENT_API_KEY=your-key-here
```

`ENRICHMENT_BASE_URL` and `ENRICHMENT_MODEL` have sensible defaults in `config.py`. They can be overridden via env vars if needed (Pydantic settings supports this automatically).

## Client Change

```python
# enrichment/client.py — __init__
self._client = openai.AsyncOpenAI(
    api_key=settings.enrichment_api_key,
    base_url=settings.enrichment_base_url,
    timeout=30.0,
)

# All 4 generate_* methods: model=settings.enrichment_model
```

No changes to prompts, error handling, concurrency (semaphore of 5), or response parsing. `response_format={"type": "json_object"}` is supported on Gemini's OpenAI-compatible endpoint.

## Deployment Changes

### cloud-run/service.yaml

```yaml
- name: ENRICHMENT_API_KEY
  valueFrom:
    secretKeyRef:
      key: latest
      name: agentdrive-enrichment-api-key
- name: ENRICHMENT_BASE_URL
  value: "https://generativelanguage.googleapis.com/v1beta/openai/"
- name: ENRICHMENT_MODEL
  value: "gemini-2.5-flash"
```

### Deployment steps

1. Create `agentdrive-enrichment-api-key` secret in GCP Secret Manager with Gemini API key
2. Deploy updated code
3. Verify enrichment works on a test file
4. Delete old `agentdrive-baseten-api-key` secret only after quality is validated in production

## Risk

- **Gemini 2.5 Flash enrichment quality is untested** against Gemma 4 26B for this specific task. If quality regresses, the config is provider-agnostic — swap `ENRICHMENT_BASE_URL` and `ENRICHMENT_MODEL` to any OpenAI-compatible endpoint. The old Baseten secret is retained until quality is confirmed.
- **Rate limits**: Default Gemini quotas should be sufficient for 5 concurrent requests. Self-service quota increase available in Google Cloud Console if needed.
