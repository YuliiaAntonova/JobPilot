"""Cover-letter LLM extractors (formerly notebook_tailoring.pipeline helpers)."""

from __future__ import annotations

import re
from typing import Any

from job_application.config import APP_LLM_MODEL
from job_application.shared.llm.client import chat_completion_tracked, complete_json_tracked

_SYSTEM = (
    "You are an expert resume and job-application assistant. "
    "Follow the user instructions precisely. "
    "Do not invent experience, skills, or metrics."
)

_USAGE_CALLS: list[dict[str, Any]] = []
_ACTIVE_MODEL: str | None = None


def configure(model: str | None) -> None:
    global _ACTIVE_MODEL
    _ACTIVE_MODEL = (model or "").strip() or None


def reset_usage() -> None:
    _USAGE_CALLS.clear()


def get_usage_calls() -> list[dict[str, Any]]:
    return list(_USAGE_CALLS)


def _model() -> str:
    return _ACTIVE_MODEL or APP_LLM_MODEL


def generate_text(prompt: str, *, call_label: str = "cover_letter") -> str:
    text, usage = chat_completion_tracked(
        _model(),
        _SYSTEM,
        prompt.strip(),
        call_label=call_label,
    )
    entry = dict(usage)
    entry["step"] = entry.get("step") or call_label
    _USAGE_CALLS.append(entry)
    return (text or "").strip()


def generate_json(prompt: str, *, call_label: str = "cover_letter_json") -> dict[str, Any]:
    data, packed = complete_json_tracked(
        _model(),
        _SYSTEM,
        prompt.strip(),
        max_retries=2,
        call_label=call_label,
    )
    for call in packed.get("calls") or []:
        _USAGE_CALLS.append(dict(call))
    if not isinstance(data, dict):
        raise ValueError("Expected a JSON object")
    return data


def flatten_skills(skills: Any) -> list[str]:
    if isinstance(skills, dict):
        flat: list[str] = []
        for val in skills.values():
            if isinstance(val, list):
                flat.extend(str(v) for v in val)
            elif isinstance(val, str):
                flat.extend(s.strip() for s in re.split(r"[,;]", val) if s.strip())
        return flat
    if isinstance(skills, str):
        return [s.strip() for s in re.split(r"[,;\n]", skills) if s.strip()]
    if isinstance(skills, list):
        return [str(x).strip() for x in skills if str(x).strip()]
    return []


def get_skill_match_score(
    resume_skills: list[str],
    job_skills: list[str],
) -> tuple[float, list[str], list[str]]:
    resume_skills_norm = [re.sub(r"[^\w\s]", "", skill.lower()) for skill in resume_skills]
    job_skills_norm = [re.sub(r"[^\w\s]", "", skill.lower()) for skill in job_skills]

    matched_skills: list[str] = []
    for i, job_skill in enumerate(job_skills):
        job_skill_norm = job_skills_norm[i]
        if any(
            job_skill_norm == resume_skill
            or job_skill_norm in resume_skill
            or resume_skill in job_skill_norm
            for resume_skill in resume_skills_norm
        ):
            matched_skills.append(job_skill)

    missing_skills = [skill for skill in job_skills if skill not in matched_skills]
    match_score = (len(matched_skills) / len(job_skills) * 100) if job_skills else 0.0
    return match_score, matched_skills, missing_skills


def parse_job_description(job_desc_text: str) -> dict[str, Any]:
    prompt = f"""
        Please analyze the following job description and extract key information in a structured JSON format.
        Include these fields:
        - job_title
        - company_name
        - required_skills (as a list)
        - preferred_skills (as a list)
        - experience_requirements
        - education_requirements
        - company_values
        - responsibilities (as a list)

        Job Description:
        {job_desc_text}

        Return only the JSON.
        """
    try:
        return generate_json(prompt, call_label="parse_job_description")
    except Exception as e:
        print(f"Error parsing job description: {e}")
        return {
            "job_title": "",
            "company_name": "",
            "required_skills": [],
            "preferred_skills": [],
            "experience_requirements": "",
            "education_requirements": "",
            "company_values": "",
            "responsibilities": [],
        }


