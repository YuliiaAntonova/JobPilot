"""cv.yml schema — source of truth for chat answers and DB structured JSON."""

from __future__ import annotations

import re
from typing import Any

CV_CHAT_FORMAT = "cv_yml"
CV_META_KEYS = frozenset({"resume_template", "resume_layout", "chat_format", "_resume_plain_text", "_experience_baseline"})

_EXP_KEY = re.compile(r"^exp_(\d+)_(.+)$")
_JOB_KEY = re.compile(r"^job_(\d+)_(.+)$")
_SKILL_KEY = re.compile(r"^skill_(\d+)_(group|items)$")
_PROJ_KEY = re.compile(r"^proj_(\d+)_(name|url|bullets)$")
_EDU_KEY = re.compile(r"^edu_(\d+)_(degree|school|period|note)$")
_EARLIER_KEY = re.compile(r"^earlier_(\d+)_(period|company|role|location|stack)$")


def _clean(text: object) -> str:
    return re.sub(r"[\u200b\u200c\u200d\ufeff]", "", str(text or "")).strip()


def _split_lines(text: str) -> list[str]:
    return [_clean(ln) for ln in str(text or "").splitlines() if _clean(ln)]


def _split_bullets(text: str) -> list[str]:
    bullets: list[str] = []
    for raw in _split_lines(text):
        line = re.sub(r"^[-•●\u25cf]\s*", "", raw)
        if line:
            bullets.append(line)
    return bullets


def _split_items(text: str) -> list[str]:
    items: list[str] = []
    for part in re.split(r"[,;\n]", _clean(text)):
        chip = part.strip()
        if chip:
            items.append(chip)
    return items


def _parse_role_and_dates(raw: str) -> tuple[str, str]:
    text = _clean(raw)
    if not text:
        return "", ""
    if "," in text:
        title, _, rest = text.partition(",")
        return title.strip(), rest.strip()
    return text, ""


def _parse_links_block(text: str) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in _split_lines(text):
        label = "Link"
        url = raw
        if "|" in raw:
            left, _, right = raw.partition("|")
            label = _clean(left) or "Link"
            url = _clean(right) or _clean(left)
        elif raw.lower().startswith("linkedin"):
            label = "LinkedIn"
        elif raw.lower().startswith("github"):
            label = "GitHub"
        url = url if url.startswith("http") else f"https://{url.lstrip('/')}"
        key = url.casefold()
        if key in seen:
            continue
        seen.add(key)
        links.append({"label": label, "text": _clean(raw.split("|")[-1]) if "|" in raw else url, "url": url})
    return links


def is_cv_structured(data: dict[str, Any] | None) -> bool:
    return isinstance(data, dict) and isinstance(data.get("basics"), dict)


def is_cv_chat_answers(answers: dict[str, str] | None) -> bool:
    if not isinstance(answers, dict):
        return False
    return bool(
        answers.get("name")
        or answers.get("headline")
        or any(k.startswith("exp_") for k in answers)
        or any(k.startswith("skill_") for k in answers)
    )


def interests_text_from_cv(cv: dict[str, Any]) -> str:
    """Top-level interests as a single display string."""
    raw = cv.get("interests")
    if isinstance(raw, list):
        parts = [_clean(x) for x in raw if _clean(x)]
        return ", ".join(parts)
    if isinstance(raw, str):
        text = _clean(raw)
        if text.lower().startswith("interests:"):
            text = re.sub(r"^interests\s*:\s*", "", text, flags=re.I).strip()
        return text
    return ""


def _clean_project_context(text: object) -> str:
    raw = _clean(text)
    if not raw:
        return ""
    return re.sub(r"^project context\s*:\s*", "", raw, flags=re.I).strip()


