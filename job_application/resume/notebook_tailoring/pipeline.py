"""End-to-end tailoring pipeline (Untitled.ipynb)."""

from __future__ import annotations

import json
import re
from typing import Any

from job_application.resume.notebook_tailoring import json_parse
from job_application.resume.notebook_tailoring import llm


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
        return llm.generate_json(prompt, call_label="parse_job_description")
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
        return llm.generate_json(prompt, call_label="parse_resume")
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


def tailor_resume_section(
    section_name: str,
    section_content: Any,
    job_info: dict[str, Any],
) -> Any:
    few_shot_examples = """
    Example 1:
    Original: "Managed a team of 5 developers building a React application"
    Job requires: "Team leadership and React.js development"
    Tailored: "Led a team of 5 developers building a React.js
    application, coordinating technical delivery"

    Example 2:
    Original skills: ["Python", "SQL", "Data Analysis"]
    Job requires: "Python, SQL, and NLP"
    Tailored skills: ["Python", "SQL", "Data Analysis"]
    Do not add NLP without evidence of NLP experience.

    Example 3:
    Original: "Built a web scraper using Beautiful Soup"
    Job requires: "Data collection and analysis"
    Tailored: "Developed a web scraping solution using
    Beautiful Soup for structured data collection"
    """

    if isinstance(section_content, (list, dict)):
        section_string = json.dumps(section_content, indent=2, ensure_ascii=False)
    else:
        section_string = str(section_content)

    job_reqs = f"""
    Job Title: {job_info.get('job_title', '')}
    Company: {job_info.get('company_name', '')}
    Required Skills: {json.dumps(job_info.get('required_skills', []))}
    Preferred Skills: {json.dumps(job_info.get('preferred_skills', []))}
    Responsibilities: {json.dumps(job_info.get('responsibilities', []))}
    """

    is_json = isinstance(section_content, (list, dict))
    if is_json:
        if isinstance(section_content, list):
            output_instruction = (
                "Return ONLY a valid JSON array (same element types as the original). "
                "No markdown fences, no commentary."
            )
        else:
            output_instruction = (
                "Return ONLY a valid JSON object with the same keys and structure "
                "as the original. No markdown fences, no commentary."
            )
    else:
        output_instruction = "Return ONLY the tailored plain text."

    prompt = f"""
    You are an expert resume optimization assistant.

    Examples:
    {few_shot_examples}

    Tailor the following resume section to match the job.

    Section: {section_name}

    Job Requirements:
    {job_reqs}

    Original Resume Section:
    {section_string}

    Instructions:
    1. Highlight relevant existing experience.
    2. Use keywords when factually supported.
    3. Keep all information accurate.
    4. Do not invent experience, skills, or metrics.
    5. Preserve the original data structure.
    6. Improve clarity and professional wording.
    7. Preserve names, dates, companies, and degrees.

    {output_instruction}
    """

    try:
        tailored_content = llm.generate_text(prompt, call_label=f"tailor_{section_name}")
        if is_json:
            try:
                return json_parse.parse_llm_json_value(
                    tailored_content, section_content, section_name=section_name
                )
            except ValueError:
                retry_prompt = (
                    f"{prompt}\n\n"
                    "Your previous answer was not valid JSON. "
                    "Reply again with ONLY valid JSON and nothing else."
                )
                tailored_content = llm.generate_text(
                    retry_prompt, call_label=f"tailor_{section_name}_retry"
                )
                return json_parse.parse_llm_json_value(
                    tailored_content, section_content, section_name=section_name
                )
        return tailored_content
    except Exception as e:
        print(f"[Warning] Tailoring section '{section_name}' failed ({e}). Using original.")
        return section_content


def tailor_headline_and_summary(
    headline: str,
    summary: str,
    job_info: dict[str, Any],
) -> tuple[str, str]:
    """
    Align headline (target role) and summary with the job posting without inventing facts.
    """
    job_title = str(job_info.get("job_title") or "").strip()
    company = str(job_info.get("company_name") or "").strip()
    prompt = f"""
    Tailor the resume headline and summary for this job application.

    Job title from posting: {job_title}
    Company: {company}
    Required skills: {json.dumps(job_info.get("required_skills") or [])}
    Responsibilities: {json.dumps(job_info.get("responsibilities") or [])}

    Current headline: {headline}
    Current summary: {summary}

    Rules:
    1. Headline must reflect the target role from the job (e.g. "Data Engineer" for a Data Engineer posting).
    2. Keep headline concise (max ~90 characters); you may add 1–3 factual specialty keywords already supported by the summary.
    3. Do NOT invent employers, years of experience, or tools not supported by the current summary/headline.
    4. Summary: rephrase for ATS alignment with the job; keep all factual claims; do not add new technologies.

    Return ONLY JSON: {{"headline": "...", "summary": "..."}}
    """
    try:
        data = llm.generate_json(prompt, call_label="tailor_headline_summary")
        new_headline = str(data.get("headline") or headline).strip() or headline
        new_summary = str(data.get("summary") or summary).strip() or summary
        return new_headline, new_summary
    except Exception as e:
        print(f"[Warning] Headline/summary tailoring failed ({e}). Using originals.")
        if job_title and job_title.lower() not in (headline or "").lower():
            return job_title, summary
        return headline, summary


