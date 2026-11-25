"""Chat answers ↔ structured CV conversion and desired-role helpers."""

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


def _bind_module_names(mod) -> None:
    """Copy public and private helpers into this module namespace."""
    g = globals()
    for name, value in vars(mod).items():
        if name.startswith("__"):
            continue
        g[name] = value

_bind_module_names(_experience_mod)
_bind_module_names(_skills_mod)

def clamp_desired_role(text: str, max_len: int | None = None) -> str:
    """Fit desired role into DB column (resume_profiles.desired_role VARCHAR)."""
    limit = DESIRED_ROLE_MAX_LEN if max_len is None else max_len
    cleaned = re.sub(r"\s+", " ", str(text or "").strip())
    if not cleaned or len(cleaned) <= limit:
        return cleaned
    cut = cleaned[:limit]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip(".,;:- ")


def _first_sentence(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(text or "").strip())
    if not cleaned:
        return ""
    match = re.match(r"^(.{1,500}?[.!?])(?:\s|$)", cleaned)
    if match:
        return match.group(1).strip()
    return cleaned


_SECTION_HEADER_RE = re.compile(
    r"^(professional summary|summary|experience|work experience|education|skills|certifications|languages|projects)\b",
    re.IGNORECASE,
)


_HEADLINE_ROLE_WORDS = (
    "engineer",
    "developer",
    "analyst",
    "manager",
    "architect",
    "qa",
    "tester",
    "consultant",
    "specialist",
    "lead",
    "director",
    "designer",
    "administrator",
)


def _looks_like_resume_headline(line: str) -> bool:
    text = str(line or "").strip()
    if not text or len(text) > 160:
        return False
    low = text.lower()
    if _SECTION_HEADER_RE.match(text):
        return False
    if _looks_like_contact_line(text):
        return False
    if low.startswith(("email", "phone", "linkedin", "github", "xing", "website", "portfolio")):
        return False
    if "|" in text:
        return True
    letters = [c for c in text if c.isalpha()]
    if letters:
        upper_ratio = sum(1 for c in letters if c.isupper()) / len(letters)
        if upper_ratio > 0.55 and len(text) <= 90:
            return True
    if any(word in low for word in _HEADLINE_ROLE_WORDS):
        return True
    return False


def _extract_headline_from_plain_text(text: str) -> str:
    lines = [ln for ln in _split_lines(text) if ln.strip()]
    if len(lines) < 2:
        return ""
    for line in lines[1:8]:
        if _looks_like_resume_headline(line):
            return line.strip()
    return ""


def resolve_desired_role(
    structured: dict,
    *,
    desired_role: str | None = None,
    plain_text: str = "",
) -> str:
    """Short job title for desired_role — never the full professional summary."""
    roles = structured.get("desired_roles")
    if isinstance(roles, list) and roles:
        candidate = str(roles[0]).strip()
        if candidate:
            return clamp_desired_role(candidate)

    for key in ("objective",):
        candidate = str(structured.get(key) or "").strip()
        if candidate:
            return clamp_desired_role(candidate)

    headline = _extract_headline_from_plain_text(plain_text)
    if headline:
        return clamp_desired_role(headline)

    plain_supp = _extract_supplementary_from_plain_text(plain_text) if plain_text else {}
    candidate = str(plain_supp.get("desiredPosition") or "").strip()
    if candidate:
        return clamp_desired_role(candidate)

    summary = str(structured.get("summary") or "").strip()
    if summary:
        return clamp_desired_role(_first_sentence(summary))

    return clamp_desired_role(str(desired_role or ""))


def structured_to_chat_answers(structured: dict, *, desired_role: str | None = None) -> dict[str, str]:
    """Structured JSON (cv.yml in DB) → flat chat answers for the editor."""
    from job_application.resume.cv_schema import cv_to_chat_answers, normalize_to_cv

    if not isinstance(structured, dict):
        return {}

    answers = cv_to_chat_answers(normalize_to_cv(structured))
    if desired_role and not answers.get("headline"):
        answers["headline"] = str(desired_role).strip()
    return answers


