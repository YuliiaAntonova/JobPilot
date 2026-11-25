"""API structured profile → L7 crew kickoff inputs."""

from __future__ import annotations

from typing import Any

from job_application.resume.crew_tailoring.cv_inputs import (
    build_crew_inputs_from_cv,
    extract_personal_writeup,
)
from job_application.resume.crew_tailoring.resume_md import structured_to_resume_md
from job_application.resume.cv_schema import normalize_to_cv


def enrich_job_posting_text(
    job_description: str,
    *,
    company_name: str | None = None,
    job_title: str | None = None,
) -> str:
    """Prepend explicit company/role so the crew does not invent [Company Name]."""
    jd = (job_description or "").strip()
    company = str(company_name or "").strip()
    title = str(job_title or "").strip()
    if not company and not title:
        return jd
    header_lines: list[str] = []
    if company:
        header_lines.append(f"Company: {company}")
    if title:
        header_lines.append(f"Job title: {title}")
    header = "\n".join(header_lines)
    if not jd:
        return header
    # Avoid duplicating if the same header was already prepended
    if jd.startswith(header):
        return jd
    return f"{header}\n\n{jd}"


def build_crew_kickoff_inputs(
    *,
    structured: dict[str, Any],
    job_description: str,
    company_name: str | None = None,
    job_title: str | None = None,
) -> dict[str, Any]:
    """
    Map slim chat/DB structured CV + JD → L7 kickoff dict.

    Returns keys for crew.kickoff plus helpers for analysis snapshot / MD→JSON.
    """
    cv = normalize_to_cv(structured)
    bits = build_crew_inputs_from_cv(cv)
    resume_text = structured_to_resume_md(cv)
    personal_writeup = bits["personal_writeup"] or extract_personal_writeup(cv)
    company = str(company_name or "").strip()
    title = str(job_title or "").strip()
    jd = enrich_job_posting_text(
        job_description,
        company_name=company,
        job_title=title,
    )

    return {
        "personal_writeup": personal_writeup,
        "job_posting_text": jd,
        "resume_text": resume_text,
        "github_url": bits.get("github_url") or "",
        "company_name": company,
        "job_title": title,
        "cv": cv,
    }
