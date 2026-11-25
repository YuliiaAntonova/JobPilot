"""Adapter: uploaded resume → plain text + structured CV + chat seed (RAG prepare)."""

from __future__ import annotations

from typing import Any

from job_application.config import APP_LLM_MODEL
from job_application.resume.cv_schema import CV_CHAT_FORMAT, cv_to_chat_answers, normalize_to_cv
from job_application.resume.rag_prepare import fill_cv_from_pdf_bytes, fill_cv_from_text
from job_application.resume.rag_prepare.normalize import l7_json_to_slim_cv


def _cv_to_structured(cv: dict[str, Any], *, plain_text: str) -> dict[str, Any]:
    slim = l7_json_to_slim_cv(cv)
    structured = normalize_to_cv({**slim, "_resume_plain_text": plain_text})
    structured["resume_template"] = "harvard"
    structured["chat_format"] = CV_CHAT_FORMAT
    structured["_resume_plain_text"] = plain_text
    return structured


def _require_identity(seed: dict[str, str]) -> None:
    if not seed.get("name") and not seed.get("email"):
        raise ValueError(
            "Could not extract name or email from the resume. "
            "Try another file or complete the chat manually."
        )


class DefaultResumePdfParser:
    """LlamaCloud Parse + section RAG fill (crew_job prepare notebook)."""

    async def parse_bytes(
        self, filename: str | None, raw: bytes, *, model: str | None = None
    ) -> tuple[str, dict[str, Any], dict[str, str]]:
        filled, plain, _usage = await fill_cv_from_pdf_bytes(
            filename, raw, llm_model=model or APP_LLM_MODEL
        )
        structured = _cv_to_structured(filled, plain_text=plain)
        seed = cv_to_chat_answers(structured)
        _require_identity(seed)
        return plain, structured, seed

    async def parse_text(
        self, text: str, *, model: str | None = None
    ) -> tuple[str, dict[str, Any], dict[str, str]]:
        filled, plain, _usage = await fill_cv_from_text(
            text, llm_model=model or APP_LLM_MODEL
        )
        structured = _cv_to_structured(filled, plain_text=plain)
        seed = cv_to_chat_answers(structured)
        _require_identity(seed)
        return plain, structured, seed


async def parse_resume_pdf(
    filename: str | None, raw: bytes, *, model: str | None = None
) -> tuple[str, dict[str, Any], dict[str, str]]:
    return await DefaultResumePdfParser().parse_bytes(filename, raw, model=model)
