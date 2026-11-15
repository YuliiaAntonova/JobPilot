# Migrate Resume Tailoring to L7 CrewAI

Replace the current Untitled.ipynb-style tailoring in `agentic_rest_api_slim` with the exact CrewAI flow from `crew_job/L7_job_application_crew.ipynb`, while keeping the existing FastAPI contracts and Harvard `cv.yml` render/PDF path.

## Goal

| Current (`agentic_rest_api_slim`) | Target (`L7_job_application_crew.ipynb`) |
|---|---|
| Sequential LLM calls in `notebook_tailoring` | CrewAI: Researcher → Profiler → Resume Strategist |
| Section JSON → `apply_notebook_resume_to_cv` | Tailored Markdown → `markdown_to_cv_json` → CV schema |
| LLM via aisuite / Cursor (`APP_LLM_MODEL`) | CrewAI + OpenAI (`OPENAI_MODEL_NAME`) |
| Cover letter + optimization report | Not in L7 (optional keep via separate endpoint) |

**Do not break** `POST /analyze/resume-tailor/analyze|generate|preview|pdf` — the frontend already depends on them.

---

## Current vs target flow

### Current (live API)

1. `POST /analyze/resume-tailor/analyze` → `orchestrator.run_analyze`
2. Plain text from structured profile → `parse_resume` + `parse_job_description`
3. Skill match score → `phase: ready_to_generate`, `ask_user: []`
4. `POST …/generate` → `pipeline.tailor_resume` → merge into `cv.yml` → preview/PDF
5. Optional JobBERT before/after

**Key files:**

- `job_application/resume/safe_tailoring_router.py`
- `job_application/resume/safe_tailoring/orchestrator.py`
- `job_application/resume/notebook_tailoring/pipeline.py`
- `job_application/resume/notebook_tailoring/cv_bridge.py`

> Note: `safe_tailoring/_core.py` ATS/ask_user logic is largely unused by the live analyze/generate path (JobBERT only). Do not mix it with L7.

### Target (L7)

1. Inputs: `{personal_writeup, job_posting_text, resume_text}`
2. Crew kickoff (tools off; texts via placeholders)
3. Output: `tailored_resume.md`
4. `markdown_to_cv_json` (OpenAI) → `cv.json` shape
5. HTML/PDF render

**Agents/tasks** (copy prompts 1:1 from the notebook):

- Researcher → `research_task` (`async_execution=True`)
- Profiler → `profile_task` (`async_execution=True`)
- Resume Strategist → `resume_strategy_task` (`context=[research, profile]`)
- Interview Preparer — keep disabled

---

## Input mapping: notebook files → slim chat profile

In L7, `input/filled_cv.*` are **not** a special resume format — they are a disk snapshot of an already-filled CV. In slim the same snapshot already lives in the DB / request as `structured` after chat (or PDF import / editor save). Crew never opens files itself: `kickoff` only receives three in-memory strings.

### L7 notebook loads (today)

| File | How loaded | Role |
|------|------------|------|
| `input/filled_cv.md` | `Path.read_text()` → `resume_text` | Full resume body for `{resume_text}` |
| `input/job_posting.txt` | `Path.read_text()` → `job_posting_text` | JD for `{job_posting_text}` |
| `input/filled_cv.json` | `build_crew_inputs_from_cv(...)` | Builds `personal_writeup` (+ optional `github_url`) |
| `input/filled_cv.json` (again) | `contacts_path` in `markdown_to_cv_json` | Backfill empty `basics` contacts/links after MD→JSON |

Kickoff dict (exact keys — only these three):

```python
job_application_inputs = {
    "personal_writeup": ...,   # from filled_cv.json via cv_inputs
    "job_posting_text": ...,   # from job_posting.txt
    "resume_text": ...,        # from filled_cv.md
}
```

`github_url` may be extracted from JSON but is **not** passed into kickoff when tools are off.

`personal_writeup` derivation (`cv_inputs.extract_personal_writeup`):

1. Prefer `basics.summary` or `basics.note`
2. Else synthesize from headline, years, skills, latest experience

### Slim source of truth

