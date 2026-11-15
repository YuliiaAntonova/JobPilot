"""Cursor SDK backend for text/JSON LLM calls (CURSOR_API_KEY)."""

from __future__ import annotations

import os
import time
from collections.abc import Sequence
from typing import Any

from cursor_sdk import Agent, AgentOptions, CursorAgentError, LocalAgentOptions, RateLimitError

from job_application.config import CURSOR_API_KEY, CURSOR_MODEL, REPO_ROOT


def is_cursor_model(model: str | None) -> bool:
    text = (model or "").strip().lower()
    return text.startswith("cursor:") or text == "cursor"


def resolve_cursor_model_id(model: str | None) -> str:
    text = (model or "").strip()
    if text.lower().startswith("cursor:"):
        model_id = text.split(":", 1)[1].strip()
        if model_id:
            return model_id
    return CURSOR_MODEL


def _build_prompt(system: str, user: str) -> str:
    system = (system or "").strip()
    user = (user or "").strip()
    if system and user:
        return f"System instructions:\n{system}\n\nUser request:\n{user}"
    return user or system


def _format_cursor_run_error(result: Any) -> str:
    run_id = getattr(result, "id", None) or "?"
    status = getattr(result, "status", None) or "error"
    snippet = (getattr(result, "result", None) or "").strip()
    if len(snippet) > 280:
        snippet = snippet[:280] + "…"

    lines = [
        f"Cursor Agent finished with an error (status={status}).",
    ]
    if snippet:
        lines.append(f"Response: {snippet}")
    else:
        lines.append(f"Run ID: {run_id}")
    lines.append(
        "Check CURSOR_API_KEY and model (APP_LLM_MODEL). "
        "For resume parsing you can set CV_YAML_LLM_FALLBACK=groq:… or openai:… in .env."
    )
    return "\n".join(lines)


def _usage_from_run(result: Any) -> dict[str, int]:
    usage = getattr(result, "usage", None)
    if usage is None:
        return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
    output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
    total_tokens = int(getattr(usage, "total_tokens", 0) or 0) or (input_tokens + output_tokens)
    return {
        "prompt_tokens": input_tokens,
        "completion_tokens": output_tokens,
        "total_tokens": total_tokens,
    }


def cursor_chat_completion_tracked(
    model: str | None,
    system: str,
    user: str,
    *,
    call_label: str = "llm",
    tools: Sequence[str] | None = None,
) -> tuple[str, dict[str, int]]:
    if not CURSOR_API_KEY:
        raise RuntimeError(
            "CURSOR_API_KEY is not set. Add it to .env (Cursor Dashboard → Integrations)."
        )

    model_id = resolve_cursor_model_id(model)
    prompt = _build_prompt(system, user)
    retries = max(1, int(os.getenv("JOB_APP_LLM_RATELIMIT_RETRIES", "8")))
    last_err: Exception | None = None

    agent_opts_kwargs: dict[str, Any] = {
        "api_key": CURSOR_API_KEY,
        "model": model_id,
        "local": LocalAgentOptions(cwd=str(REPO_ROOT)),
    }
    if tools is not None:
        agent_opts_kwargs["tools"] = list(tools)

    for attempt in range(retries):
        try:
            result = Agent.prompt(
                prompt,
                AgentOptions(**agent_opts_kwargs),
            )
            status = getattr(result, "status", "")
            if status in ("error", "cancelled", "expired"):
                raise RuntimeError(_format_cursor_run_error(result))
            content = (getattr(result, "result", None) or "").strip()
            if not content and status == "finished":
                raise RuntimeError(
                    _format_cursor_run_error(result)
                    if getattr(result, "id", None)
                    else "Cursor Agent returned an empty response."
                )
            usage = _usage_from_run(result)
            usage["step"] = call_label if attempt == 0 else f"{call_label}_retry{attempt + 1}"
            return content, usage
        except RateLimitError as e:
            last_err = e
            if attempt >= retries - 1:
                break
            wait = 4.0 * (attempt + 1)
            retry_after = getattr(e, "retry_after", None)
            if retry_after:
                try:
                    wait = min(120.0, float(retry_after))
                except (TypeError, ValueError):
                    pass
            time.sleep(wait)
        except CursorAgentError as e:
            if getattr(e, "is_retryable", False) and attempt < retries - 1:
                last_err = e
                time.sleep(min(120.0, 4.0 * (attempt + 1)))
                continue
            raise RuntimeError(f"Cursor API error: {e}") from e

    assert last_err is not None
    raise RuntimeError(f"Cursor API rate limit: {last_err}") from last_err
