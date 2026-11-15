# JobPilot

Job application assistant: resume chat, ATS/JobBERT scoring, and L7 CrewAI resume tailoring — FastAPI backend + React SPA.

## Features

- **Resume via chat** — `POST /profile/from-chat`, PostgreSQL `resume_profiles`
- **ATS / score** — `POST /analyze/job-description` (JobBERT)
- **Resume tailor (L7 CrewAI)** — Researcher → Profiler → Resume Strategist → Markdown → Harvard `cv.yml` / PDF  
  API: `/analyze/resume-tailor/analyze|generate|preview|pdf`  
  Legacy: `TAILORING_PIPELINE=notebook`
- **Job drafts**, JWT auth, portal UI
- **cv/** — workshop render helpers (`render.py`, HTML/PDF)

Optional migration notes: [`MIGRATE_RESUME_TAILORING_L7.md`](MIGRATE_RESUME_TAILORING_L7.md).

## Requirements

- **Python 3.11** (CrewAI 0.28)
- **Node.js 18+** (frontend build)
- **PostgreSQL**

## Setup

```bash
# 1) Python env
python3.11 -m venv env_l7
source env_l7/bin/activate
pip install -r requirements.txt
pip install -e .

# 2) Secrets (never commit .env)
cp .env.example .env
# Fill: DATABASE_URL, OPENAI_API_KEY, CURSOR_API_KEY / GROQ_API_KEY, JOB_APP_JWT_SECRET

# 3) Frontend
cd frontend && npm install && npm run build && cd ..

# 4) Run API
uvicorn job_application.main:app --reload --port 8000
```

Open: http://127.0.0.1:8000/

### Quick UI check

1. Sign in / open a job with a JD  
2. Ensure the cabinet has a structured resume (chat or PDF)  
3. **Analyze** → **Generate** (crew may take several minutes)  
4. Check preview / PDF  

Generate logs appear in the uvicorn terminal (`Working Agent` / `=== Usage ===`). Disable with `JOB_APP_CREW_VERBOSE=0`.

## Environment

Copy `.env.example` → `.env`. Important keys:

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | PostgreSQL SQLAlchemy URL |
| `JOB_APP_JWT_SECRET` | JWT signing secret (≥32 chars recommended) |
| `OPENAI_API_KEY` | CrewAI L7 tailor + md→json |
| `OPENAI_MODEL_NAME` | Default `gpt-4o-mini` |
| `TAILORING_PIPELINE` | `crew_l7` (default) or `notebook` |
| `CURSOR_API_KEY` | Chat / default `APP_LLM_MODEL` |
| `APP_LLM_MODEL` | e.g. `cursor:composer-2.5` or `groq:...` |
| `GROQ_API_KEY` | Optional Groq models |

`.env` is gitignored. Only `.env.example` is tracked.

## Tests

```bash
source env_l7/bin/activate
PYTHONPATH=. python -m pytest tests/ -q
```

## Notes

- Cover letter in L7 generate is empty; legacy `POST /analyze/cover-letter` uses the notebook path.
- HITL / wizard flows were removed in this slim build.
- Do not commit API keys, `.env`, personal CVs under `cv/yuliia_old/`, or local `data/` / `output/` files.