```text
чат / PDF / редактор кабинета
        ↓
  resume_profiles.structured   # Harvard cv.yml JSON shape  ≈  filled_cv.json
  (+ optional body.structured from frontend)
        ↓
  normalize_to_cv(structured)
        ↓
  adapter (no disk I/O)
        ↓
  { personal_writeup, resume_text, job_posting_text }
        ↓
  crew.kickoff(inputs=...)
        ↓
  tailored_resume.md → markdown_to_cv_json(contacts_source=structured)
        ↓
  normalize_to_cv → Harvard preview / PDF
```

- Profile table: `resume_profiles.structured` (JSON), `profile_text` (plain mirror), `chat_answers`, `desired_role`, `source`
- Chat save path: answers → `chat_answers_to_cv` / `normalize_to_cv` → upsert
- On-disk `cv/cv.yml` + `cv/cv.html` are preview artifacts, **not** the tailor source of truth
- Router already resolves profile via `_resolve_structured(db, user, body.structured)` when the body omits structured

### File → API mapping (implement this adapter)

| Notebook file / role | Slim source | How to build |
|----------------------|-------------|--------------|
| `job_posting.txt` → `job_posting_text` | Request `job_description` (offer JD) | Pass through 1:1 |
| `filled_cv.json` (schema) | `structured` from body or DB | `cv = normalize_to_cv(structured)` |
| `filled_cv.json` → `personal_writeup` | Same `cv` | `extract_personal_writeup(cv)` — **no separate chat field** |
| `filled_cv.md` → `resume_text` | Same `cv` | `structured_to_resume_md(cv)` matching `render_cv_json_to_md` / `filled_cv.md` style (**not** current ATS plain text) |
| `filled_cv.json` as `contacts_path` | Original `structured` dict | `markdown_to_cv_json(..., contacts_source=structured)` instead of a file path |

### When inputs are built (analyze vs generate)

| Phase | Endpoint | What happens |
|-------|----------|--------------|
| Analyze (no crew) | `POST …/resume-tailor/analyze` | Validate JD (≥40) + resume (≥80); from `structured` build `resume_text` + `personal_writeup`; optional JobBERT before; stash crew-ready snapshot in `analysis` (`pipeline: "crew_l7"`, texts, etc.); `ask_user: []`, `phase: ready_to_generate` |
| Generate (crew) | `POST …/resume-tailor/generate` | Read snapshot from `analysis` + fresh `job_description`; `kickoff`; MD → JSON + contact backfill; `normalize_to_cv`; preview/PDF; JobBERT after |

Frontend contract stays the same: still sends `job_description` + `structured` (or API loads profile from DB). No new “writeup” or “upload filled_cv” UI.

### Gaps vs current live API (must close in adapter)

| Gap | Mitigation |
|-----|------------|
| Slim feeds LLM **plain/ATS text** today; L7 expects **Markdown** like `filled_cv.md` | Add `structured_to_resume_md` (port/adapt `render_cv_json_to_md`) |
| No first-class `personal_writeup` in chat | Derive via ported `extract_personal_writeup` / `synthesize_personal_writeup` |
| Contact backfill used a JSON path | Accept in-memory `contacts_source: dict` in ported `md_to_cv_json` |
| Empty / unfinished chat profile | Same as today: refuse generate without `structured` |

**Rule:** runtime must not depend on `input/` or `output/` directories. Temp paths only if a CrewAI task insists on writing `tailored_resume.md` to disk.

---

## Step 0 — Environment

1. Use **Python 3.11** (CrewAI 0.28 is documented against 3.11; 3.12+ is risky).
2. Prefer a dedicated venv so langchain 0.1 does not fight newer stacks.
3. Capture a baseline from the notebook: one JD + `filled_cv.md` → reference `tailored_resume.md` / JSON.

---

## Step 1 — Dependencies (`requirements.txt`)

Add the **L7 slice only** (do not pull the full LlamaIndex prepare stack unless you also port prepare):

```text
# --- CrewAI L7 (from crew_job) ---
# crewai 0.28.x needs pkg_resources; setuptools>=81 removed it
setuptools==80.10.2

crewai==0.28.8
langchain==0.1.20
langchain_community==0.0.38
tiktoken==0.7.0

openai
```

`python-dotenv` already present in slim.

**Do not install:**

- `crewai_tools` (old `lancedb` pin breaks on Python 3.11+)
- `jupyter-ai` / `langchain>=0.3` (conflicts with CrewAI 0.28)
- LlamaIndex packages (needed for prepare notebook, not for L7 kickoff)

**Already in slim (keep):** FastAPI stack, `PyYAML`, `sentence-transformers` (JobBERT), aisuite/cursor for other features.

