from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Form, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from job_application.services import get_job_service
from job_application.models.schemas import OfferDraftPatch
from job_application.config import APP_LLM_MODEL
from job_application.models.db import get_db
from job_application.routers.deps import get_current_user, get_job_with_access
from job_application.models.exceptions import ApplicationError
from job_application.models import Job, User

router = APIRouter(prefix="/jobs", tags=["jobs"])


class OfferDraftSaveBody(BaseModel):
    jd_text: str | None = None
    analysis: dict | None = None
    cover_letter_text: str | None = None
    tailored_resume_text: str | None = None
    resume_paste: str | None = None
    model: str | None = None


class TrackerPatchBody(BaseModel):
    company_name: str | None = None
    job_title: str | None = None
    pipeline_status: str | None = None
    applied_at: str | None = None
    closed: bool | None = None


def _http_error(exc: ApplicationError, *, status: int = 400) -> HTTPException:
    return HTTPException(status_code=status, detail=str(exc))


@router.post("/jd-draft")
async def save_jd_draft(
    job_description: str = Form(...),
    analysis_json: str | None = Form(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    jd_clean = job_description.strip()
    if len(jd_clean) < 40:
        raise HTTPException(status_code=400, detail="job_description is too short (minimum 40 characters).")

    analysis = None
    if analysis_json and analysis_json.strip():
        try:
            parsed = json.loads(analysis_json)
            if isinstance(parsed, dict):
                analysis = parsed
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=400, detail=f"analysis_json: {e}") from e

    return get_job_service(db).save_jd_draft(
        user.id,
        jd_text=jd_clean,
        analysis=analysis,
        llm_model=APP_LLM_MODEL,
    )


@router.get("/offer-draft/latest")
def get_latest_offer_draft(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return get_job_service(db).get_latest_offer_draft(user.id)


@router.get("/applications")
def list_applications(
    include_closed: bool = Query(False),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return get_job_service(db).list_applications(
        user.id,
        include_closed=include_closed,
        limit=limit,
        offset=offset,
    )


@router.get("/{job_id}/offer-draft")
def get_offer_draft(row: Job = Depends(get_job_with_access), db: Session = Depends(get_db)):
    return get_job_service(db).get_offer_draft(row.id)


@router.put("/{job_id}/offer-draft")
def save_offer_draft(
    body: OfferDraftSaveBody,
    row: Job = Depends(get_job_with_access),
    db: Session = Depends(get_db),
):
    try:
        return get_job_service(db).save_offer_draft(
            row.id,
            OfferDraftPatch(
                jd_text=body.jd_text,
                analysis=body.analysis,
                cover_letter_text=body.cover_letter_text,
                tailored_resume_text=body.tailored_resume_text,
                resume_paste=body.resume_paste,
                model=body.model,
            ),
        )
    except ApplicationError as e:
        raise _http_error(e) from e


@router.patch("/{job_id}/tracker")
def patch_tracker(
    body: TrackerPatchBody,
    row: Job = Depends(get_job_with_access),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    del user  # auth required; ownership checked in get_job_with_access
    patch = body.model_dump(exclude_unset=True)
    try:
        return get_job_service(db).patch_tracker(row.id, patch)
    except ApplicationError as e:
        raise _http_error(e) from e