def _interests_text_from_note(note: str) -> str:
    text = _clean(note)
    if not text:
        return ""
    match = re.match(r"^interests\s*[:\-–—]\s*(.+)$", text, re.I)
    if match:
        return _clean(match.group(1))
    if re.match(r"^interests\b", text, re.I):
        return re.sub(r"^interests\s*", "", text, flags=re.I).strip(" :-–—\t")
    return ""


def migrate_interests_from_note(cv: dict[str, Any]) -> None:
    """In-place: move legacy basics.note 'Interests: …' into cv['interests'] and clear note."""
    basics = cv.get("basics")
    if not isinstance(basics, dict):
        return
    note = _clean(basics.get("note") or "")
    if not note:
        return
    from_note = _interests_text_from_note(note)
    if not from_note:
        return
    if not interests_text_from_cv(cv):
        cv["interests"] = from_note
    basics["note"] = ""


def _indices_from_answers(answers: dict[str, str], pattern: re.Pattern[str]) -> list[int]:
    found: set[int] = set()
    for key in answers:
        match = pattern.match(key)
        if match:
            found.add(int(match.group(1)))
    return sorted(found)


def _legacy_chat_to_cv(answers: dict[str, str]) -> dict[str, Any]:
    """Map old chat keys (fullName, job_*) into cv.yml shape."""
    name = _clean(answers.get("name") or answers.get("fullName") or "")
    headline = _clean(
        answers.get("headline")
        or answers.get("desiredPosition")
        or answers.get("desiredPositions")
        or answers.get("objective")
        or ""
    )
    basics: dict[str, Any] = {
        "name": name,
        "headline": headline,
        "location": _clean(answers.get("location") or answers.get("city") or ""),
        "email": _clean(answers.get("email") or ""),
        "phone": _clean(answers.get("phone") or ""),
        "summary": _clean(answers.get("summary") or answers.get("about") or ""),
        "note": _clean(answers.get("note") or ""),
        "links": _parse_links_block(_clean(answers.get("links") or "")),
    }
    if not basics["links"]:
        for label, key in (("LinkedIn", "linkedin"), ("GitHub", "github")):
            raw = _clean(answers.get(key) or "")
            if raw:
                url = raw if raw.startswith("http") else f"https://{raw.lstrip('/')}"
                basics["links"].append({"label": label, "text": raw, "url": url})

    cv: dict[str, Any] = {"basics": basics}

    skills: list[dict[str, Any]] = []
    for idx in _indices_from_answers(answers, _SKILL_KEY):
        group = _clean(answers.get(f"skill_{idx}_group") or "")
        items = _split_items(answers.get(f"skill_{idx}_items") or "")
        if group and items:
            skills.append({"group": group, "items": items})
    if not skills:
        skills_text = _clean(answers.get("skills") or answers.get("mainTechStack") or "")
        if skills_text:
            for line in _split_lines(skills_text):
                if ":" in line:
                    group, body = line.split(":", 1)
                    items = _split_items(body)
                    if group.strip() and items:
                        skills.append({"group": group.strip(), "items": items})
                else:
                    items = _split_items(line)
                    if items:
                        skills.append({"group": "Technical Skills", "items": items})
    if skills:
        cv["skills"] = skills

    experience: list[dict[str, Any]] = []
    exp_indices = sorted(
        set(_indices_from_answers(answers, _EXP_KEY)) | set(_indices_from_answers(answers, _JOB_KEY))
    )
    for idx in exp_indices:
        prefix = f"exp_{idx}_" if f"exp_{idx}_company" in answers or f"exp_{idx}_title" in answers else f"job_{idx}_"
        company = _clean(answers.get(f"{prefix}company") or "")
        title = _clean(answers.get(f"{prefix}title") or "")
        period = _clean(answers.get(f"{prefix}period") or "")
        location = _clean(answers.get(f"{prefix}location") or "")
        bullets = _split_bullets(answers.get(f"{prefix}bullets") or "")

        if prefix.startswith("job_"):
            role_dates = _clean(answers.get(f"{prefix}roleAndDates") or "")
            if role_dates and not title:
                title, period_from_role = _parse_role_and_dates(role_dates)
                period = period or period_from_role
            desc = _clean(answers.get(f"{prefix}description") or "")
            result = _clean(answers.get(f"{prefix}result") or "")
            if not bullets:
                if desc:
                    bullets.append(desc)
                if result:
                    bullets.extend(_split_bullets(result))

        if company or title or bullets:
            row: dict[str, Any] = {
                "company": company or title,
                "title": title,
                "location": location,
                "period": period,
                "bullets": bullets,
            }
            context = _clean_project_context(
                answers.get(f"{prefix}context") or answers.get(f"{prefix}project_context") or ""
            )
            if context:
                row["context"] = context
            experience.append(row)
    if experience:
        cv["experience"] = experience

    earlier: list[dict[str, Any]] = []
    for idx in _indices_from_answers(answers, _EARLIER_KEY):
        row = {
            "period": _clean(answers.get(f"earlier_{idx}_period") or ""),
            "company": _clean(answers.get(f"earlier_{idx}_company") or ""),
            "role": _clean(answers.get(f"earlier_{idx}_role") or ""),
            "location": _clean(answers.get(f"earlier_{idx}_location") or ""),
            "stack": _split_items(answers.get(f"earlier_{idx}_stack") or ""),
        }
        if any(row.values()):
            earlier.append(row)
    if earlier:
        cv["experience_earlier"] = earlier

    projects: list[dict[str, Any]] = []
    for idx in _indices_from_answers(answers, _PROJ_KEY):
        name = _clean(answers.get(f"proj_{idx}_name") or "")
        url = _clean(answers.get(f"proj_{idx}_url") or "")
        bullets = _split_bullets(answers.get(f"proj_{idx}_bullets") or "")
        if name or bullets or url:
            row: dict[str, Any] = {"name": name or "Project", "bullets": bullets}
            if url:
                row["url"] = url
            projects.append(row)
    if not projects:
        projects_text = _clean(answers.get("projects") or "")
        if projects_text:
            for block in re.split(r"\n\s*\n", projects_text):
                lines = _split_lines(block)
                if not lines:
                    continue
                projects.append({"name": lines[0].lstrip("- "), "bullets": lines[1:] or [lines[0]]})
    if projects:
        cv["projects"] = projects

    education: list[dict[str, Any]] = []
    for idx in _indices_from_answers(answers, _EDU_KEY):
        row = {
            "degree": _clean(answers.get(f"edu_{idx}_degree") or ""),
            "school": _clean(answers.get(f"edu_{idx}_school") or ""),
            "period": _clean(answers.get(f"edu_{idx}_period") or ""),
            "note": _clean(answers.get(f"edu_{idx}_note") or ""),
        }
        if row["degree"] or row["school"]:
            education.append(row)
    if not education:
        edu_text = _clean(answers.get("education") or "")
        lines = _split_lines(edu_text)
        if lines:
            education.append({"school": lines[0], "degree": lines[1] if len(lines) > 1 else "", "period": ""})
    if education:
        cv["education"] = education

    certifications: list[Any] = []
    for line in _split_lines(answers.get("certifications") or answers.get("courses") or ""):
        certifications.append(line.lstrip("- "))
    if certifications:
        cv["certifications"] = certifications

    languages: list[Any] = []
    for line in _split_lines(answers.get("languages") or ""):
        if "—" in line or "–" in line:
            name, _, level = line.partition("—") if "—" in line else line.partition("–")
            languages.append({"name": name.strip(), "level": level.strip()})
        else:
            languages.append(line)
    if languages:
        cv["languages"] = languages

    recognition: dict[str, Any] = {}
    books: list[dict[str, str]] = []
    for raw in _split_lines(answers.get("recognition_books") or ""):
        parts = [p.strip() for p in re.split(r"\s*\|\s*", raw) if p.strip()]
        if not parts:
            continue
        book: dict[str, str] = {"title": parts[0]}
        if len(parts) > 1:
            book["publisher"] = parts[1]
        if len(parts) > 2:
            book["year"] = parts[2]
        if len(parts) > 3:
            book["url"] = parts[3]
        books.append(book)
    if books:
        recognition["books"] = books

    highlights = _split_bullets(answers.get("recognition_highlights") or "")
    if highlights:
        recognition["highlights"] = highlights
    if recognition:
        cv["recognition"] = recognition

    interests = _clean(answers.get("interests") or "")
    if interests:
        cv["interests"] = interests

    return cv