After install, verify:

```bash
pip install -r requirements.txt
python -c "from crewai import Agent, Task, Crew; import pkg_resources; print('ok')"
```

Watch for conflicts with slim pins such as `httpx>=0.27,<0.28`.

### Env vars (`.env` / `.env.example`)

| Variable | Required for | Notes |
|----------|--------------|--------|
| `OPENAI_API_KEY` | Crew + `md_to_cv_json` | Required for exact L7 behavior |
| `OPENAI_MODEL_NAME` | CrewAI | Notebook default: `gpt-4o-mini` |
| `APP_LLM_MODEL` | Rest of API | Optional; leave for chat/ATS/etc. |

Optional feature flag:

```text
TAILORING_PIPELINE=crew_l7   # or notebook (legacy)
```

---

## Step 2 — Port modules from `crew_job`

Suggested package layout:

```text
job_application/resume/crew_tailoring/
  __init__.py
  crew.py                 # Agent / Task / Crew definitions (exact L7 prompts)
  runner.py               # kickoff wrapper for in-memory strings
  cv_inputs.py            # from crew_job/cv_inputs.py (accept dict, not only file)
  md_to_cv_json.py        # from crew_job/md_to_cv_json.py
  template_extractor.py   # from crew_job/template_extractor.py
  utils.py                # OpenAI key helper → slim config/env
  run_usage.py            # optional; or map into pack_token_usage
  cv_template.json        # copy of crew_job/data/cv.json
```

**Copy literally:**

- Agent roles, goals, backstories, `max_iter=3`, empty `tools=[]`
- Task descriptions / expected outputs / context wiring
- Interview preparer left commented out

**Minimal API adaptations:**

- Replace fixed `output/tailored_resume.md` with a temp path or in-memory task output
- Route `verbose` through logging instead of notebook stdout
- Keep `async_execution=True` on research/profile as in L7

**Out of scope for L7-only migration:** `cursor_llm.py`, LlamaIndex prepare, `helper.get_llm`, jupyter.

---

## Step 3 — Data bridge (API profile → crew inputs)