def parse_resume(resume_text: str) -> dict[str, Any]:
    prompt = f"""
        Please analyze the following resume and extract key information in a structured JSON format.
        Include these fields:
        - name
        - contact_info
        - education (as a list of objects with school, degree, year)
        - work_experience (as a list of objects with company, title, duration, achievements)
        - skills (as a list)
        - certifications (as a list)
        - projects (as a list of objects with title, description)

        Resume:
        {resume_text}

        Return only the JSON.
        """
    try:
        return generate_json(prompt, call_label="parse_resume")
    except Exception as e:
        print(f"Error parsing resume: {e}")
        return {
            "name": "",
            "contact_info": {},
            "education": [],
            "work_experience": [],
            "skills": [],
            "certifications": [],
            "projects": [],
        }


def _strip_cover_letter_placeholders(text: str) -> str:
    lines = (text or "").splitlines()
    cleaned: list[str] = []
    placeholder_re = re.compile(
        r"^\s*("
        r"\[.*?\]"
        r"|Your Name|Your Address|Your Email|Your Phone(?: Number)?"
        r"|City,\s*State,\s*Zip"
        r")\s*$",
        re.IGNORECASE,
    )
    for line in lines:
        if placeholder_re.match(line.strip()):
            continue
        cleaned.append(line)
    dear_idx = next(
        (i for i, line in enumerate(cleaned) if re.match(r"^\s*Dear\b", line, re.I)),
        None,
    )
    if dear_idx is not None and dear_idx > 0:
        cleaned = cleaned[dear_idx:]
    while cleaned and not cleaned[0].strip():
        cleaned.pop(0)
    return "\n".join(cleaned).strip()


def generate_cover_letter(
    resume_info: dict[str, Any],
    job_info: dict[str, Any],
    match_score: float,
    matched_skills: list[str],
) -> str:
    del match_score
    name = str(resume_info.get("name") or "").strip() or "Candidate"
    company = str(job_info.get("company_name") or "").strip() or "the company"
    job_title = str(job_info.get("job_title") or "").strip() or "the position"

    recent_experience = ""
    if isinstance(resume_info.get("work_experience"), list) and resume_info["work_experience"]:
        recent_experience = resume_info["work_experience"][0]

    highlight_skills = matched_skills[:5]
    values = str(job_info.get("company_values") or "").strip()
    prompt = f"""
Write a short, ready-to-send cover letter for {name} applying to "{job_title}" at {company}.

Required structure (nothing else):
1) Greeting line only, e.g. "Dear Hiring Manager," (or a named contact if known)
2) 3–4 short body paragraphs
3) Closing: "Sincerely," then the real candidate name on the next line: {name}

Content guidelines:
- Open with enthusiasm for this specific role and {company}
- Highlight these skills when relevant: {', '.join(highlight_skills) or 'skills from the resume'}
- Weave in this recent experience (facts only, do not invent): {recent_experience}
- Optionally reflect alignment with: {values or 'the company mission'}
- End with a brief thank-you and willingness to talk

Hard constraints:
- MAXIMALLY SIMPLE: no letterhead, no address block, no date line, no phone/email header
- NEVER invent or print placeholders such as [Your Name], [Your Address], [City, State, Zip],
  [Your Email], [Your Phone Number], [Date], or any other square-bracket fields
- Do not invent employers, metrics, titles, or contact details that are not given above
- Professional tone, about 220–280 words
- Return ONLY the cover letter text — no commentary, no markdown fences
"""
    try:
        raw = generate_text(prompt, call_label="cover_letter")
        return _strip_cover_letter_placeholders(raw)
    except Exception as e:
        print(f"[Error] Generating cover letter: {e}")
        return "Error generating cover letter. Please try again."
