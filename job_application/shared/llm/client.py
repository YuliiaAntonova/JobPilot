"""OpenAI / aisuite client helpers."""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any

import aisuite as ai
from aisuite.provider import LLMError

from job_application.config import APP_LLM_MODEL
from job_application.shared.llm.cursor_client import cursor_chat_completion_tracked, is_cursor_model
from job_application.shared.llm.tokens import (
    extract_token_usage,
    log_llm_token_usage,
    pack_token_usage,
)

_RATE_LIMIT_PAUSE_RE = re.compile(
    r"try\s+again\s+in\s+(?P<secs>\d+(?:\.\d+)?)\s*s\.?",
    re.IGNORECASE,
)

_client = None


def get_client():
    global _client
    if _client is None:
        _client = ai.Client()
    return _client


def strip_json_fence(text: str) -> str:
    if not text:
        return ""
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
    return t.strip()


def chat_completion_tracked(
    model: str | None,
    system: str,
    user: str,
    *,
    call_label: str = "llm",
) -> tuple[str, dict[str, int]]:
    model = model or APP_LLM_MODEL
    if is_cursor_model(model):
        return cursor_chat_completion_tracked(model, system, user, call_label=call_label)

    client = get_client()
    retries = max(1, int(os.getenv("JOB_APP_LLM_RATELIMIT_RETRIES", "8")))
    last_err: LLMError | None = None
    for attempt in range(retries):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
            msg = resp.choices[0].message
            content = getattr(msg, "content", None) or ""
            usage = extract_token_usage(resp)
            usage["step"] = call_label if attempt == 0 else f"{call_label}_retry{attempt + 1}"
            return content.strip(), usage
        except LLMError as e:
            last_err = e
            low = str(e).lower()
            if "429" not in low and "rate_limit" not in low:
                raise
            if attempt >= retries - 1:
                break
            hint = _RATE_LIMIT_PAUSE_RE.search(str(e))
            if hint:
                wait = min(120.0, float(hint.group("secs")) + 0.75)
            else:
                wait = min(120.0, 4.0 * (attempt + 1))
            time.sleep(wait)
    assert last_err is not None
    raise last_err


def chat_completion_text(model: str | None, system: str, user: str) -> str:
    text, _ = chat_completion_tracked(model, system, user)
    return text


def complete_json_tracked(
    model: str | None,
    system: str,
    user: str,
    max_retries: int = 2,
    *,
    call_label: str = "json",
) -> tuple[dict | list, dict[str, Any]]:
    model = model or APP_LLM_MODEL
    last_err: Exception | None = None
    extra = ""
    calls: list[dict] = []
    for attempt in range(max_retries + 1):
        prompt = user + extra
        step = call_label if attempt == 0 else f"{call_label}_retry{attempt + 1}"
        raw, usage = chat_completion_tracked(model, system, prompt, call_label=step)
        usage_entry = {
            "step": step,
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
        }
        calls.append(usage_entry)
        raw = strip_json_fence(raw)
        try:
            parsed = json.loads(raw)
            return parsed, pack_token_usage(call_label, model, calls)
        except json.JSONDecodeError as e:
            last_err = e
            extra = "\nYour previous reply was not valid JSON. Reply with JSON ONLY, no markdown."
    raise ValueError(f"LLM did not return valid JSON: {last_err}") from last_err


def complete_json(model: str | None, system: str, user: str, max_retries: int = 2):
    data, _ = complete_json_tracked(model, system, user, max_retries=max_retries)
    return data
