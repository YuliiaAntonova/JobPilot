"""LLM helpers for notebook tailoring (uses shared chat_completion_tracked)."""

from __future__ import annotations

from typing import Any

from job_application.config import APP_LLM_MODEL
from job_application.shared.llm.client import chat_completion_tracked, complete_json_tracked

_SYSTEM = (
    "You are an expert resume and job-application assistant. "
    "Follow the user instructions precisely. "
    "Do not invent experience, skills, or metrics."
)

_USAGE_CALLS: list[dict[str, Any]] = []
_ACTIVE_MODEL: str | None = None


def configure(model: str | None) -> None:
    global _ACTIVE_MODEL
    _ACTIVE_MODEL = (model or "").strip() or None


def reset_usage() -> None:
    _USAGE_CALLS.clear()


def get_usage_calls() -> list[dict[str, Any]]:
    return list(_USAGE_CALLS)


def _model() -> str:
    return _ACTIVE_MODEL or APP_LLM_MODEL


def generate_text(prompt: str, *, call_label: str = "notebook_tailor") -> str:
    text, usage = chat_completion_tracked(
        _model(),
        _SYSTEM,
        prompt.strip(),
        call_label=call_label,
    )
    entry = dict(usage)
    entry["step"] = entry.get("step") or call_label
    _USAGE_CALLS.append(entry)
    return (text or "").strip()


def generate_json(prompt: str, *, call_label: str = "notebook_tailor_json") -> dict[str, Any]:
    data, packed = complete_json_tracked(
        _model(),
        _SYSTEM,
        prompt.strip(),
        max_retries=2,
        call_label=call_label,
    )
    for call in packed.get("calls") or []:
        _USAGE_CALLS.append(dict(call))
    if not isinstance(data, dict):
        raise ValueError("Expected a JSON object")
    return data
