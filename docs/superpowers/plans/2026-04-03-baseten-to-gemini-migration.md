# Baseten → Gemini 2.5 Flash Migration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Baseten enrichment backend with Google AI Studio's Gemini 2.5 Flash, switching from per-minute GPU billing to per-token pricing.

**Architecture:** Rename `baseten_*` config fields to `enrichment_*`, point at Google AI Studio's OpenAI-compatible endpoint. No changes to prompts, orchestration, or concurrency logic.

**Tech Stack:** Python, OpenAI SDK (unchanged), Pydantic settings, Cloud Run

**Spec:** `docs/superpowers/specs/2026-04-03-baseten-to-gemini-migration-design.md`

---

### Task 1: Update config.py

**Files:**
- Modify: `src/agentdrive/config.py:10-12`

- [ ] **Step 1: Replace baseten fields with enrichment fields**

Replace lines 10-12:

```python
# Before
baseten_api_key: str = ""
baseten_base_url: str = "https://model-wx41ye7q.api.baseten.co/environments/production/sync/v1"
baseten_model: str = "google/gemma-4-26B-A4B-it"

# After
enrichment_api_key: str = ""
enrichment_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
enrichment_model: str = "gemini-2.5-flash"
```

- [ ] **Step 2: Verify config loads**

Run: `cd /Users/rafey/Development/Rafey/AgentDrive && uv run python -c "from agentdrive.config import settings; print(settings.enrichment_model)"`
Expected: `gemini-2.5-flash`

- [ ] **Step 3: Commit**

```bash
git add src/agentdrive/config.py
git commit -m "refactor(config): rename baseten_* to enrichment_* with Gemini defaults"
```

---

### Task 2: Update enrichment client

**Files:**
- Modify: `src/agentdrive/enrichment/client.py:50-51,59,77,103,126`

- [ ] **Step 1: Run existing tests to confirm green baseline**

Run: `cd /Users/rafey/Development/Rafey/AgentDrive && uv run pytest tests/enrichment/test_client.py -v`
Expected: All tests PASS (they mock `openai.AsyncOpenAI`, not config values)

- [ ] **Step 2: Update client init (lines 50-51)**

```python
# Before
api_key=settings.baseten_api_key,
base_url=settings.baseten_base_url,

# After
api_key=settings.enrichment_api_key,
base_url=settings.enrichment_base_url,
```

- [ ] **Step 3: Update model references (lines 59, 77, 103, 126)**

Replace all 4 occurrences:

```python
# Before
model=settings.baseten_model,

# After
model=settings.enrichment_model,
```

- [ ] **Step 4: Run tests to verify nothing broke**

Run: `cd /Users/rafey/Development/Rafey/AgentDrive && uv run pytest tests/enrichment/ -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/agentdrive/enrichment/client.py
git commit -m "refactor(enrichment): point client at enrichment_* config fields"
```

---

### Task 3: Update .env.example

**Files:**
- Modify: `.env.example:14-17`

- [ ] **Step 1: Replace Baseten lines with enrichment lines**

Remove lines 14-17:
```
# Baseten (Gemma 4 enrichment)
BASETEN_API_KEY=your-key-here
BASETEN_BASE_URL=https://model-wx41ye7q.api.baseten.co/environments/production/sync/v1
BASETEN_MODEL=google/gemma-4-26B-A4B-it
```

Replace with:
```
# Enrichment (Gemini 2.5 Flash via Google AI Studio)
ENRICHMENT_API_KEY=your-key-here
```

- [ ] **Step 2: Commit**

```bash
git add .env.example
git commit -m "docs(env): update .env.example for Gemini enrichment"
```

---

### Task 4: Update cloud-run/service.yaml

**Files:**
- Modify: `cloud-run/service.yaml:49-57`

- [ ] **Step 1: Replace Baseten env vars with enrichment env vars**

Remove lines 49-57 (the 3 Baseten entries) and replace with:

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

Match the existing indentation in the file (8 spaces for `- name:`).

