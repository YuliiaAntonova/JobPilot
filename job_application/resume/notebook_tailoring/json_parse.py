"""Parse JSON list/dict from LLM text (notebook Untitled.ipynb logic)."""

from __future__ import annotations

import json
import re
from typing import Any


def strip_markdown_code_fence(text: str) -> str:
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*\n?", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\n?```\s*$", "", text)
    return text.strip()


def parse_llm_json_value(text: str, expected: Any, section_name: str = "") -> Any:
    cleaned = strip_markdown_code_fence(text)
    if not cleaned:
        raise ValueError("Empty model response")

    parsed = None
    last_err: Exception | None = None
    for start in [0] + [i for i, ch in enumerate(cleaned) if ch in "{["]:
        fragment = cleaned[start:].strip()
        if not fragment:
            continue
        try:
            parsed, _end = json.JSONDecoder().raw_decode(fragment)
            break
        except json.JSONDecodeError as err:
            last_err = err

    if parsed is None:
        if isinstance(expected, list):
            lines = [
                re.sub(r"^[-*•]\s*", "", line).strip()
                for line in cleaned.splitlines()
                if line.strip()
            ]
            if lines:
                return lines
        raise ValueError(last_err or "Could not parse JSON from model output")

    if isinstance(expected, list) and isinstance(parsed, list):
        return parsed
    if isinstance(expected, dict) and isinstance(parsed, dict):
        return parsed
    if isinstance(expected, list) and isinstance(parsed, dict):
        for key in (section_name, "skills", "items", "data"):
            if key and isinstance(parsed.get(key), list):
                return parsed[key]
        for val in parsed.values():
            if isinstance(val, list):
                return val
    if isinstance(expected, dict) and isinstance(parsed, list):
        if len(parsed) == 1 and isinstance(parsed[0], dict):
            return parsed[0]

    raise ValueError(
        f"Output structure mismatch: got {type(parsed).__name__}, "
        f"expected {type(expected).__name__}"
    )
