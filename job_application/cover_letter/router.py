"""Cover letter generation (Untitled.ipynb pipeline)."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from job_application.config import APP_LLM_MODEL
from job_application.models import User
from job_application.models.db import get_db
from job_application.repositories import users as db_users
from job_application.resume.notebook_tailoring.cv_bridge import resume_plain_text_for_tailoring
from job_application.resume.notebook_tailoring import pipeline as nb
from job_application.resume.profile_service import structured_for_render_from_profile
from job_application.routers.deps import get_optional_user
from job_application.shared.llm.tokens import pack_token_usage

router = APIRouter(prefix="/analyze", tags=["analyze"])


class CoverLetterBody(BaseModel):
    job_description: str
    structured: dict[str, Any] | None = None
    resume_text: str | None = None
    model: str | None = None


def _resolve_structured(
    db: Session,
    user: User | None,
    structured: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if isinstance(structured, dict) and structured:
        return structured
    if user is None:
        return None
    row = db_users.get_profile_for_user(db, user.id)
    if row is None:
        return None
    data = structured_for_render_from_profile(row)
    return data if isinstance(data, dict) and data else None


@router.post("/cover-letter")
async def generate_cover_letter(
    body: CoverLetterBody,
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    jd = (body.job_description or "").strip()
    if len(jd) < 40:
        raise HTTPException(status_code=400, detail="job_description is too short")

    structured = _resolve_structured(db, user, body.structured)
    llm_model = body.model or APP_LLM_MODEL

    try:
        plain = resume_plain_text_for_tailoring(structured=structured, resume_text=body.resume_text)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    loop = asyncio.get_running_loop()

    def _run() -> dict[str, Any]:
        nb.llm.configure(llm_model)
        nb.llm.reset_usage()
        resume_info = nb.parse_resume(plain)
        job_info = nb.parse_job_description(jd)
        from job_application.resume.notebook_tailoring.pipeline import flatten_skills

        job_skills = list(job_info.get("required_skills") or []) + list(
            job_info.get("preferred_skills") or []
        )
        resume_skills = flatten_skills(resume_info.get("skills") or [])
        score, matched, _missing = nb.get_skill_match_score(resume_skills, job_skills)
        letter = nb.generate_cover_letter(resume_info, job_info, score, matched)
        usage = pack_token_usage("cover_letter", llm_model, nb.llm.get_usage_calls())
        return {
            "cover_letter": letter,
            "match_score": score,
            "matched_skills": matched,
            "token_usage": usage,
        }

    try:
        payload = await loop.run_in_executor(None, _run)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Cover letter generation error: {e}") from e

    return {"model": llm_model, **payload}


@router.post("/cover-letter/analyze")
async def analyze_cover_letter(
    body: CoverLetterBody,
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    return await generate_cover_letter(body, user=user, db=db)


@router.post("/cover-letter/draft-from-meta")
async def draft_cover_letter_from_meta(
    body: CoverLetterBody,
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    return await generate_cover_letter(body, user=user, db=db)


@router.post("/cover-letter/template")
async def generate_cover_letter_template(
    body: CoverLetterBody,
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    return await generate_cover_letter(body, user=user, db=db)


@router.post("/cover-letter/pdf")
async def render_cover_letter_pdf():
    raise HTTPException(status_code=501, detail="Cover letter PDF export is not implemented in slim build.")


@router.post("/cover-letter/revise-paragraph")
async def revise_cover_letter_paragraph():
    raise HTTPException(status_code=501, detail="Cover letter revision is not implemented in slim build.")


@router.post("/cover-letter/recruiter-feedback")
async def cover_letter_recruiter_feedback():
    raise HTTPException(status_code=501, detail="Recruiter feedback is not implemented in slim build.")
