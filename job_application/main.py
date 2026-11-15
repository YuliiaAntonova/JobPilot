"""FastAPI entrypoint for resume + JD → filled application."""

from __future__ import annotations

import sys
import threading
from pathlib import Path

# Allow `uvicorn main:app` from inside job_application/ (repo root must be on path).
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

from sqlalchemy import inspect, text

from job_application.config import JOBS_DIR, MATCH_SCORE_WARMUP
from job_application.models.db import Base, engine
from job_application.routers import analyze, auth, jobs, profile, root

load_dotenv()

PACKAGE_DIR = Path(__file__).resolve().parent
SPA_STATIC_DIR = PACKAGE_DIR / "static" / "app"
UI_BUILD_ID = "20261116-jobpilot-brand-v12"


class NoCacheStaticFiles(StaticFiles):
    """SPA assets must not stick in browser cache after rebuild."""

    async def get_response(self, path: str, scope: Scope):
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
        return response

app = FastAPI(title="JobPilot")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _ensure_dirs():
    JOBS_DIR.mkdir(parents=True, exist_ok=True)


def _ensure_schema():
    """create_all не добавляет колонки в существующие таблицы."""
    insp = inspect(engine)
    if insp.has_table("application_jobs"):
        cols = {c["name"] for c in insp.get_columns("application_jobs")}
        if "user_id" not in cols:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE application_jobs "
                        "ADD COLUMN IF NOT EXISTS user_id VARCHAR(36) "
                        "REFERENCES users(id)"
                    )
                )


@app.on_event("startup")
def _startup():
    _ensure_dirs()
    Base.metadata.create_all(bind=engine)
    _ensure_schema()
    if MATCH_SCORE_WARMUP:
        from job_application.scoring.jobbert import warmup_jobbert_models

        threading.Thread(target=warmup_jobbert_models, name="jobbert-warmup", daemon=True).start()


if SPA_STATIC_DIR.is_dir():
    app.mount("/static/app", NoCacheStaticFiles(directory=SPA_STATIC_DIR), name="spa_static")

app.include_router(root.router)
app.include_router(auth.router)
app.include_router(profile.router)
app.include_router(analyze.router)
app.include_router(jobs.router)
