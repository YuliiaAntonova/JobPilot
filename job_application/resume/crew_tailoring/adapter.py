"""API structured profile → L7 crew kickoff inputs."""

from __future__ import annotations

from typing import Any

from job_application.resume.crew_tailoring.cv_inputs import (
    build_crew_inputs_from_cv,
    extract_personal_writeup,
)
from job_application.resume.crew_tailoring.resume_md import structured_to_resume_md
from job_application.resume.cv_schema import normalize_to_cv


def build_crew_kickoff_inputs(
    *,
    structured: dict[str, Any],
    job_description: str,
) -> dict[str, Any]:
    """
    Map slim chat/DB structured CV + JD → L7 kickoff dict.

    Returns keys for crew.kickoff plus helpers for analysis snapshot / MD→JSON.
    """
    cv = normalize_to_cv(structured)
    bits = build_crew_inputs_from_cv(cv)
    resume_text = structured_to_resume_md(cv)
    personal_writeup = bits["personal_writeup"] or extract_personal_writeup(cv)
    jd = (job_description or "").strip()

    return {
        "personal_writeup": personal_writeup,
        "job_posting_text": jd,
        "resume_text": resume_text,
        "github_url": bits.get("github_url") or "",
        "cv": cv,
    }
