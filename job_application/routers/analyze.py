"""Aggregate /analyze/* routers (scoring, safe tailoring, cover letter stub)."""

from __future__ import annotations

from fastapi import APIRouter

from job_application.config import APP_LLM_MODEL
from job_application.cover_letter.router import router as cover_letter_router
from job_application.resume.safe_tailoring_router import router as safe_tailoring_router
from job_application.scoring.router import router as scoring_router
from job_application.shared.forms import (
    ChatAnswersBody,
    _parse_ats_suggestions,
    _split_skills,
    _upload_bytes_to_jd_text,
    _upload_bytes_to_resume_plain,
    parse_ats_suggestions,
    split_skills,
    upload_bytes_to_jd_text,
    upload_bytes_to_resume_plain,
)

router = APIRouter(tags=["analyze"])
router.include_router(scoring_router)
router.include_router(cover_letter_router)
router.include_router(safe_tailoring_router)


@router.get("/analyze/llm-config")
def llm_config():
    """Default LLM model and Cursor availability for UI."""
    from job_application.config import CURSOR_API_KEY

    return {
        "default_model": APP_LLM_MODEL,
        "cursor_configured": bool(CURSOR_API_KEY),
    }


__all__ = [
    "ChatAnswersBody",
    "router",
    "_parse_ats_suggestions",
    "_split_skills",
    "_upload_bytes_to_jd_text",
    "_upload_bytes_to_resume_plain",
    "parse_ats_suggestions",
    "split_skills",
    "upload_bytes_to_jd_text",
    "upload_bytes_to_resume_plain",
]