def _legacy_structured_to_chat_answers_unused(structured: dict, *, desired_role: str | None = None) -> dict[str, str]:
    p = structured.get("personal") if isinstance(structured.get("personal"), dict) else {}
    full_name = " ".join(
        x for x in [str(p.get("first_name") or "").strip(), str(p.get("last_name") or "").strip()] if x
    ).strip() or str(p.get("full_name") or "").strip()

    portfolio = str(p.get("portfolio") or "").strip()
    urls = p.get("portfolio_urls")
    if not portfolio and isinstance(urls, list):
        for url in urls:
            text = str(url).strip()
            if text:
                portfolio = text
                break

    plain_text = str(structured.get("_resume_plain_text") or "").strip()
    if not portfolio and plain_text:
        portfolio = _extract_portfolio_from_plain_text(plain_text)
    plain_supp = _extract_supplementary_from_plain_text(plain_text) if plain_text else {}
    plain_skills = _extract_skills_from_plain_text(plain_text) if plain_text else {}
    plain_contact = _extract_contact_from_plain_text(plain_text) if plain_text else {}

    if portfolio:
        links, parsed = _merge_social_links(portfolio, p.get("linkedin"), p.get("github"))
    else:
        links, parsed = _merge_social_links(
            p.get("linkedin"),
            p.get("github"),
            plain_contact.get("linkedin"),
            plain_contact.get("github"),
        )
    linkedin = parsed["linkedin"]
    github = parsed["github"]

    desired_positions = resolve_desired_role(
        structured,
        desired_role=desired_role,
        plain_text=plain_text,
    )

    languages_text = str(structured.get("languages_text") or "").strip() or _language_lines(structured.get("languages"))
    education_text = str(structured.get("education_text") or "").strip() or _education_text_from_structured(
        structured.get("education")
    )
    certificates_text = str(structured.get("courses_text") or "").strip() or _certificates_text_from_structured(
        structured.get("certifications") or structured.get("courses")
    )
    skills_text = str(structured.get("skills_text") or "").strip() or _tech_stack_from_structured(structured)
    main_tech_stack = ""
    raw_stack = structured.get("main_tech_stack") or structured.get("skills")
    if isinstance(raw_stack, list):
        main_tech_stack = ", ".join(str(x).strip() for x in raw_stack if str(x).strip())
    elif isinstance(raw_stack, str):
        main_tech_stack = raw_stack.strip()

    if not languages_text and plain_supp.get("languages"):
        languages_text = plain_supp["languages"]
    if plain_text:
        education_text = _prefer_plain_supplementary(education_text, plain_supp.get("education", ""))
        languages_text = _prefer_plain_supplementary(languages_text, plain_supp.get("languages", ""))
        certificates_text = _prefer_plain_supplementary(certificates_text, plain_supp.get("courses", ""))
        skills_text = _prefer_plain_supplementary(skills_text, plain_skills.get("skills", ""))
        main_tech_stack = _prefer_plain_supplementary(main_tech_stack, plain_skills.get("mainTechStack", ""))
    elif not education_text and plain_supp.get("education"):
        education_text = plain_supp["education"]
    if not certificates_text and plain_supp.get("courses"):
        certificates_text = plain_supp["courses"]
    if not skills_text and plain_skills.get("skills"):
        skills_text = plain_skills["skills"]
    if not main_tech_stack and plain_skills.get("mainTechStack"):
        main_tech_stack = plain_skills["mainTechStack"]
    if skills_text:
        skills_text = format_skills_text_for_chat(skills_text)

    interests_text = str(structured.get("interests_text") or "").strip()
    if plain_text:
        interests_text = _prefer_plain_supplementary(interests_text, plain_supp.get("interests", ""))
    elif not interests_text and plain_supp.get("interests"):
        interests_text = plain_supp["interests"]

    projects_text = str(structured.get("projects_text") or "").strip()
    if plain_text:
        projects_text = _prefer_plain_supplementary(projects_text, plain_supp.get("projects", ""))
    elif not projects_text and plain_supp.get("projects"):
        projects_text = plain_supp["projects"]

    location = _sanitize_contact_location(
        str(p.get("location") or p.get("city") or "").strip() or plain_contact.get("location", "")
    )

    answers: dict[str, str] = {
        "fullName": full_name,
        "city": location,
        "phone": str(p.get("phone") or "").strip() or plain_contact.get("phone", ""),
        "email": str(p.get("email") or "").strip() or plain_contact.get("email", ""),
        "links": links,
        "linkedin": linkedin or plain_contact.get("linkedin", ""),
        "github": github or plain_contact.get("github", ""),
        "desiredPosition": desired_positions,
        "skills": skills_text,
        "mainTechStack": main_tech_stack,
        "languages": languages_text,
        "education": education_text,
        "courses": certificates_text,
        "interests": interests_text,
        "projects": projects_text,
    }
    summary_text = str(structured.get("summary") or "").strip()
    if summary_text:
        answers["summary"] = summary_text

    jobs = _experience_entries_from_structured(structured)
    if isinstance(jobs, list) and jobs:
        for idx, job in enumerate(jobs):
            prefix = f"job_{idx}_"
            dates_raw = str(job.get("dates") or "").strip()
            if not dates_raw:
                dates_raw = " — ".join(
                    x for x in (str(job.get("start_date") or "").strip(), str(job.get("end_date") or "").strip()) if x
                )

            position = str(job.get("position") or job.get("title") or "").strip()
            company = _normalize_company_label(str(job.get("company") or "").strip())
            position, parsed_company = _split_merged_position_company(position, company)
            if not company and parsed_company:
                company = parsed_company
            role_and_dates = ", ".join(x for x in (position, dates_raw) if x)

            description = _job_description_for_chat(job)

            result = ""
            for field in ("improvements", "achievements"):
                val = job.get(field)
                if isinstance(val, list) and val:
                    result = "\n".join(str(x) for x in val if str(x).strip())
                    break
                if isinstance(val, str) and val.strip():
                    result = val.strip()
                    break

            technologies = job.get("technologies")
            if isinstance(technologies, list):
                tech_text = ", ".join(str(x).strip() for x in technologies if str(x).strip())
            else:
                tech_text = str(technologies or "").strip()

            answers.update(
                {
                    f"{prefix}company": company or str(job.get("company") or "").strip(),
                    f"{prefix}roleAndDates": role_and_dates,
                    f"{prefix}description": description,
                    f"{prefix}raw_description": description,
                    f"{prefix}result": result,
                }
            )
            if tech_text:
                answers[f"{prefix}technologies"] = tech_text
                answers[f"{prefix}needs_tech_fallback"] = "0"
            elif description:
                answers[f"{prefix}needs_tech_fallback"] = "1"

            responsibilities = job.get("responsibilities")
            if isinstance(responsibilities, list) and responsibilities:
                answers[f"{prefix}responsibilities_json"] = json.dumps(
                    [str(x).strip() for x in responsibilities if str(x).strip()],
                    ensure_ascii=False,
                )

    global_tech = str(answers.get("mainTechStack") or answers.get("skills") or "").strip()
    if global_tech:
        for key in list(answers.keys()):
            if key.endswith("_needs_tech_fallback") and not answers.get(key.replace("needs_tech_fallback", "technologies")):
                answers[key] = "0"

    return {k: v for k, v in expand_skill_fields_in_answers(answers).items() if str(v).strip()}


