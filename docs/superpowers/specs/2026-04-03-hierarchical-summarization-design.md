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

Reuses existing `generate_document_summary()` with concatenated group summaries as input instead of raw document text. No changes to the function or its prompt.

Reduce input format:

```
Group 1 summary: ...
Sections: ...

Group 2 summary: ...
Sections: ...
```

### Token Settings

Same `max_tokens=16384` for both map and reduce calls.

## Files Changed

| File | Change |
|------|--------|
| `services/ingest.py` | Token check, `_batch_parents()` helper, `_hierarchical_summarize()` orchestration |
| `enrichment/client.py` | New `generate_group_summary()` method |
| `enrichment/contextual.py` | New `generate_group_summaries()` entry point |
| `tests/` | Batch logic tests, threshold routing tests, hierarchical path tests |

## Files NOT Changed

- `models/file_summary.py` — no schema changes
- `enrichment/client.py` existing methods — untouched
- `chunking/` — untouched
- Phase 3 (enrichment), Phase 4 (embedding) — untouched
- `config.py` — no new settings

## Scope

- ~3 files modified, ~80-100 lines added
- No schema changes
- No contract changes (FileSummary output identical)
- Existing path for docs ≤ 200k tokens is completely untouched
- Low risk
