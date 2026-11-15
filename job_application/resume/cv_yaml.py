"""Harvard-format resume: structured JSON ↔ cv.yml (YAML only)."""

from __future__ import annotations

import html
import re
from typing import Any

import yaml

from job_application.resume.profile_text import (
    _job_highlights,
    _parse_labeled_skills_line,
    skills_lines_for_render,
)

_SKILL_FIELD_GROUPS: tuple[tuple[str, str], ...] = (
    ("skill_handsOn", "Hands-on experience"),
    ("skill_knowledge", "Knowledge of"),
    ("skill_databases", "Cloud & Data"),
    ("skill_git", "Git"),
    ("skill_collab", "Experience with"),
    ("skill_tools", "Tools"),
    ("skill_domain", "Domain expertise"),
)


def esc(s: object) -> str:
    return html.escape(str(s), quote=True)


def _clean(text: object) -> str:
    return re.sub(r"[\u200b\u200c\u200d\ufeff]", "", str(text or "")).strip()


def _split_skill_items(text: str) -> list[str]:
    items: list[str] = []
    for part in re.split(r"[,;\n]", _clean(text)):
        chip = part.strip()
        if chip:
            items.append(chip)
    return items


def _skills_groups_from_structured(data: dict[str, Any]) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    chat = data.get("chat_answers") if isinstance(data.get("chat_answers"), dict) else {}
    for key, label in _SKILL_FIELD_GROUPS:
        raw = _clean(chat.get(key) or "")
        if raw:
            items = _split_skill_items(raw)
            if items:
                groups.append({"group": label, "items": items})

    skills_text = _clean(data.get("skills_text") or "")
    skill_lines = skills_lines_for_render(
        skills_text,
        skills_list=[str(x) for x in (data.get("skills") or []) if _clean(x)],
    )
    seen_groups = {g["group"].casefold() for g in groups}
    for line in skill_lines:
        labeled = _parse_labeled_skills_line(line)
        if labeled:
            group_name, body = labeled
            items = _split_skill_items(body)
            if items and group_name.casefold() not in seen_groups:
                groups.append({"group": group_name, "items": items})
                seen_groups.add(group_name.casefold())
            continue
        if ":" in line:
            group_name, body = line.split(":", 1)
            items = _split_skill_items(body)
            if items and group_name.strip().casefold() not in seen_groups:
                groups.append({"group": group_name.strip(), "items": items})
                seen_groups.add(group_name.strip().casefold())

    flat = [str(x) for x in (data.get("skills") or data.get("main_tech_stack") or []) if _clean(x)]
    if not groups and flat:
        groups.append({"group": "Technical Skills", "items": flat})
    return groups


def _links_from_structured(data: dict[str, Any]) -> list[dict[str, str]]:
    pers = data.get("personal") if isinstance(data.get("personal"), dict) else {}
    links: list[dict[str, str]] = []
    seen: set[str] = set()

    def add(label: str, text: str, url: str) -> None:
        text = _clean(text)
        url = _clean(url)
        if not text and not url:
            return
        key = (label.casefold(), url.casefold())
        if key in seen:
            return
        seen.add(key)
        links.append({"label": label, "text": text or url, "url": url or text})

    for label, key in (("LinkedIn", "linkedin"), ("GitHub", "github"), ("Xing", "xing")):
        raw = _clean(pers.get(key) or "")
        if raw:
            url = raw if raw.startswith("http") else f"https://{raw.lstrip('/')}"
            add(label, raw, url)

    portfolio = _clean(pers.get("portfolio") or "")
    if portfolio:
        for chunk in re.split(r"[\n|]", portfolio):
            token = _clean(chunk)
            if not token:
                continue
            url = token if token.startswith("http") else f"https://{token.lstrip('/')}"
            add("Link", token, url)

    chat_links = data.get("chat_answers") if isinstance(data.get("chat_answers"), dict) else {}
    for chunk in re.split(r"[\n|]", _clean(chat_links.get("links") or "")):
        token = _clean(chunk)
        if not token:
            continue
        url = token if token.startswith("http") else f"https://{token.lstrip('/')}"
        low = token.lower()
        label = "LinkedIn" if "linkedin" in low else "GitHub" if "github" in low else "Link"
        add(label, token, url)

    return links


