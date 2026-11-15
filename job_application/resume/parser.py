"""Adapter: uploaded resume bytes → plain text + cv.yml structured + chat seed."""

from __future__ import annotations

from typing import Any

from job_application.config import APP_LLM_MODEL
from job_application.resume.cv_schema import CV_CHAT_FORMAT, cv_to_chat_answers, normalize_to_cv
from job_application.resume.cv_yml_io import resume_bytes_to_cv, resume_text_to_cv


def _cv_to_structured(cv: dict[str, Any], *, plain_text: str) -> dict[str, Any]:
    structured = normalize_to_cv({**cv, "_resume_plain_text": plain_text})
    structured["resume_template"] = "harvard"
    structured["chat_format"] = CV_CHAT_FORMAT
    structured["_resume_plain_text"] = plain_text
    return structured


class DefaultResumePdfParser:
    def parse_bytes(self, filename: str | None, raw: bytes) -> tuple[str, dict[str, Any], dict[str, str]]:
        text, cv = resume_bytes_to_cv(filename, raw, model=APP_LLM_MODEL)
        structured = _cv_to_structured(cv, plain_text=text)
        seed = cv_to_chat_answers(structured)
        if not seed.get("name") and not seed.get("email"):
            raise ValueError(
                "Could not extract name or email from the resume. "
                "Try another file or complete the chat manually."
            )
        return text, structured, seed

    def parse_text(self, text: str) -> tuple[str, dict[str, Any], dict[str, str]]:
        plain = (text or "").strip()
        cv = resume_text_to_cv(plain, model=APP_LLM_MODEL)
        structured = _cv_to_structured(cv, plain_text=plain)
        seed = cv_to_chat_answers(structured)
        if not seed.get("name") and not seed.get("email"):
            raise ValueError(
                "Could not extract name or email from the resume. "
                "Try another file or complete the chat manually."
            )
        return plain, structured, seed


def parse_resume_pdf(filename: str | None, raw: bytes) -> tuple[str, dict[str, Any], dict[str, str]]:
    return DefaultResumePdfParser().parse_bytes(filename, raw)
