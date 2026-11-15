"""Safe YAML resume tailoring API (analyze → confirm → generate → PDF)."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from job_application.config import APP_LLM_MODEL
from job_application.models import User
from job_application.models.db import get_db
from job_application.resume.cv_pdf_export import render_structured_resume_pdf_bytes
from job_application.resume.cv_schema import normalize_to_cv
from job_application.resume.profile_service import structured_for_render_from_profile
from job_application.repositories import users as db_users
from job_application.resume.safe_tailoring import run_analyze, run_generate, run_preview_render
from job_application.routers.deps import get_current_user, get_optional_user

router = APIRouter(prefix="/analyze/resume-tailor", tags=["analyze"])


class ResumeTailorAnalyzeBody(BaseModel):
    job_description: str
    structured: dict[str, Any] | None = None
    resume_text: str | None = None
    model: str | None = None
    include_jobbert: bool = True


class ResumeTailorGenerateBody(BaseModel):
    job_description: str
    analysis: dict[str, Any]
    structured: dict[str, Any] | None = None
    resume_text: str | None = None
    selected_ids: list[str] = Field(default_factory=list)
    model: str | None = None
    include_jobbert: bool = True


class ResumeTailorPdfBody(BaseModel):
    tailored_structured: dict[str, Any]
    company_name: str | None = None


class ResumeTailorPreviewBody(BaseModel):
    tailored_structured: dict[str, Any] | None = None
    tailored_yaml: str | None = None


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


@router.post("/analyze")
async def resume_tailor_analyze(
    body: ResumeTailorAnalyzeBody,
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    """ATS analysis + ask_user proposals (human confirmation before generate)."""
    structured = _resolve_structured(db, user, body.structured)
    llm_model = body.model or APP_LLM_MODEL
    loop = asyncio.get_running_loop()
    try:
        result = await loop.run_in_executor(
            None,
            lambda: run_analyze(
                job_description=body.job_description,
                structured=structured,
                resume_text=body.resume_text,
                model=llm_model,
                include_jobbert=body.include_jobbert,
            ),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Safe tailoring error: {e}") from e
    return {"model": llm_model, **result}


@router.post("/generate")
async def resume_tailor_generate(
    body: ResumeTailorGenerateBody,
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    """Generate cv_tailored.yml after user confirms ask_user facts."""
    structured = _resolve_structured(db, user, body.structured)
    llm_model = body.model or APP_LLM_MODEL
    loop = asyncio.get_running_loop()
    try:
        result = await loop.run_in_executor(
            None,
            lambda: run_generate(
                job_description=body.job_description,
                analysis=body.analysis,
                structured=structured,
                resume_text=body.resume_text,
                selected_ids=body.selected_ids,
                model=llm_model,
                include_jobbert=body.include_jobbert,
            ),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Resume generation error: {e}") from e
    return {"model": llm_model, **result}


@router.post("/preview")
async def resume_tailor_preview(body: ResumeTailorPreviewBody):
    """Update cv_tailored_draft.html from edited structured JSON (does not touch cabinet profile)."""
    if not body.tailored_structured and not (body.tailored_yaml or "").strip():
        raise HTTPException(status_code=400, detail="tailored_structured or tailored_yaml is required")
    loop = asyncio.get_running_loop()
    try:
        result = await loop.run_in_executor(
            None,
            lambda: run_preview_render(
                tailored_structured=body.tailored_structured,
                tailored_yaml=body.tailored_yaml,
            ),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Preview error: {e}") from e
    return result


@router.post("/pdf")
def resume_tailor_pdf(body: ResumeTailorPdfBody, user: User = Depends(get_current_user)):
    """cv_tailored structured → cv/render.py → Chrome PDF."""
    _ = user
    structured = normalize_to_cv(body.tailored_structured)
    if not structured:
        raise HTTPException(status_code=400, detail="tailored_structured is empty")
    try:
        pdf_bytes = render_structured_resume_pdf_bytes(structured)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to build PDF: {e}") from e

    company = str(body.company_name or "").strip()
    if company:
        base = company
    else:
        basics = structured.get("basics") if isinstance(structured.get("basics"), dict) else {}
        base = str(basics.get("name") or "resume").strip()
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in base)[:60] or "resume"
    filename = f"{safe}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