def _experience_entries(data: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    exp = data.get("experience")
    if not isinstance(exp, list):
        return out
    for job in exp:
        if not isinstance(job, dict):
            continue
        company = _clean(job.get("company") or job.get("company_name") or "")
        title = _clean(job.get("title") or job.get("position") or job.get("job_title") or "")
        if not company and not title:
            continue
        bullets = [_clean(x) for x in _job_highlights(job) if _clean(x)]
        entry: dict[str, Any] = {
            "company": company or title,
            "title": title,
            "location": _clean(job.get("location") or job.get("subtitle") or ""),
            "period": _clean(job.get("dates") or job.get("period") or ""),
            "bullets": bullets,
        }
        context = _clean(job.get("context") or job.get("project_context") or "")
        if context:
            entry["context"] = context
        variant = job.get("variant")
        if variant:
            entry["variant"] = variant
        out.append(entry)
    return out


def _project_entries(data: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    projects = data.get("projects")
    if isinstance(projects, list):
        for project in projects:
            if not isinstance(project, dict):
                continue
            name = _clean(project.get("name") or project.get("title") or "")
            bullets = [_clean(x) for x in (project.get("bullets") or project.get("highlights") or []) if _clean(x)]
            desc = _clean(project.get("description") or "")
            if desc and not bullets:
                bullets = [desc]
            if name or bullets:
                out.append({"name": name or "Project", "bullets": bullets})
    text = _clean(data.get("projects_text") or "")
    if not out and text:
        for block in re.split(r"\n\s*\n", text):
            lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
            if not lines:
                continue
            heading = lines[0].lstrip("- ").strip()
            body = [ln.lstrip("- ").strip() for ln in lines[1:] if ln.strip()]
            out.append({"name": heading, "bullets": body or [heading]})
    return out


def _education_entries(data: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    edu = data.get("education")
    if isinstance(edu, list):
        for row in edu:
            if not isinstance(row, dict):
                continue
            school = _clean(row.get("institution") or row.get("school") or "")
            degree = _clean(row.get("degree") or "")
            period = _clean(row.get("graduation_date") or row.get("period") or row.get("dates") or "")
            note = _clean(row.get("note") or row.get("details") or "")
            if school or degree:
                entry = {"school": school, "degree": degree, "period": period}
                if note:
                    entry["note"] = note
                out.append(entry)
    if out:
        return out
    text = _clean(data.get("education_text") or "")
    if not text:
        return out
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if lines:
        out.append({"school": lines[0], "degree": lines[1] if len(lines) > 1 else "", "period": ""})
    return out


def _certification_entries(data: dict[str, Any]) -> list[Any]:
    out: list[Any] = []
    for key in ("certifications", "courses"):
        items = data.get(key)
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, str) and _clean(item):
                out.append(_clean(item))
            elif isinstance(item, dict):
                name = _clean(item.get("name") or item.get("title") or "")
                if name:
                    cert = {"name": name}
                    issuer = _clean(item.get("issuer") or item.get("provider") or "")
                    year = _clean(item.get("year") or item.get("date") or "")
                    if issuer:
                        cert["issuer"] = issuer
                    if year:
                        cert["year"] = year
                    out.append(cert)
    text = _clean(data.get("courses_text") or "")
    if not out and text:
        for line in text.splitlines():
            line = line.lstrip("- ").strip()
            if line:
                out.append(line)
    return out


def _language_entries(data: dict[str, Any]) -> list[Any]:
    out: list[Any] = []
    langs = data.get("languages")
    if isinstance(langs, list):
        for item in langs:
            if isinstance(item, str) and _clean(item):
                out.append(_clean(item))
            elif isinstance(item, dict):
                name = _clean(item.get("name") or item.get("language") or "")
                level = _clean(item.get("level") or "")
                if name:
                    out.append({"name": name, "level": level} if level else name)
    text = _clean(data.get("languages_text") or "")
    if not out and text:
        for line in text.splitlines():
            line = line.lstrip("- ").strip()
            if line:
                out.append(line)
    return out


def structured_to_harvard_cv(structured: dict[str, Any]) -> dict[str, Any]:
    """Project structured JSON → workshop cv.yml shape."""
    from job_application.resume.cv_schema import CV_META_KEYS, is_cv_structured

    if is_cv_structured(structured):
        return {
            k: v
            for k, v in structured.items()
            if k not in CV_META_KEYS and not str(k).startswith("_")
        }

    data = dict(structured)
    pers = data.get("personal") if isinstance(data.get("personal"), dict) else {}
    full_name = _clean(pers.get("full_name") or "")
    if not full_name:
        full_name = " ".join(
            x for x in (_clean(pers.get("first_name")), _clean(pers.get("last_name"))) if x
        ).strip()

    desired = _clean(data.get("objective") or "")
    if not desired:
        roles = data.get("desired_roles")
        if isinstance(roles, list) and roles:
            desired = _clean(roles[0])

    basics: dict[str, Any] = {
        "name": full_name or "Candidate",
        "headline": desired,
        "location": _clean(pers.get("location") or pers.get("city") or ""),
        "email": _clean(pers.get("email") or ""),
        "phone": _clean(pers.get("phone") or ""),
        "summary": _clean(data.get("summary") or data.get("professional_summary") or ""),
        "links": _links_from_structured(data),
    }
    if data.get("resume_density") == "compact":
        basics["density"] = "compact"

    cv: dict[str, Any] = {"basics": basics}
    skills = _skills_groups_from_structured(data)
    if skills:
        cv["skills"] = skills

    experience = _experience_entries(data)
    if experience:
        cv["experience"] = experience

    earlier = data.get("experience_earlier")
    if isinstance(earlier, list) and earlier:
        cv["experience_earlier"] = earlier

    projects = _project_entries(data)
    if projects:
        cv["projects"] = projects

    education = _education_entries(data)
    if education:
        cv["education"] = education

    certifications = _certification_entries(data)
    if certifications:
        cv["certifications"] = certifications

    languages = _language_entries(data)
    if languages:
        cv["languages"] = languages

    recognition = data.get("recognition")
    if isinstance(recognition, dict) and recognition:
        cv["recognition"] = recognition

    interests = _clean(data.get("interests_text") or "")
    if not interests:
        raw = data.get("interests")
        if isinstance(raw, list):
            parts = [_clean(x) for x in raw if _clean(x)]
            interests = ", ".join(parts)
        elif isinstance(raw, str):
            interests = _clean(raw)
    if interests:
        cv["interests"] = interests

    return cv


def harvard_cv_to_structured(cv: dict[str, Any]) -> dict[str, Any]:
    """Workshop cv.yml → DB structured (same schema, plus metadata)."""
    if not isinstance(cv, dict):
        raise ValueError("cv must be a mapping")
    out = dict(cv)
    out["resume_template"] = "harvard"
    out["chat_format"] = "cv_yml"
    return out

def structured_to_harvard_yaml(structured: dict[str, Any]) -> str:
    cv = structured_to_harvard_cv(structured)
    return yaml.safe_dump(cv, sort_keys=False, allow_unicode=True, width=1000)


def harvard_yaml_to_structured(text: str) -> dict[str, Any]:
    cv = yaml.safe_load(text)
    if not isinstance(cv, dict):
        raise ValueError("YAML must contain a mapping at the top level")
    return harvard_cv_to_structured(cv)
