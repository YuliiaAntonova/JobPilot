"""Lightweight usage counters for one RAG prepare run."""

from __future__ import annotations

from typing import Any

_LLAMA_PARSE: list[dict[str, Any]] = []
_CALLS: list[dict[str, Any]] = []


def reset_run_usage() -> None:
    _LLAMA_PARSE.clear()
    _CALLS.clear()


def record_llama_parse_job(
    *,
    job_id: str,
    file_name: str,
    tier: str | None,
    status: str,
    pages: int,
    credits: float | None,
) -> None:
    _LLAMA_PARSE.append(
        {
            "job_id": job_id,
            "file": file_name,
            "tier": tier,
            "status": status,
            "pages": pages,
            "credits": credits,
            "cached": False,
        }
    )


def record_llama_parse_cached(*, file_name: str, index_dir: str) -> None:
    _LLAMA_PARSE.append(
        {
            "file": file_name,
            "cached": True,
            "index_dir": index_dir,
            "pages": None,
            "credits": 0.0,
        }
    )


def record_llm_completion(
    prompt: str,
    response: str,
    *,
    backend: str = "app",
    label: str | None = None,
    raw_response: Any = None,
) -> None:
    del raw_response
    _CALLS.append(
        {
            "label": label,
            "backend": backend,
            "prompt_chars": len(prompt or ""),
            "response_chars": len(response or ""),
        }
    )


def get_run_usage_summary() -> dict[str, Any]:
    return {
        "llama_parse": list(_LLAMA_PARSE),
        "llm_calls": list(_CALLS),
    }