def chat_answers_to_cv(answers: dict[str, str]) -> dict[str, Any]:
    """Chat answers → cv.yml dict (stored in resume_profiles.structured)."""
    cv = normalize_to_cv(
        {
            **_legacy_chat_to_cv(answers),
            "resume_template": "harvard",
            "chat_format": CV_CHAT_FORMAT,
        }
    )
    return cv


def cv_to_chat_answers(cv: dict[str, Any]) -> dict[str, str]:
    """cv.yml dict → flat chat answers for the editor."""
    data = normalize_to_cv(cv)
    b = data.get("basics") if isinstance(data.get("basics"), dict) else {}
    out: dict[str, str] = {
        "name": _clean(b.get("name") or ""),
        "headline": _clean(b.get("headline") or ""),
        "location": _clean(b.get("location") or ""),
        "email": _clean(b.get("email") or ""),
        "phone": _clean(b.get("phone") or ""),
        "summary": _clean(b.get("summary") or ""),
        "note": _clean(b.get("note") or ""),
    }
    links = b.get("links") if isinstance(b.get("links"), list) else []
    if links:
        out["links"] = "\n".join(
            f'{ln.get("label", "Link")} | {ln.get("url") or ln.get("text", "")}'
            for ln in links
            if isinstance(ln, dict) and (ln.get("url") or ln.get("text"))
        )

    for idx, group in enumerate(data.get("skills") or []):
        if not isinstance(group, dict):
            continue
        out[f"skill_{idx}_group"] = _clean(group.get("group") or "")
        items = group.get("items") or []
        if isinstance(items, list):
            out[f"skill_{idx}_items"] = ", ".join(_clean(x) for x in items if _clean(x))

    for idx, job in enumerate(data.get("experience") or []):
        if not isinstance(job, dict):
            continue
        prefix = f"exp_{idx}_"
        out[f"{prefix}company"] = _clean(job.get("company") or "")
        out[f"{prefix}title"] = _clean(job.get("title") or "")
        out[f"{prefix}location"] = _clean(job.get("location") or "")
        out[f"{prefix}period"] = _clean(job.get("period") or job.get("dates") or "")
        bullets = job.get("bullets") or job.get("highlights") or []
        if isinstance(bullets, list):
            out[f"{prefix}bullets"] = "\n".join(_clean(x) for x in bullets if _clean(x))
        context = _clean_project_context(job.get("context") or job.get("project_context") or "")
        if context:
            out[f"{prefix}context"] = context

    for idx, row in enumerate(data.get("experience_earlier") or []):
        if not isinstance(row, dict):
            continue
        out[f"earlier_{idx}_period"] = _clean(row.get("period") or "")
        out[f"earlier_{idx}_company"] = _clean(row.get("company") or "")
        out[f"earlier_{idx}_role"] = _clean(row.get("role") or "")
        out[f"earlier_{idx}_location"] = _clean(row.get("location") or "")
        stack = row.get("stack") or []
        if isinstance(stack, list):
            out[f"earlier_{idx}_stack"] = ", ".join(_clean(x) for x in stack if _clean(x))

    for idx, project in enumerate(data.get("projects") or []):
        if not isinstance(project, dict):
            continue
        out[f"proj_{idx}_name"] = _clean(project.get("name") or "")
        url = _clean(project.get("url") or "")
        if url:
            out[f"proj_{idx}_url"] = url
        bullets = project.get("bullets") or []
        if isinstance(bullets, list):
            out[f"proj_{idx}_bullets"] = "\n".join(_clean(x) for x in bullets if _clean(x))

    for idx, edu in enumerate(data.get("education") or []):
        if not isinstance(edu, dict):
            continue
        out[f"edu_{idx}_degree"] = _clean(edu.get("degree") or "")
        out[f"edu_{idx}_school"] = _clean(edu.get("school") or edu.get("institution") or "")
        out[f"edu_{idx}_period"] = _clean(edu.get("period") or edu.get("dates") or "")
        out[f"edu_{idx}_note"] = _clean(edu.get("note") or "")

    certs = data.get("certifications") or []
    if isinstance(certs, list) and certs:
        lines: list[str] = []
        for c in certs:
            if isinstance(c, str):
                lines.append(_clean(c))
            elif isinstance(c, dict):
                lines.append(_clean(c.get("name") or ""))
        out["certifications"] = "\n".join(x for x in lines if x)

    langs = data.get("languages") or []
    if isinstance(langs, list) and langs:
        lang_lines: list[str] = []
        for lang in langs:
            if isinstance(lang, str):
                lang_lines.append(_clean(lang))
            elif isinstance(lang, dict):
                name = _clean(lang.get("name") or "")
                level = _clean(lang.get("level") or "")
                lang_lines.append(f"{name} — {level}" if level else name)
        out["languages"] = "\n".join(x for x in lang_lines if x)

    rec = data.get("recognition") if isinstance(data.get("recognition"), dict) else {}
    books = rec.get("books") if isinstance(rec.get("books"), list) else []
    if books:
        book_lines: list[str] = []
        for bk in books:
            if not isinstance(bk, dict):
                continue
            title = _clean(bk.get("title") or "")
            if not title:
                continue
            parts = [title]
            for key in ("publisher", "year", "url"):
                val = _clean(bk.get(key) or "")
                if val:
                    parts.append(val)
            book_lines.append(" | ".join(parts))
        if book_lines:
            out["recognition_books"] = "\n".join(book_lines)

    highlights = rec.get("highlights") if isinstance(rec.get("highlights"), list) else []
    if highlights:
        out["recognition_highlights"] = "\n".join(_clean(x) for x in highlights if _clean(x))

    interests = interests_text_from_cv(data)
    if interests:
        out["interests"] = interests

    return {k: v for k, v in out.items() if _clean(v)}


