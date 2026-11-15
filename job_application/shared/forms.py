"""Shared form/API helpers used by analyze routes."""

from __future__ import annotations

import json

from pydantic import BaseModel, Field

from job_application.shared.parsing import jd_bytes_to_plain_text, resume_bytes_to_plain_text

upload_bytes_to_jd_text = jd_bytes_to_plain_text
upload_bytes_to_resume_plain = resume_bytes_to_plain_text

_upload_bytes_to_jd_text = jd_bytes_to_plain_text
_upload_bytes_to_resume_plain = resume_bytes_to_plain_text


def split_skills(raw: str | None) -> list[str]:
    if not raw or not raw.strip():
        return []
    if raw.strip().startswith("["):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(x).strip() for x in parsed if str(x).strip()]
        except json.JSONDecodeError:
            pass
    return [p.strip() for p in raw.split(",") if p.strip()]


def parse_ats_suggestions(raw: str | None) -> list[dict[str, str]]:
    if not raw or not raw.strip():
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    out: list[dict[str, str]] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        rp = str(item.get("resume_phrase") or "").strip()
        jp = str(item.get("jd_phrase") or "").strip()
        if rp and jp:
            out.append({"resume_phrase": rp, "jd_phrase": jp})
    return out


class ChatAnswersBody(BaseModel):
    """Ответы чат-мастера создания резюме (Sprint 2)."""

    answers: dict[str, str] = Field(default_factory=dict)


_split_skills = split_skills
_parse_ats_suggestions = parse_ats_suggestions
