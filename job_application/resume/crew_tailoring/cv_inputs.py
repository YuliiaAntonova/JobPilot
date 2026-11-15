"""Build CrewAI kickoff bits from structured CV (dict or filled_cv.json)."""

from __future__ import annotations

import json
import re
import warnings
from pathlib import Path
from typing import Any


def _link_is_github(link: dict[str, Any]) -> bool:
    blob = " ".join(str(link.get(k) or "") for k in ("label", "text", "url")).lower()
    return "github.com" in blob or "github" in blob


def extract_github_url(cv: dict[str, Any]) -> str | None:
    for link in (cv.get("basics") or {}).get("links") or []:
        if not isinstance(link, dict):
            continue
        url = (link.get("url") or "").strip()
        if url and _link_is_github(link):
            return url.rstrip("/")
    return None


def _years_from_experience(cv: dict[str, Any]) -> str | None:
    """Rough years span from experience periods; None if unknown."""
    years: list[int] = []
    for section in ("experience", "experience_earlier"):
        for row in cv.get(section) or []:
            if not isinstance(row, dict):
                continue
            period = str(row.get("period") or "")
            years.extend(int(y) for y in re.findall(r"(20\d{2}|19\d{2})", period))
    if not years:
        return None
    span = max(years) - min(years)
    if span <= 0:
        return None
    return f"{span}+ years"


def synthesize_personal_writeup(cv: dict[str, Any]) -> str:
    """Deterministic writeup when basics.summary is empty (no extra LLM call)."""
    b = cv.get("basics") or {}
    name = (b.get("name") or "The candidate").split()[0]
    headline = (b.get("headline") or "software / data engineer").strip()
    if headline.lower().startswith("obtain "):
        role = headline[7:].replace(" position", "").strip()
        role_bit = role or "data engineer"
    else:
        role_bit = headline

    years = _years_from_experience(cv)
    years_bit = f" with {years} of experience" if years else ""

    skill_bits: list[str] = []
    for group in cv.get("skills") or []:
        if not isinstance(group, dict):
            continue
        items = [str(i) for i in (group.get("items") or []) if i][:4]
        if items:
            title = group.get("group") or "Skills"
            skill_bits.append(f"{title}: {', '.join(items)}")
    skills_sentence = (
        " Key skills include " + "; ".join(skill_bits[:4]) + "." if skill_bits else ""
    )

    latest = None
    for row in cv.get("experience") or []:
        if isinstance(row, dict) and (row.get("title") or row.get("company")):
            latest = row
            break
    latest_bit = ""
    if latest:
        title = latest.get("title") or "Engineer"
        company = latest.get("company") or ""
        ctx = (
            latest.get("project_context") or latest.get("context") or ""
        ).strip()
        latest_bit = f" Recently worked as {title}"
        if company:
            latest_bit += f" at {company}"
        latest_bit += "."
        if ctx:
            latest_bit += f" Focus: {ctx}"

    article = "an" if role_bit[:1].lower() in "aeiou" else "a"
    return (
        f"{name} is {article} {role_bit}{years_bit}, building scalable data platforms "
        f"and modern data architectures.{skills_sentence}{latest_bit}"
    ).strip()


def extract_personal_writeup(cv: dict[str, Any]) -> str:
    b = cv.get("basics") or {}
    for key in ("summary", "note"):
        val = b.get(key)
        if isinstance(val, str) and val.strip():
            return re.sub(r"\s+", " ", val.strip())
    return synthesize_personal_writeup(cv)


def load_cv(path: str | Path = "input/filled_cv.json") -> dict[str, Any]:
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{p} root must be a JSON object")
    return data


def build_crew_inputs_from_cv(
    cv: dict[str, Any] | str | Path = "input/filled_cv.json",
    *,
    job_posting_url: str = "",
    resume_md: str | Path | None = None,
) -> dict[str, str]:
    """
    Auto-fill github_url + personal_writeup from a CV dict or JSON path.

    Prefer basics.summary (Profile). Fallback synthesizes from structured fields.
    """
    if isinstance(cv, dict):
        data = cv
        source_label = "structured CV"
    else:
        data = load_cv(cv)
        source_label = str(cv)

    github = extract_github_url(data) or ""
    writeup = extract_personal_writeup(data)
    if not github:
        warnings.warn(
            f"No GitHub URL in {source_label} basics.links — continuing with empty github_url.",
            UserWarning,
            stacklevel=2,
        )
    out: dict[str, str] = {
        "github_url": github,
        "personal_writeup": writeup,
    }
    if resume_md is not None:
        out["resume_md"] = str(resume_md)
    if job_posting_url:
        out["job_posting_url"] = job_posting_url
    return out
