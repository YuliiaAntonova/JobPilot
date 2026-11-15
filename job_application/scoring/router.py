"""Scoring endpoints: JD + resume → JobBERT / hybrid match score."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from job_application.models import User
from job_application.models.db import get_db
from job_application.shared.forms import upload_bytes_to_jd_text
from job_application.routers.deps import get_optional_user
from job_application.scoring import service as match_score
from job_application.resume.profile_service import resolve_resume_text_for_jobbert_scoring

router = APIRouter(prefix="/analyze", tags=["analyze"])


@router.post("/job-description")
async def analyze_job_description(
    job_description: str | None = Form(None),
    resume_text: str | None = Form(None),
    jd_file: UploadFile | None = File(None),
    model: str | None = Form(None),
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    """
    Текст вакансии + резюме → JobBERT skill match (Untitled1_skillmatch_fixed.ipynb).
    LLM здесь не используется.
    """
    chunks: list[str] = []
    if job_description and job_description.strip():
        chunks.append(job_description.strip())

    if jd_file is not None:
        raw = await jd_file.read()
        if raw:
            try:
                extracted = upload_bytes_to_jd_text(jd_file.filename, raw).strip()
                if extracted:
                    chunks.append(extracted)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e)) from e
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Failed to read file: {e}") from e

    combined = "\n\n".join(chunks).strip()
    if len(combined) < 40:
        raise HTTPException(
            status_code=400,
            detail=(
                "Job description text is required (job_description field) and/or jd_file "
                "(PDF/HTML/TXT) with sufficient text."
            ),
        )

    resume_for_score, resume_structured, resume_text_source = resolve_resume_text_for_jobbert_scoring(
        db,
        user,
        resume_text,
    )
    loop = asyncio.get_running_loop()

    scoring_method = None
    match_details = None
    try:
        if resume_for_score:
            match_details = await loop.run_in_executor(
                None,
                lambda: match_score.compute_hybrid_match_score(
                    resume_for_score,
                    combined,
                    structured=resume_structured,
                    include_ats=True,
                ),
            )
            ats = match_details.get("ats") or {}
            analysis = {
                "match_score": match_details["match_score"],
                "match_rank_label": match_details["match_rank_label"],
                "comparison_summary": match_details["comparison_summary"],
                "scoring_skipped": False,
                "matched_skills": match_details.get("matched_skills") or [],
                "unmatched_skills": match_details.get("unmatched_skills") or [],
                "skills_source": match_details.get("skills_source"),
                "skills_available": match_details.get("skills_available", False),
                "scoring_method": match_details.get("scoring_method"),
                "resume_text_source": resume_text_source,
                "ats_suggestions": ats.get("suggestions") or [],
                "ats_confident_suggestions": ats.get("confident_suggestions") or [],
                "ats_phrase_suggestions": ats.get("phrase_suggestions") or [],
                "ats_min_phrase_sim": ats.get("min_phrase_sim"),
                "ats_phrase_discovery_threshold": ats.get("phrase_discovery_threshold"),
                "ats_jd_phrase_count": ats.get("jd_phrase_count", 0),
                "ats_resume_phrase_count": ats.get("resume_phrase_count", 0),
                "required_entities": match_details.get("required_skills") or [],
                "resume_entities": match_details.get("resume_skills") or [],
                "resume_entities_source": match_details.get("resume_entities_source"),
                "ats_preview_text": (match_details.get("ats") or {}).get("preview_text"),
                "ats_phrase_resume_text": (match_details.get("ats") or {}).get("phrase_resume_text"),
            }
            scoring_method = match_details["scoring_method"]
        else:
            analysis = {
                "match_score": 0,
                "match_rank_label": "Resume not provided",
                "comparison_summary": (
                    "Score not calculated: use resume from cabinet (checkbox above) "
                    "or paste text at least 80 characters long."
                ),
                "scoring_skipped": True,
                "matched_skills": [],
                "unmatched_skills": [],
                "ats_suggestions": [],
                "ats_jd_phrase_count": 0,
                "ats_resume_phrase_count": 0,
            }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Analyze error: {e}") from e

    return {
        "job_description_text": combined,
        "scoring_method": scoring_method,
        "match_details": match_details,
        "analysis": analysis,
    }