- [ ] **Step 2: Validate YAML syntax**

Run: `cd /Users/rafey/Development/Rafey/AgentDrive && uv run python -c "import yaml; yaml.safe_load(open('cloud-run/service.yaml'))"`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add cloud-run/service.yaml
git commit -m "chore(cloud-run): update service.yaml for Gemini enrichment"
```

---

### Task 5: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md:41,54,62,74`

- [ ] **Step 1: Update architecture tree (line 41)**

```markdown
# Before
├── enrichment/          # Gemma 4 contextual enrichment + table questions

# After
├── enrichment/          # Gemini 2.5 Flash contextual enrichment + table questions
```

- [ ] **Step 2: Update enrichment gotcha (line 54)**

```markdown
# Before
- **Enrichment mocked in all tests** — conftest.py has an autouse fixture that no-ops `enrich_chunks`, `generate_table_aliases`, `embed_file_chunks`, and `embed_file_aliases`. Enrichment uses Baseten (OpenAI-compatible API), not Anthropic.

# After
- **Enrichment mocked in all tests** — conftest.py has an autouse fixture that no-ops `enrich_chunks`, `generate_table_aliases`, `embed_file_chunks`, and `embed_file_aliases`. Enrichment uses Google AI Studio (OpenAI-compatible API) with Gemini 2.5 Flash.
```

- [ ] **Step 3: Update External APIs table (line 62)**

```markdown
# Before
| Baseten | Contextual enrichment (Gemma 4 26B-A4B) | `BASETEN_API_KEY`, `BASETEN_BASE_URL`, `BASETEN_MODEL` |

# After
| Google AI Studio | Contextual enrichment (Gemini 2.5 Flash) | `ENRICHMENT_API_KEY` |
```

- [ ] **Step 4: Update test mock reference (line 74)**

```markdown
# Before
- External APIs (Voyage, Cohere, Baseten, GCS) are mocked in all tests

# After
- External APIs (Voyage, Cohere, Google AI Studio, GCS) are mocked in all tests
```

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md for Gemini enrichment migration"
```

---

### Task 6: Update E2E test references

**Files:**
- Modify: `tests/e2e/test_pdf_pipeline.py:1,87`

- [ ] **Step 1: Update docstring (line 1)**

```python
# Before
"""E2E test: PDF upload → DocAI chunking → Baseten enrichment → Voyage embedding.

# After
"""E2E test: PDF upload → DocAI chunking → Gemini enrichment → Voyage embedding.
```

- [ ] **Step 2: Update assertion message (line 87)**

```python
# Before
assert len(enriched) > 0, f"No chunks have context_prefix. Enrichment (Baseten/Gemma 4) may have failed."

# After
assert len(enriched) > 0, f"No chunks have context_prefix. Enrichment (Gemini 2.5 Flash) may have failed."
```

- [ ] **Step 3: Run full test suite**

Run: `cd /Users/rafey/Development/Rafey/AgentDrive && uv run pytest tests/ -v --ignore=tests/e2e`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add tests/e2e/test_pdf_pipeline.py
git commit -m "docs(test): update e2e test references for Gemini enrichment"
```

---

### Task 7: Verify no remaining Baseten references

- [ ] **Step 1: Grep for any remaining baseten references**

Run: `cd /Users/rafey/Development/Rafey/AgentDrive && grep -ri "baseten" --include="*.py" --include="*.yaml" --include="*.yml" --include="*.md" --include="*.env*" . | grep -v node_modules | grep -v ".git/" | grep -v "docs/superpowers/specs/" | grep -v "docs/superpowers/plans/"`
Expected: No output (all references cleaned up). Spec/plan docs excluded since they describe the migration itself.

- [ ] **Step 2: Verify .env has the new key (if it exists)**

Check that local `.env` has `ENRICHMENT_API_KEY` set. If not, add it with your Gemini API key from aistudio.google.com.

- [ ] **Step 3: Final commit if any stragglers found**

Only if step 1 found remaining references.