> Full file↔API mapping: see **[Input mapping: notebook files → slim chat profile](#input-mapping-notebook-files--slim-chat-profile)** above.

L7 kickoff expects:

```python
{
  "personal_writeup": "...",
  "job_posting_text": "...",
  "resume_text": "...",  # Markdown CV (filled_cv.md style), NOT ATS plain text
}
```

From slim (implement as adapter; no `input/` files):

1. Resolve `structured` from request body or `_resolve_structured` (DB profile after chat)
2. `cv = normalize_to_cv(structured)`  — this **is** `filled_cv.json`
3. `personal_writeup` = `extract_personal_writeup(cv)` (ported `cv_inputs`; summary/note or synthesize)
4. `resume_text` = `structured_to_resume_md(cv)` matching `input/filled_cv.md` / `render_cv_json_to_md`
5. `job_posting_text` = request `job_description`
6. After crew: `markdown_to_cv_json(..., contacts_source=structured)` — replaces `contacts_path="input/filled_cv.json"`
7. Stash `{personal_writeup, resume_text, job_posting_text, pipeline: "crew_l7"}` in `analysis` at analyze time

Template for MD→JSON:

- Ship `cv_template.json` (= `data/cv.json`), **or**
- Build empty shape from slim schema keys

**Schema watch-outs:**

- L7 JSON uses `selected_projects`; slim `cv.yml` often uses `projects` → always run `normalize_to_cv`
- Certifications may arrive as strings in L7 JSON vs richer objects in slim — coerce in normalize/bridge
- Do **not** reuse `structured_profile_to_plain_text` / `resume_plain_text_for_tailoring` as crew `resume_text` — wrong format for L7 prompts

---

## Step 4 — Replace orchestrator internals

File: `job_application/resume/safe_tailoring/orchestrator.py`

### `run_analyze` (lightweight; no crew)

Keep the two-step UX, drop `notebook_tailoring.parse_*`:

- Validate JD (≥40 chars) and resume (≥80 chars)
- Build `resume_text`, `personal_writeup`, YAML dump
- Optional JobBERT “before”
- Return `ask_user: []`, `phase: ready_to_generate`
- Put crew-ready snapshot into `analysis` (`pipeline: "crew_l7"`, texts, etc.)

### `run_generate` (L7 core)

1. Read inputs from `analysis` + `job_description`
2. Build crew (`build_job_application_crew()`)
3. `crew.kickoff(inputs=...)`
4. Read tailored Markdown (task output / temp file)
5. `markdown_to_cv_json(...)` with contacts backfill
6. `normalize_to_cv(tailored_json)`
7. Preview via existing `write_job_tailored_draft_preview`
8. Optional JobBERT “after”
9. Pack `token_usage` from `crew.usage_metrics` / ported `run_usage`
10. Return the **same response shape** the frontend expects

Cover letter: L7 has none. Return `""` or keep `/analyze/cover-letter` on the old path.

Run crew work in a thread executor (router already tends to do sync-off-event-loop) and raise HTTP client timeouts — a full kickoff takes minutes.

---

## Step 5 — Router / frontend

- Keep `safe_tailoring_router.py` request/response models unchanged
- `ask_user` / `selected_ids` already unused — leave as-is
- Optionally relabel `cover_letter_source` / pipeline tags from `llm_notebook` → `crew_l7`
- Increase timeouts in `OfferResumeSection.jsx` (`authFetchWithTimeout`)

---

## Step 6 — Retire legacy pipeline

After crew is stable:

1. Feature-flag default → `crew_l7`
2. Remove or quarantine `job_application/resume/notebook_tailoring/`
3. Replace `tests/test_notebook_tailoring.py` with crew-oriented tests
4. Update README (“Tailoring = L7 CrewAI”)
5. Decide fate of unused ATS `_core` path: delete, freeze, or restore as a separate mode — do not mix with L7

---

## Step 7 — Tests

1. **Unit (no LLM):** `cv_inputs` / `structured_to_resume_md` / contact backfill / `normalize_to_cv` project-key mapping
2. **Mocked kickoff:** stub `Crew.kickoff` with fixture Markdown → assert MD→JSON → API response shape
3. **Optional live integration:** one real OpenAI run vs notebook baseline
4. **Regression:** draft HTML preview, PDF endpoint, JobBERT fields still present

---

## Implementation checklist

1. [x] Python 3.11 venv (`env_l7`)
2. [x] Pin L7 deps in `requirements.txt`; verify `crewai` import + `pkg_resources`
3. [x] Port `cv_inputs`, `md_to_cv_json`, `template_extractor`, helpers (`contacts_source: dict`)
4. [x] Extract agents/tasks/crew from notebook into `crew.py` without prompt edits
5. [x] Adapter: chat/`structured` → `{resume_text` (MD), `personal_writeup`, `job_posting_text`}` — see Input mapping
6. [x] `structured_to_resume_md` (filled_cv.md parity); do not use ATS plain exporter for crew
7. [x] Rewrite `run_generate`; slim down `run_analyze` (stash crew inputs in `analysis`)
8. [x] Raise frontend / proxy timeouts
9. [ ] End-to-end UI test on one real JD (manual; needs `OPENAI_API_KEY`)
10. [x] Feature-flag default `crew_l7`; legacy via `TAILORING_PIPELINE=notebook` (notebook package kept for cover-letter)
11. [x] Update README

---

## Risks

| Risk | Mitigation |
|------|------------|
| Dependency conflicts (langchain 0.1 vs modern FastAPI/aisuite) | Hard pins; 3.11 venv; optional extras or subprocess isolation |
| Dual LLM stacks (Cursor/aisuite vs OpenAI for crew) | Exact L7 = OpenAI for crew + `md_to_cv_json` |
| Latency / cost (3 agents + second MD→JSON call) | Executor + long timeouts; show progress in UI |
| Schema drift (`selected_projects` vs `projects`) | Always `normalize_to_cv` |
| Weaker fact-safety than old `_core` validators | Keep prompts (“do not invent”); optional later validators |
| Filesystem coupling (`input/` / `output/`) | Temp dirs or in-memory MD strings |

---

## Bottom line

Keep FastAPI + profile DB + Harvard render/PDF as the outer shell. Replace only the inner tailor: **CrewAI researcher → profiler → strategist → Markdown → `markdown_to_cv_json` → `normalize_to_cv`**.

Treat LlamaIndex prepare and Cursor LLM helpers as out of scope for an L7-only migration.

Treat **Python 3.11 + `setuptools==80.10.2` + langchain 0.1 pins** as hard constraints.