def chat_answers_to_structured(answers: dict[str, str]) -> dict:
    """Преобразует ответы чат-мастера в structured JSON (cv.yml schema in DB)."""
    from job_application.config import RESUME_PLAIN_TEXT_KEY
    from job_application.resume.cv_schema import chat_answers_to_cv

    a = expand_skill_fields_in_answers(_legacy_answers(answers))
    merged_skills = merge_skill_fields_from_answers(a)
    if merged_skills:
        a["skills"] = format_skills_text_for_chat(merged_skills)

    if _is_career_interview_answers(a):
        cv = chat_answers_to_cv(a)
        pdf_plain = str(a.get(RESUME_PLAIN_TEXT_KEY) or "").strip()
        if pdf_plain:
            cv[RESUME_PLAIN_TEXT_KEY] = pdf_plain
        return cv

    full_name = str(a.get("fullName") or a.get("name") or "").strip()
    parts = full_name.split()
    first_name = parts[0] if parts else ""
    last_name = " ".join(parts[1:]).strip() if len(parts) > 1 else ""

    contact_links = _parse_contact_links(str(a.get("contactLinks") or ""))
    objective = str(a.get("objective") or "").strip()
    skills_text = str(a.get("skills") or "").strip()
    experience_text = str(a.get("experience") or "").strip()
    courses_text = str(a.get("courses") or "").strip()
    education_text = str(a.get("education") or "").strip()
    interests_text = str(a.get("interests") or "").strip()
    projects_text = str(a.get("projects") or "").strip()
    languages_text = _normalize_languages_block(str(a.get("languages") or ""))

    experience = _parse_experience_block(experience_text) if experience_text else []
    courses = _parse_courses(courses_text)

    skills_list = [
        s.strip()
        for s in re.split(r"[,;\n]", skills_text)
        if s.strip() and len(s.strip()) < 80 and not s.strip().lower().startswith("tools")
    ][:24]

    return {
        "personal": {
            "full_name": full_name,
            "first_name": first_name,
            "last_name": last_name,
            "email": str(a.get("email") or "").strip(),
            "phone": str(a.get("phone") or "").strip(),
            "location": _sanitize_contact_location(str(a.get("city") or "")),
            "github": contact_links.get("github", ""),
            "linkedin": contact_links.get("linkedin", ""),
            "xing": contact_links.get("xing", ""),
        },
        "objective": objective,
        "summary": objective,
        "skills_text": skills_text,
        "skills": skills_list,
        "experience_text": experience_text,
        "experience": experience,
        "courses_text": courses_text,
        "courses": courses,
        "certifications": courses,
        "education_text": education_text,
        "education": _education_entries_from_chat_or_structured(education_text, []),
        "languages_text": languages_text,
        "languages": [ln.lstrip("- ").strip() for ln in languages_text.splitlines() if ln.strip()],
        "interests_text": interests_text,
        "interests": [ln.lstrip("- ").strip() for ln in interests_text.splitlines() if ln.strip()],
        "projects_text": projects_text,
        "projects": _parse_projects_chat_text(projects_text),
    }

