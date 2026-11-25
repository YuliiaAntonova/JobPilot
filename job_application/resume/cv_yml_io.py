"""cv.yml helpers — date/experience normalization and YAML I/O."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

MONTHS = {
    "January": "Jan",
    "February": "Feb",
    "March": "Mar",
    "April": "Apr",
    "May": "May",
    "June": "Jun",
    "July": "Jul",
    "August": "Aug",
    "September": "Sep",
    "October": "Oct",
    "November": "Nov",
    "December": "Dec",
}

EXPERIENCE_RECENT_LIMIT = 3


def _normalize_period_text(period: str) -> str:
    text = str(period or "")
    for full, short in MONTHS.items():
        text = re.sub(rf"\b{full}\b", short, text, flags=re.IGNORECASE)
    text = re.sub(r"\s*[-–—]\s*", " – ", text)
    text = re.sub(r"\bCurrent\b", "Present", text, flags=re.IGNORECASE)
    text = re.sub(r"\bNow\b", "Present", text, flags=re.IGNORECASE)
    return text.strip()


def _exp_clean(text: object) -> str:
    return str(text or "").strip()


def _unified_experience_job(job: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(job, dict):
        return None
    title = _exp_clean(job.get("title") or job.get("role"))
    company = _exp_clean(job.get("company"))
    if not company and not title:
        return None
    bullets = [_exp_clean(x) for x in (job.get("bullets") or []) if _exp_clean(x)]
    stack = [_exp_clean(x) for x in (job.get("stack") or []) if _exp_clean(x)]
    return {
        "company": company or title,
        "title": title,
        "location": _exp_clean(job.get("location")),
        "period": _exp_clean(job.get("period")),
        "context": _exp_clean(job.get("context") or job.get("project_context")),
        "bullets": bullets,
        "stack": stack,
    }


def _to_experience_entry(job: dict[str, Any]) -> dict[str, Any]:
    bullets = list(job.get("bullets") or [])
    stack = list(job.get("stack") or [])
    if not bullets and stack:
        bullets = list(stack)
    entry: dict[str, Any] = {
        "company": job["company"],
        "title": job["title"],
        "location": job.get("location", ""),
        "period": job.get("period", ""),
        "bullets": bullets,
    }
    if job.get("context"):
        entry["context"] = job["context"]
    return entry


def _to_earlier_entry(job: dict[str, Any]) -> dict[str, Any]:
    stack = list(job.get("stack") or [])
    if not stack:
        stack = list(job.get("bullets") or [])
    return {
        "period": job.get("period", ""),
        "company": job["company"],
        "role": job.get("title", ""),
        "location": job.get("location", ""),
        "stack": stack,
    }


def split_experience_sections(cv: dict[str, Any], limit: int = EXPERIENCE_RECENT_LIMIT) -> dict[str, Any]:
    """Keep the N most recent roles in experience; move the rest to experience_earlier."""
    data = dict(cv or {})
    unified: list[dict[str, Any]] = []
    for job in data.get("experience") or []:
        row = _unified_experience_job(job)
        if row:
            unified.append(row)
    for job in data.get("experience_earlier") or []:
        row = _unified_experience_job(job)
        if row:
            unified.append(row)
    if not unified:
        data.pop("experience", None)
        data.pop("experience_earlier", None)
        return data

    recent = unified[:limit]
    older = unified[limit:]
    data["experience"] = [_to_experience_entry(job) for job in recent]
    if older:
        data["experience_earlier"] = [_to_earlier_entry(job) for job in older]
    else:
        data.pop("experience_earlier", None)
    return data


def enrich_cv_basics_from_plain(cv: dict[str, Any], plain_text: str) -> dict[str, Any]:
    """Fill missing basics contact fields from resume plain text."""
    plain = str(plain_text or "").strip()
    if not plain:
        return cv
    from job_application.resume.profile_text import _extract_contact_from_plain_text, _sanitize_contact_location

    contact = _extract_contact_from_plain_text(plain)
    basics = cv.setdefault("basics", {})
    if not isinstance(basics, dict):
        return cv

    if contact.get("email") and not _exp_clean(basics.get("email")):
        basics["email"] = contact["email"]
    if contact.get("phone") and not _exp_clean(basics.get("phone")):
        basics["phone"] = contact["phone"]

    plain_loc = _sanitize_contact_location(contact.get("location", ""))
    existing_loc = _sanitize_contact_location(str(basics.get("location") or ""))
    if plain_loc and not existing_loc:
        basics["location"] = plain_loc
    elif plain_loc and existing_loc and "," in plain_loc and "," not in existing_loc:
        basics["location"] = plain_loc
    return cv


def normalize_dates(cv: dict[str, Any]) -> dict[str, Any]:
    data = dict(cv or {})
    experience = data.get("experience")
    if isinstance(experience, list):
        for job in experience:
            if not isinstance(job, dict):
                continue
            job["period"] = _normalize_period_text(job.get("period", ""))

    earlier = data.get("experience_earlier")
    if isinstance(earlier, list):
        for job in earlier:
            if not isinstance(job, dict):
                continue
            period = _normalize_period_text(job.get("period", ""))
            years = re.findall(r"\b(?:19|20)\d{2}\b", period)
            if len(years) >= 2:
                job["period"] = f"{years[0]} – {years[-1]}"
            elif len(years) == 1:
                if re.search(r"\bPresent\b", period, re.IGNORECASE):
                    job["period"] = f"{years[0]} – Present"
                else:
                    job["period"] = years[0]
            else:
                job["period"] = period
    return data


def write_cv_yml(cv: dict[str, Any], output: Path | str) -> Path:
    """Write normalized cv.yml for Harvard render / preview."""
    dst = Path(output).expanduser().resolve()
    data = normalize_dates(dict(cv or {}))
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100),
        encoding="utf-8",
    )
    return dst