def legacy_structured_to_cv(data: dict[str, Any]) -> dict[str, Any]:
    """Old structured JSON (personal/experience) → cv.yml."""
    from job_application.resume.cv_yaml import structured_to_harvard_cv
    from job_application.resume.profile_text import (
        _experience_entries_from_structured,
        enrich_structured_personal_from_plain,
    )

    from job_application.resume.profile_text import (
        _education_entries_from_chat_or_structured,
        _extract_supplementary_from_plain_text,
        _parse_courses,
    )

    enriched = enrich_structured_personal_from_plain(dict(data))
    canonical_jobs = _experience_entries_from_structured(enriched)
    if canonical_jobs and not enriched.get("_keep_stored_experience_bullets"):
        enriched["experience"] = canonical_jobs

    plain = str(enriched.get("_resume_plain_text") or "").strip()
    if plain:
        supp = _extract_supplementary_from_plain_text(plain)
        if supp.get("education") and not enriched.get("education"):
            enriched["education"] = _education_entries_from_chat_or_structured(supp["education"], [])
        if supp.get("courses") and not enriched.get("certifications"):
            enriched["certifications"] = _parse_courses(supp["courses"])
        if supp.get("languages") and not enriched.get("languages"):
            enriched["languages"] = [
                ln.lstrip("- ").strip() for ln in supp["languages"].splitlines() if ln.strip()
            ]

    cv = structured_to_harvard_cv(enriched)
    cv["resume_template"] = str(data.get("resume_template") or "harvard")
    cv["chat_format"] = CV_CHAT_FORMAT
    plain = _clean(data.get("_resume_plain_text") or "")
    if plain:
        cv["_resume_plain_text"] = plain
    baseline = data.get("_experience_baseline")
    if isinstance(baseline, list) and baseline:
        cv["_experience_baseline"] = baseline
    return cv


