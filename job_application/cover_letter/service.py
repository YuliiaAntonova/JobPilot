"""Cover letter use-case — no dependency on notebook_tailoring."""

from __future__ import annotations

from typing import Any

from job_application.cover_letter import extract as cl
from job_application.infra.llm.usage import pack_and_log_token_usage
from job_application.resume.profile_text import structured_profile_to_plain_text


def resume_plain_text_for_letter(
    *,
    structured: dict[str, Any] | None,
    resume_text: str | None,
) -> str:
    if isinstance(structured, dict) and structured:
        return structured_profile_to_plain_text(structured).strip()
    text = (resume_text or "").strip()
    if not text:
        raise ValueError("structured profile or resume_text is required.")
    return text


def run_cover_letter(
    *,
    job_description: str,
    structured: dict[str, Any] | None = None,
    resume_text: str | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    jd = (job_description or "").strip()
    if len(jd) < 40:
        raise ValueError("job_description is too short")

    plain = resume_plain_text_for_letter(structured=structured, resume_text=resume_text)
    llm_model = (model or "").strip() or None

    cl.configure(llm_model)
    cl.reset_usage()
    resume_info = cl.parse_resume(plain)
    job_info = cl.parse_job_description(jd)
    job_skills = list(job_info.get("required_skills") or []) + list(
        job_info.get("preferred_skills") or []
    )
    resume_skills = cl.flatten_skills(resume_info.get("skills") or [])
    score, matched, _missing = cl.get_skill_match_score(resume_skills, job_skills)
    letter = cl.generate_cover_letter(resume_info, job_info, score, matched)
    usage = pack_and_log_token_usage(
        "cover_letter",
        llm_model or cl._model(),
        cl.get_usage_calls(),
    )
    return {
        "cover_letter": letter,
        "match_score": score,
        "matched_skills": matched,
        "token_usage": usage,
        "model": llm_model or cl._model(),
    }
