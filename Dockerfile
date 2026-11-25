# JobPilot: React SPA → job_application/static/app, then FastAPI + Chromium PDF.

# --- Frontend (cached unless package-lock / frontend sources change) ---
FROM node:20-bookworm-slim AS frontend
WORKDIR /src
COPY frontend/package.json frontend/package-lock.json ./frontend/
RUN cd frontend && npm ci
COPY frontend ./frontend
RUN mkdir -p job_application/static/app \
  && cd frontend && npm run build

# --- API runtime ---
FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    JOB_APP_DATA_ROOT=/app/data \
    CV_PREVIEW_DIR=/app/data/output/preview \
    CV_CHROME_BIN=/usr/bin/chromium \
    MATCH_SCORE_WARMUP=0

RUN apt-get update && apt-get install -y --no-install-recommends \
      chromium \
      fonts-liberation \
      fonts-dejavu-core \
      ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /app/data/output/preview /app/data/output/tailored \
      /app/data/storage/jobs /app/data/storage/rag /app/data/input

WORKDIR /app

# Install Python deps BEFORE copying app code so code edits reuse the torch layer.
COPY requirements.txt pyproject.toml ./
RUN pip install -r requirements.txt

COPY alembic.ini ./
COPY alembic ./alembic
COPY job_application ./job_application
COPY cv ./cv
COPY --from=frontend /src/job_application/static/app ./job_application/static/app

RUN pip install -e . \
  && test -f job_application/static/app/index.html

EXPOSE 8000

CMD ["uvicorn", "job_application.main:app", "--host", "0.0.0.0", "--port", "8000"]