def _strip_cover_letter_placeholders(text: str) -> str:
    """Remove letterhead / bracket placeholders the model sometimes invents."""
    lines = (text or "").splitlines()
    cleaned: list[str] = []
    placeholder_re = re.compile(
        r"^\s*("
        r"\[.*?\]"  # [Your Name], [Date], …
        r"|Your Name|Your Address|Your Email|Your Phone(?: Number)?"
        r"|City,\s*State,\s*Zip"
        r")\s*$",
        re.IGNORECASE,
    )
    for line in lines:
        if placeholder_re.match(line.strip()):
            continue
        cleaned.append(line)
    # Start at the greeting — drop leftover "Hiring Manager / Company" letterhead
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
    del match_score  # used by callers for UI; not needed in the letter body
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
        raw = llm.generate_text(prompt, call_label="cover_letter")
        return _strip_cover_letter_placeholders(raw)
    except Exception as e:
        print(f"[Error] Generating cover letter: {e}")
        return "Error generating cover letter. Please try again."


def generate_optimization_report(
    resume_info: dict[str, Any],
    job_info: dict[str, Any],
    match_score: float,
    matched_skills: list[str],
    missing_skills: list[str],
) -> dict[str, Any]:
    prompt = f"""
    Analyze the alignment between this resume and job description and generate a structured optimization report.

    Resume Summary:
    {json.dumps(resume_info, indent=2)}

    Job Description:
    {json.dumps(job_info, indent=2)}

    Match Score: {match_score:.1f}%
    Matched Skills: {matched_skills}
    Missing Skills: {missing_skills}

    Please return a valid JSON object with the following fields:
    {{
      "overall_score": <number between 0 and 100>,
      "section_scores": {{
        "experience": <0–100>,
        "skills": <0–100>,
        "education": <0–100>
      }},
      "key_strengths": [<top 3 matching aspects>],
      "improvement_areas": [<3 specific and actionable suggestions>],
      "keyword_recommendations": [<relevant keywords to add>]
    }}
    """
    try:
        return llm.generate_json(prompt, call_label="optimization_report")
    except Exception as e:
        print(f"[Error] Failed to generate optimization report: {e}")
        return {
            "overall_score": round(match_score),
            "section_scores": {"experience": 50, "skills": 40, "education": 60},
            "key_strengths": matched_skills[:3]
            if matched_skills
            else ["Relevant skills match", "Basic qualification met", "Industry-aligned role"],
            "improvement_areas": [
                f"Add missing skills: {', '.join(missing_skills[:3])}",
                "Include quantifiable outcomes in experience section",
                "Tailor summary section with job-relevant keywords",
            ],
            "keyword_recommendations": missing_skills[:5],
        }


def tailor_resume(
    resume_text: str,
    job_desc_text: str,
    *,
    model: str | None = None,
    include_cover_letter: bool = True,
    include_optimization_report: bool = True,
    verbose: bool = False,
) -> dict[str, Any]:
    llm.configure(model)
    llm.reset_usage()

    if verbose:
        print("Step 1: Parsing resume and job description...")
    resume_info = parse_resume(resume_text)
    job_info = parse_job_description(job_desc_text)

    if verbose:
        print("Step 2: Calculating skill match score...")
    job_skills = list(job_info.get("required_skills") or []) + list(
        job_info.get("preferred_skills") or []
    )
    resume_skills = flatten_skills(resume_info.get("skills") or [])
    initial_score, matched_skills, missing_skills = get_skill_match_score(
        resume_skills, job_skills
    )
    if verbose:
        print(f"Initial Match Score: {initial_score:.1f}%")

    if verbose:
        print("Step 3: Tailoring resume sections...")
    tailored = dict(resume_info)
    for section in ("work_experience", "skills", "education", "projects"):
        if section not in tailored or tailored[section] in (None, "", []):
            continue
        if verbose:
            print(f"  - Tailoring section: {section}")
        tailored[section] = tailor_resume_section(section, tailored[section], job_info)

    cover_letter = ""
    if include_cover_letter:
        if verbose:
            print("Step 4: Generating tailored cover letter...")
        cover_letter = generate_cover_letter(
            tailored, job_info, initial_score, matched_skills
        )

    optimization_report: dict[str, Any] = {}
    if include_optimization_report:
        if verbose:
            print("Step 5: Generating optimization report...")
        optimization_report = generate_optimization_report(
            tailored, job_info, initial_score, matched_skills, missing_skills
        )

    if verbose:
        print("Step 6: Recalculating match score after tailoring...")
    final_skills = flatten_skills(tailored.get("skills") or [])
    final_score, _, _ = get_skill_match_score(final_skills, job_skills)
    if verbose:
        delta = final_score - initial_score
        print(f"Final Match Score: {final_score:.1f}% (Improved by {delta:.1f}%)")

    calls = llm.get_usage_calls()
    total = {
        "prompt_tokens": sum(int(c.get("prompt_tokens") or 0) for c in calls),
        "completion_tokens": sum(int(c.get("completion_tokens") or 0) for c in calls),
        "total_tokens": sum(int(c.get("total_tokens") or 0) for c in calls),
    }

    return {
        "resume": tailored,
        "cover_letter": cover_letter,
        "optimization_report": optimization_report,
        "initial_match_score": initial_score,
        "final_match_score": final_score,
        "matched_skills": matched_skills,
        "missing_skills": missing_skills,
        "job_info": job_info,
        "resume_info_parsed": resume_info,
        "llm_calls": calls,
        "token_usage": total,
        "token_totals": total,
    }
