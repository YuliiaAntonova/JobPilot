"""Map cv.yml structured profile ↔ plain text ↔ notebook JSON resume."""

from __future__ import annotations

import copy
import re
from typing import Any

from job_application.cover_letter.service import resume_plain_text_for_letter as resume_plain_text_for_tailoring
from job_application.resume.cv_schema import is_cv_structured, normalize_to_cv
from job_application.resume.profile_text import structured_profile_to_plain_text


def _bullets_from_achievements(achievements: Any) -> list[str]:
    if isinstance(achievements, list):
        return [str(x).strip() for x in achievements if str(x).strip()]
    if isinstance(achievements, str) and achievements.strip():
        lines = [ln.strip() for ln in achievements.splitlines() if ln.strip()]
        return [re.sub(r"^[-*•]\s*", "", ln) for ln in lines]
    return []


def _normalize_skill_group_label(name: str) -> str:
    label = str(name or "").strip()
    if not label or label.lower() == "skills":
        return "Technical"
    return label


def _skill_item_key(text: str) -> str:
    return re.sub(r"[^\w\s]", "", str(text or "").lower()).strip()


def _dedupe_skills_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in items:
        item = str(raw or "").strip()
        if not item:
            continue
        key = _skill_item_key(item)
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _skill_group_index(item: str, original_groups: list[dict[str, Any]]) -> int | None:
    """Map a flat skill string to its original Harvard group index (fuzzy)."""
    key = _skill_item_key(item)
    if not key:
        return None
    for gi, group in enumerate(original_groups):
        for orig in group.get("items") or []:
            ok = _skill_item_key(str(orig))
            if not ok:
                continue
            if key == ok or key in ok or ok in key:
                return gi
    return None


def _redistribute_flat_skills_to_groups(
    flat: list[str],
    original_groups: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Notebook returns one flat skills list (full tailored set). Place each item
    back into its original group instead of stuffing everything into group[0].
    """
    flat_dedup = _dedupe_skills_preserve_order(flat)
    if not original_groups:
        return [{"group": "Technical", "items": flat_dedup}]

    buckets: list[list[str]] = [[] for _ in original_groups]
    for item in flat_dedup:
        gi = _skill_group_index(item, original_groups)
        target = gi if gi is not None else 0
        bucket = buckets[target]
        if not any(_skill_item_key(x) == _skill_item_key(item) for x in bucket):
            bucket.append(item)

    groups: list[dict[str, Any]] = []
    for gi, orig in enumerate(original_groups):
        items = buckets[gi]
        if not items:
            continue
        groups.append(
            {
                "group": _normalize_skill_group_label(str(orig.get("group") or "Technical")),
                "items": items,
            }
        )
    return groups or [{"group": "Technical", "items": flat_dedup}]


def _skills_to_cv_groups(
    skills: Any,
    original_groups: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    if isinstance(skills, dict):
        groups: list[dict[str, Any]] = []
        for group_name, val in skills.items():
            items = []
            if isinstance(val, list):
                items = [str(x).strip() for x in val if str(x).strip()]
            elif isinstance(val, str):
                items = [s.strip() for s in re.split(r"[,;]", val) if s.strip()]
            if items:
                groups.append(
                    {"group": _normalize_skill_group_label(str(group_name)), "items": items}
                )
        return groups

    flat: list[str] = []
    if isinstance(skills, list):
        flat = [str(x).strip() for x in skills if str(x).strip()]
    elif isinstance(skills, str):
        flat = [s.strip() for s in re.split(r"[,;\n]", skills) if s.strip()]

    if not flat:
        return copy.deepcopy(original_groups) if original_groups else []

    flat_dedup = _dedupe_skills_preserve_order(flat)
    if original_groups:
        return _redistribute_flat_skills_to_groups(flat_dedup, original_groups)

    return [{"group": "Technical", "items": flat_dedup}]


def apply_notebook_resume_to_cv(
    original_structured: dict[str, Any],
    notebook_resume: dict[str, Any],
    *,
    job_info: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Merge tailored notebook JSON sections into an existing cv.yml-shaped dict.
    Preserves basics, layout meta, certifications, languages not produced by the notebook.
    """
    base = normalize_to_cv(original_structured) if is_cv_structured(original_structured) else normalize_to_cv(
        original_structured
    )
    cv = copy.deepcopy(base)

    basics = cv.setdefault("basics", {})
    if isinstance(basics, dict):
        name = str(notebook_resume.get("name") or "").strip()
        if name:
            basics["name"] = name

    orig_experience = cv.get("experience") if isinstance(cv.get("experience"), list) else []

    def _context_for_role(company: str, period: str) -> str:
        company_k = company.strip().lower()
        period_k = period.strip().lower()
        for orig in orig_experience:
            if not isinstance(orig, dict):
                continue
            oc = str(orig.get("company") or "").strip().lower()
            op = str(orig.get("period") or "").strip().lower()
            if company_k and oc == company_k and (not period_k or not op or op == period_k):
                return str(orig.get("context") or "").strip()
        return ""

    work = notebook_resume.get("work_experience") or []
    if isinstance(work, list) and work:
        experience: list[dict[str, Any]] = []
        for row in work:
            if not isinstance(row, dict):
                continue
            bullets = _bullets_from_achievements(row.get("achievements"))
            company = str(row.get("company") or "").strip()
            period = str(row.get("duration") or row.get("period") or "").strip()
            entry: dict[str, Any] = {
                "company": company,
                "title": str(row.get("title") or "").strip(),
                "location": str(row.get("location") or "").strip(),
                "period": period,
                "bullets": bullets,
            }
            ctx = _context_for_role(company, period)
            if ctx:
                entry["context"] = ctx
            experience.append(entry)
        if experience:
            cv["experience"] = experience

    orig_skill_groups = cv.get("skills") if isinstance(cv.get("skills"), list) else []
    skill_groups = _skills_to_cv_groups(notebook_resume.get("skills"), orig_skill_groups)
    if skill_groups:
        cv["skills"] = skill_groups

    orig_education = cv.get("education") if isinstance(cv.get("education"), list) else []
    edu_in = notebook_resume.get("education") or []
    if isinstance(edu_in, list) and edu_in:
        education: list[dict[str, Any]] = []
        for row in edu_in:
            if not isinstance(row, dict):
                continue
            school = str(row.get("school") or row.get("institution") or "").strip()
            degree = str(row.get("degree") or "").strip()
            for orig in orig_education:
                if not isinstance(orig, dict):
                    continue
                if school and str(orig.get("school") or "").strip().lower() == school.lower():
                    orig_degree = str(orig.get("degree") or "").strip()
                    if orig_degree and len(degree) > len(orig_degree) + 40:
                        degree = orig_degree
                    break
            education.append(
                {
                    "school": school,
                    "degree": degree,
                    "period": str(row.get("year") or row.get("period") or "").strip(),
                    "note": "",
                }
            )
        if education:
            cv["education"] = education

    had_projects = isinstance(cv.get("projects"), list) and bool(cv.get("projects"))
    proj_in = notebook_resume.get("projects") or []
    if had_projects and isinstance(proj_in, list) and proj_in:
        projects: list[dict[str, Any]] = []
        for row in proj_in:
            if not isinstance(row, dict):
                continue
            title = str(row.get("title") or row.get("name") or "").strip()
            desc = row.get("description") or row.get("bullets") or ""
            bullets = _bullets_from_achievements(desc)
            if title:
                projects.append({"name": title, "bullets": bullets})
        if projects:
            cv["projects"] = projects
    elif not had_projects and "projects" in cv:
        cv.pop("projects", None)

    return cv
