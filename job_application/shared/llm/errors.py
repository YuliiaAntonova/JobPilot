"""User-facing LLM error messages."""

from __future__ import annotations


def llm_error_message(exc: BaseException) -> str:
    """Single-line message for HTTP 502 (avoid duplicate 'LLM error' prefixes)."""
    text = str(exc).strip()
    for prefix in ("LLM error: ", "Ошибка LLM: ", "RuntimeError: "):
        if text.startswith(prefix):
            text = text[len(prefix) :].strip()
    return text or exc.__class__.__name__
