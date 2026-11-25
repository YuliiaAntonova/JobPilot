# JobPilot

Resume chat, JobBERT score, CrewAI tailor — FastAPI + React SPA.

## Docker

### 1. First time only

```bash
cp .env.example .env
# fill: JOB_APP_JWT_SECRET, OPENAI_API_KEY, LLAMA_CLOUD_API_KEY
```

Defaults: `APP_LLM_MODEL=openai:gpt-4o-mini`, `OPENAI_MODEL_NAME=gpt-4o-mini`, `EMBED_BACKEND=openai`.

Then build once (slow, ~minutes, image ~4GB: torch + Chromium + npm):

```bash
docker compose up --build -d
docker compose logs -f api
```

Open http://127.0.0.1:8000/ → **Register**.

### 2. Every next start (no build)

```bash
docker compose up -d
docker compose logs -f api
```

| Command | When |
|---------|------|
| `docker compose up -d` | Usual start. Fast. Uses existing image. |
| `docker compose logs -f api` | Watch uvicorn / CrewAI / LLM logs. |
| `docker compose down` | Stop API (`app_data` volume keeps). |
| `docker compose ps` | Status. |

### 3. When you need `--build`

`--build` is **slow**. Use only if something that goes **into the image** changed:

| Changed | Need `--build`? |
|---------|-----------------|
| Nothing / only `.env` | **No** — `docker compose up -d --force-recreate api` |
| `job_application/`, `cv/`, `alembic/`, `frontend/src/` | **Yes** — code is copied into the image |
| `requirements.txt`, `Dockerfile`, `frontend/package-lock.json` | **Yes** — and will reinstall heavy deps |

```bash
docker compose up --build -d
docker compose logs -f api
```

### Ports & data

| What | Where |
|------|--------|
| App | http://127.0.0.1:8000/ |
| Postgres | your Mac DB on `localhost:5432` (Compose has no Postgres). Set `DOCKER_DATABASE_URL` in `.env` (default: `postgres` / `postgres` / `world` via `host.docker.internal`). |
| Volumes | `app_data` — wipe with `docker compose down -v` |

## Optional: local without Docker

```bash
python3.11 -m venv env_l7 && source env_l7/bin/activate
pip install -r requirements.txt && pip install -e .
cp .env.example .env   # set DATABASE_URL + keys
cd frontend && npm ci && npm run build && cd ..
uvicorn job_application.main:app --reload --port 8000
```

## Tests

```bash
source env_l7/bin/activate
PYTHONPATH=. python -m pytest tests/ -q
```
