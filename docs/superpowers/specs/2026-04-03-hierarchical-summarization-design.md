# Hierarchical Summarization for Large Documents

**Issue:** #27
**Date:** 2026-04-03
**Status:** Approved

## Problem

`_phase2_summarization` in `services/ingest.py` concatenates all parent chunks into a single string and sends it as one LLM call to Gemini 2.5 Flash. For very large documents, this risks context window overflow, degraded summary quality, and unnecessary cost.

Current upper bound is ~100 pages (~70k tokens), which is fine today. This change adds a safety valve for when document sizes grow.

## Decision

**Approach A: Threshold gate** — add a token count check in `_phase2_summarization`. Documents under 200k tokens use the existing single-call path (unchanged). Documents over 200k tokens use a map-reduce hierarchical path.

Rejected alternatives:
- **Strategy classes** — over-engineered for a rarely-triggered branch
- **Always map-reduce** — changes working behavior for no benefit on small docs

## Design

### Flow

```
_phase2_summarization(file, session)
│
├─ Query all ParentChunks (unchanged)
├─ count_tokens(concatenated text)
│
├─ ≤ 200k tokens
│   └─ generate_document_summary(text)          ← existing path, untouched
│
└─ > 200k tokens
    ├─ Batch parents into groups (~50k tokens each)
    ├─ Map phase: for each group (concurrent via asyncio.gather):
    │   └─ generate_group_summary(group_text)
    │       returns { "summary": "...", "section_summaries": [...] }
    ├─ Collect all intermediate summaries
    └─ Reduce phase: generate_document_summary(intermediates)
        returns { "document_summary": "...", "section_summaries": [...] }
```

Output contract is identical regardless of path. `FileSummary` gets the same `document_summary` + `section_summaries`. Phase 3 enrichment is unaffected.

### Batching

- Target batch size: **50k tokens**
- Never split a parent chunk across batches
- If a single parent exceeds 50k, it gets its own batch
- At 200k threshold / 50k per batch = ~4 parallel map calls + 1 reduce call

### Constants

```python
MAX_SINGLE_PASS_TOKENS = 200_000
GROUP_BATCH_TOKENS = 50_000
```

Defined as constants in `services/ingest.py`. No config setting needed.

### Map Phase Prompt

New method `EnrichmentClient.generate_group_summary()`:

```
"You are summarizing section {group_index} of {total_groups}
 of a larger document. Produce:
 1. A summary of this section (2-3 sentences)
 2. section_summaries for each major section within this portion

 <document_section>
 {group_text}
 </document_section>

 Return JSON: {"summary": "...", "section_summaries": [{"heading": "...", "summary": "..."}]}"
```

### Reduce Phase

New method `EnrichmentClient.generate_reduce_summary()` with a dedicated prompt. The existing `SUMMARY_PROMPT` wraps input in `<document>` tags and says "Analyze this document" — feeding it pre-summarized text would confuse the model. The reduce prompt instead instructs the LLM to synthesize group summaries into a single coherent summary, merging and deduplicating section summaries across groups.

Reduce input format:

```
Group 1 (of 4):
Summary: ...
Sections:
- Introduction: ...
- Background: ...

Group 2 (of 4):
Summary: ...
Sections:
- Methodology: ...
```

Returns the same schema as `generate_document_summary()`: `{ "document_summary": "...", "section_summaries": [...] }`. The LLM handles merging/deduplication of section summaries across groups into a single flat list.

### Concurrency

Map phase calls run concurrently via `asyncio.gather` with a semaphore (max 5 concurrent). At 200k/50k = ~4 calls this rarely matters, but protects against very large documents producing 20+ batches.

### Token Settings

Same `max_tokens=16384` for both map and reduce calls.

**Note:** Token counts use `cl100k_base` tokenizer (tiktoken), not Gemini's native tokenizer. The counts are approximate but close enough for a threshold-based safety valve.

## Files Changed

| File | Change |
|------|--------|
| `services/ingest.py` | Token check, `_batch_parents()` helper, `_hierarchical_summarize()` orchestration with semaphore |
| `enrichment/client.py` | New `generate_group_summary()` (map) and `generate_reduce_summary()` (reduce) methods with dedicated prompts |
| `enrichment/contextual.py` | New `generate_group_summary()` thin wrapper (mirrors `generate_document_summary()` pattern) |
| `tests/` | Batch logic tests, threshold routing tests, hierarchical path tests |

## Files NOT Changed

- `models/file_summary.py` — no schema changes
- `enrichment/client.py` existing methods (`generate_summary`, `generate_context`) — untouched
- `chunking/` — untouched
- Phase 3 (enrichment), Phase 4 (embedding) — untouched
- `config.py` — no new settings

## Scope

- ~3 files modified, ~80-100 lines added
- No schema changes
- No contract changes (FileSummary output identical)
- Existing path for docs ≤ 200k tokens is completely untouched
- Low risk

## Error Handling

Map phase calls follow the same pattern as existing `generate_summary()`: catch exceptions, log warning, return fallback. If a group summary fails, it returns `{"summary": "", "section_summaries": []}`. The reduce phase proceeds with whatever groups succeeded — a partial summary is better than no summary. If all groups fail, the reduce phase receives empty input and produces an empty summary (same fallback as today's single-call failure mode).
