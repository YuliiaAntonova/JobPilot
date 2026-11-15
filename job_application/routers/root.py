from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from sqlalchemy import text

from job_application.models.db import engine

PACKAGE_DIR = Path(__file__).resolve().parent.parent
SPA_INDEX = PACKAGE_DIR / "static" / "app" / "index.html"
FAVICON = PACKAGE_DIR / "static" / "app" / "favicon.svg"

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def spa_index():
    if not SPA_INDEX.is_file():
        return HTMLResponse(
            content=(
                "<!DOCTYPE html><html><head><meta charset='utf-8'><title>Build UI</title></head>"
                "<body style='font-family:system-ui;padding:2rem;background:#0c0f14;color:#e8edf4'>"
                "<p>Build the React UI:</p>"
                "<pre style='background:#161d29;padding:1rem;border-radius:8px'>cd frontend\n"
                "npm install\nnpm run build</pre>"
                "<p>Then refresh this page.</p></body></html>"
            ),
            status_code=503,
        )
    return FileResponse(SPA_INDEX, headers={"Cache-Control": "no-cache, must-revalidate"})


@router.get("/favicon.ico", include_in_schema=False)
@router.get("/apple-touch-icon.png", include_in_schema=False)
@router.get("/apple-touch-icon-precomposed.png", include_in_schema=False)
async def site_icon():
    if FAVICON.is_file():
        return FileResponse(FAVICON, media_type="image/svg+xml")
    return HTMLResponse(status_code=404)


@router.get("/about")
def about_json(request: Request):
    return {
        "service": request.app.title,
        "build": "slim",
        "docs": "/docs",
        "health": "/health",
        "ui": "/",
        "auth": "POST /auth/register, POST /auth/login, GET /auth/me (Bearer JWT)",
        "profile": (
            "GET/PUT/DELETE /profile/me; POST /profile/from-chat; "
            "POST /profile/from-structured; GET /profile/me/cv.html"
        ),
        "analyze": (
            "POST /analyze/job-description (score); "
            "POST /analyze/resume-tailor/analyze|generate|pdf (safe YAML tailoring)"
        ),
        "jobs": (
            "POST /jobs/jd-draft; GET/PUT /jobs/{id}/offer-draft; "
            "GET /jobs/applications; PATCH /jobs/{id}/tracker"
        ),
        "cover_letter": "POST /analyze/cover-letter",
    }


@router.get("/health")
def health():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok", "database": "ok"}
    except Exception as e:
        return JSONResponse(
            {"status": "degraded", "database": str(e)},
            status_code=503,
        )