def normalize_to_cv(data: dict[str, Any]) -> dict[str, Any]:
    if is_cv_structured(data):
        cv = dict(data)
    else:
        cv = legacy_structured_to_cv(data)
    migrate_interests_from_note(cv)
    from job_application.resume.cv_yml_io import (
        enrich_cv_basics_from_plain,
        normalize_dates,
        split_experience_sections,
    )

    plain = str(data.get("_resume_plain_text") or cv.get("_resume_plain_text") or "").strip()
    cv = normalize_dates(cv)
    cv = split_experience_sections(cv)
    if plain:
        cv = enrich_cv_basics_from_plain(cv, plain)
    return cv


def desired_role_from_cv(cv: dict[str, Any]) -> str:
    b = cv.get("basics") if isinstance(cv.get("basics"), dict) else {}
    return _clean(b.get("headline") or "")


def cv_to_plain_text(cv: dict[str, Any]) -> str:
    """Plain text mirror of cv.yml for ATS / profile_text."""
    data = normalize_to_cv(cv)
    b = data.get("basics") if isinstance(data.get("basics"), dict) else {}
    lines: list[str] = []

    name = _clean(b.get("name") or "")
    if name:
        lines.append(name.upper())
        lines.append("")

    contact_bits = [
        _clean(b.get("location") or ""),
        _clean(b.get("email") or ""),
        _clean(b.get("phone") or ""),
    ]
    contact_bits = [x for x in contact_bits if x]
    if contact_bits:
        lines.extend(["CONTACT", " · ".join(contact_bits), ""])

    summary = _clean(b.get("summary") or "")
    if summary:
        lines.extend(["SUMMARY", summary, ""])

    skills = data.get("skills") or []
    if isinstance(skills, list) and skills:
        lines.append("SKILLS")
        for group in skills:
            if not isinstance(group, dict):
                continue
            g = _clean(group.get("group") or "")
            items = ", ".join(_clean(x) for x in (group.get("items") or []) if _clean(x))
            if g and items:
                lines.append(f"{g}: {items}")
        lines.append("")

    for job in data.get("experience") or []:
        if not isinstance(job, dict):
            continue
        header = " · ".join(
            x
            for x in (
                _clean(job.get("company") or ""),
                _clean(job.get("title") or ""),
                _clean(job.get("period") or ""),
            )
            if x
        )
        if header:
            lines.append(header)
        context = _clean_project_context(job.get("context") or job.get("project_context") or "")
        if context:
            lines.append(f"Project context: {context}")
        for bullet in job.get("bullets") or []:
            text = _clean(bullet)
            if text:
                lines.append(f"- {text}")
        lines.append("")

    for project in data.get("projects") or []:
        if not isinstance(project, dict):
            continue
        lines.append(_clean(project.get("name") or "Project"))
        for bullet in project.get("bullets") or []:
            text = _clean(bullet)
            if text:
                lines.append(f"- {text}")
        lines.append("")

    for edu in data.get("education") or []:
        if not isinstance(edu, dict):
            continue
        lines.append(_clean(edu.get("degree") or ""))
        lines.append(_clean(edu.get("school") or ""))
        lines.append("")

    interests = interests_text_from_cv(data)
    if interests:
        lines.extend(["INTERESTS", interests, ""])

    return "\n".join(ln for ln in lines if ln is not None).strip()
