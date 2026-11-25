"""Canonical LLM token accounting + server-side logging."""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger("job_application.llm_tokens")


def token_logging_enabled() -> bool:
    return os.getenv("JOB_APP_LLM_TOKEN_LOG", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def empty_token_usage() -> dict[str, int]:
    return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}


def extract_token_usage(response: Any) -> dict[str, int]:
    usage = getattr(response, "usage", None)
    if usage is None and isinstance(response, dict):
        usage = response.get("usage")
    if usage is None:
        return empty_token_usage()
    if isinstance(usage, dict):
        return {
            "prompt_tokens": int(usage.get("prompt_tokens") or 0),
            "completion_tokens": int(usage.get("completion_tokens") or 0),
            "total_tokens": int(usage.get("total_tokens") or 0),
        }
    return {
        "prompt_tokens": int(getattr(usage, "prompt_tokens", 0) or 0),
        "completion_tokens": int(getattr(usage, "completion_tokens", 0) or 0),
        "total_tokens": int(getattr(usage, "total_tokens", 0) or 0),
    }


def add_token_usage(a: dict[str, int], b: dict[str, int]) -> dict[str, int]:
    return {
        "prompt_tokens": int(a.get("prompt_tokens", 0)) + int(b.get("prompt_tokens", 0)),
        "completion_tokens": int(a.get("completion_tokens", 0)) + int(b.get("completion_tokens", 0)),
        "total_tokens": int(a.get("total_tokens", 0)) + int(b.get("total_tokens", 0)),
    }


def pack_token_usage(operation: str, model: str, calls: list[dict[str, Any]]) -> dict[str, Any]:
    total = empty_token_usage()
    for call in calls:
        total = add_token_usage(
            total,
            {
                "prompt_tokens": int(call.get("prompt_tokens") or 0),
                "completion_tokens": int(call.get("completion_tokens") or 0),
                "total_tokens": int(call.get("total_tokens") or 0),
            },
        )
    return {
        "operation": operation,
        "model": model,
        "calls": calls,
        "total": total,
    }


def log_llm_token_usage(operation: str, model: str, token_usage: dict[str, Any]) -> None:
    if not token_logging_enabled():
        return
    total = token_usage.get("total") or empty_token_usage()
    lines = [
        f"[LLM tokens] {operation} | model={model}",
        f"  TOTAL: prompt={total.get('prompt_tokens', 0)} "
        f"completion={total.get('completion_tokens', 0)} "
        f"sum={total.get('total_tokens', 0)}",
    ]
    for call in token_usage.get("calls") or []:
        step = call.get("step") or "call"
        lines.append(
            f"  - {step}: prompt={call.get('prompt_tokens', 0)} "
            f"completion={call.get('completion_tokens', 0)} "
            f"total={call.get('total_tokens', 0)}"
        )
    message = "\n".join(lines)
    logger.info(message)
    print(message, flush=True)


def pack_and_log_token_usage(
    operation: str,
    model: str,
    calls: list[dict[str, Any]],
) -> dict[str, Any]:
    """Pack call rows and emit server log when JOB_APP_LLM_TOKEN_LOG is on."""
    packed = pack_token_usage(operation, model, calls)
    log_llm_token_usage(operation, model, packed)
    return packed
