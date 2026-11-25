"""Profile text helpers (split from monolithic profile_text.py)."""

from __future__ import annotations

import importlib
from typing import Any

from job_application.resume.profile_text.chat_answers import (
    chat_answers_to_structured,
    clamp_desired_role,
    resolve_desired_role,
    structured_to_chat_answers,
)
from job_application.resume.profile_text.experience import (
    build_contact_line,
    enrich_structured_personal_from_plain,
)
from job_application.resume.profile_text.plain_text import structured_profile_to_plain_text
from job_application.resume.profile_text.skills import (
    categorize_skill_chips,
    chips_from_skills_text,
    expand_skill_fields_in_answers,
    extract_skills_education_text,
    extract_skills_experience_text,
    extract_skills_text_for_jobbert,
    format_skills_text_for_chat,
    merge_skill_fields_from_answers,
    parse_skills_text_to_fields,
    skills_from_plain_resume_text,
    skills_lines_for_render,
    skills_text_is_categorized,
    structured_skills_list,
)

_SUBMODULES = (
    "job_application.resume.profile_text.experience",
    "job_application.resume.profile_text.skills",
    "job_application.resume.profile_text.chat_answers",
    "job_application.resume.profile_text.plain_text",
)


def __getattr__(name: str) -> Any:
    """Resolve private helpers still imported as profile_text._name."""
    for mod_name in _SUBMODULES:
        mod = importlib.import_module(mod_name)
        if hasattr(mod, name):
            value = getattr(mod, name)
            globals()[name] = value
            return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "build_contact_line",
    "categorize_skill_chips",
    "chat_answers_to_structured",
    "chips_from_skills_text",
    "clamp_desired_role",
    "enrich_structured_personal_from_plain",
    "expand_skill_fields_in_answers",
    "extract_skills_education_text",
    "extract_skills_experience_text",
    "extract_skills_text_for_jobbert",
    "format_skills_text_for_chat",
    "merge_skill_fields_from_answers",
    "parse_skills_text_to_fields",
    "resolve_desired_role",
    "skills_from_plain_resume_text",
    "skills_lines_for_render",
    "skills_text_is_categorized",
    "structured_profile_to_plain_text",
    "structured_skills_list",
    "structured_to_chat_answers",
]
