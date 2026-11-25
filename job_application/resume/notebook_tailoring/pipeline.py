"""End-to-end tailoring pipeline (Untitled.ipynb) — legacy TAILORING_PIPELINE=notebook."""

from __future__ import annotations

import json
from typing import Any

from job_application.cover_letter.extract import (
    flatten_skills,
    generate_cover_letter,
    get_skill_match_score,
)
from job_application.resume.notebook_tailoring import json_parse
from job_application.resume.notebook_tailoring import llm


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
