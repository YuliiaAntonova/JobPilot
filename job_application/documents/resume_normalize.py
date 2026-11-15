"""Normalize structured JSON before PDF render."""

from __future__ import annotations


def _has_structured_experience_bullets(structured: dict) -> bool:
    """True when experience JSON already has bullets."""
    exp = structured.get("experience")
    if not isinstance(exp, list):
        return False
    for job in exp:
        if not isinstance(job, dict):
            continue
        for key in ("highlights", "responsibilities", "bullets"):
            val = job.get(key)
            if isinstance(val, list) and any(str(x).strip() for x in val):
                return True
        for key in ("summary", "description", "raw_description", "responsibilities_narrative"):
            if str(job.get(key) or "").strip():
                return True
    return False


def normalize_structured_for_render(structured: dict) -> dict:
    """All PDF export uses workshop cv.yml (cv/render.py + Chrome)."""
    from job_application.resume.cv_schema import is_cv_structured, normalize_to_cv

    if is_cv_structured(structured) or str(structured.get("chat_format") or "") == "cv_yml":
        return normalize_to_cv(structured)

    if _has_structured_experience_bullets(structured):
        return normalize_to_cv(structured)

    plain = str(structured.get("_resume_plain_text") or "").strip()
    if plain:
        from job_application.resume.profile_text import chat_answers_to_structured, structured_to_chat_answers

        seed = structured_to_chat_answers({**structured, "_resume_plain_text": plain})
        rebuilt = chat_answers_to_structured(seed)
        rebuilt["_resume_plain_text"] = plain
        return normalize_structured_for_render(rebuilt)

    return normalize_to_cv(structured)
