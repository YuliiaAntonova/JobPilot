"""Structured profile → plain text for ATS / JobBERT."""

from __future__ import annotations

import json
import re

from job_application.resume.cv_constants import (
    IMPROVEMENTS_NO_MEASURABLE_ANSWER,
    RESULT_NO_MEASURABLE_ANSWER_LEGACY,
)
from job_application.config import DESIRED_ROLE_MAX_LEN

from job_application.resume.profile_text import experience as _experience_mod
from job_application.resume.profile_text import skills as _skills_mod
from job_application.resume.profile_text import chat_answers as _chat_answers_mod


def _bind_module_names(mod) -> None:
    """Copy public and private helpers into this module namespace."""
    g = globals()
    for name, value in vars(mod).items():
        if name.startswith("__"):
            continue
        g[name] = value

_bind_module_names(_experience_mod)
_bind_module_names(_skills_mod)
_bind_module_names(_chat_answers_mod)

def structured_profile_to_plain_text(data: dict) -> str:
    """Текст резюме в формате resume.txt."""
    from job_application.resume.cv_schema import cv_to_plain_text, is_cv_structured, normalize_to_cv

    if is_cv_structured(data):
        return cv_to_plain_text(data)
    if isinstance(data, dict) and data.get("chat_format") == "cv_yml":
        return cv_to_plain_text(normalize_to_cv(data))

    pers = data.get("personal") if isinstance(data.get("personal"), dict) else {}
    name = " ".join(
        x for x in [str(pers.get("first_name") or "").strip(), str(pers.get("last_name") or "").strip()] if x
    ).strip()
    if not name:
        name = str(pers.get("full_name") or "").strip()

    lines: list[str] = []
    if name:
        lines.append(name.upper())
    lines.append("")
    lines.append("CONTACT")

    phone = str(pers.get("phone") or "").strip()
    email = str(pers.get("email") or "").strip()
    if phone:
        lines.append(f"Phone/WhatsApp: {phone}")
    if email:
        lines.append(f"E-mail: {email}")

    for label, key in (("GitHub", "github"), ("LinkedIn", "linkedin"), ("Xing", "xing")):
        val = str(pers.get(key) or "").strip()
        if val:
            lines.append(f"{label}: {val}")

    objective = str(data.get("objective") or data.get("summary") or "").strip()
    if objective:
        lines.extend(["", "OBJECTIVE", objective])

    skills_text = str(data.get("skills_text") or "").strip()
    if not skills_text:
        skills = data.get("skills")
        if isinstance(skills, list) and skills:
            skills_text = ", ".join(str(x).strip() for x in skills if str(x).strip())
    if skills_text:
        lines.extend(["", "SKILLS", "", skills_text])

    experience_text = str(data.get("experience_text") or "").strip()
    if not experience_text or data.get("_keep_stored_experience_bullets"):
        exp = data.get("experience")
        if isinstance(exp, list) and exp:
            experience_text = _experience_text_from_jobs(exp)
    if experience_text:
        lines.extend(["", "EXPERIENCE", "", experience_text])

    courses_text = str(data.get("courses_text") or "").strip()
    if not courses_text:
        courses = data.get("courses") or data.get("certifications")
        if isinstance(courses, list) and courses:
            courses_text = "\n".join(
                f"- {c}" if not str(c).strip().startswith("-") else str(c).strip() for c in courses if str(c).strip()
            )
    if courses_text:
        lines.extend(["", "COURSES", courses_text if courses_text.lstrip().startswith("-") else f"- {courses_text}"])

    education_text = str(data.get("education_text") or "").strip()
    if not education_text:
        edu = data.get("education")
        if isinstance(edu, list) and edu:
            edu_lines: list[str] = []
            for e in edu:
                if not isinstance(e, dict):
                    continue
                inst = str(e.get("institution") or "").strip()
                degree = str(e.get("degree") or "").strip()
                if inst:
                    edu_lines.append(inst)
                if degree:
                    edu_lines.append(degree)
            education_text = "\n".join(edu_lines)
    if education_text:
        lines.extend(["", "EDUCATION", education_text])

    languages_text = str(data.get("languages_text") or "").strip()
    if not languages_text:
        langs = data.get("languages")
        if isinstance(langs, list) and langs:
            languages_text = _normalize_languages_block(
                "\n".join(str(x).strip() for x in langs if str(x).strip())
            )
    if languages_text:
        lines.extend(["", "LANGUAGES", languages_text])

    interests_text = str(data.get("interests_text") or "").strip()
    if not interests_text:
        interests = data.get("interests")
        if isinstance(interests, list) and interests:
            interests_text = _lines_to_bullet_block([str(x).strip() for x in interests if str(x).strip()])
    if interests_text:
        lines.extend(["", "INTERESTS", interests_text])

    projects_text = str(data.get("projects_text") or "").strip()
    if not projects_text:
        projects = data.get("projects")
        if isinstance(projects, list) and projects:
            blocks: list[str] = []
            for item in projects:
                if isinstance(item, dict):
                    blocks.append(f"- {_format_project_heading(item)}\n  {item.get('description', '')}".strip())
                elif str(item).strip():
                    blocks.append(str(item).strip())
            projects_text = "\n\n".join(blocks)
    if projects_text:
        lines.extend(["", "PROJECTS", projects_text])

    return "\n".join(lines).strip()

