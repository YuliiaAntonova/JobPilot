"""L7 job application crew — agents/tasks copied 1:1 from L7_job_application_crew.ipynb."""

from __future__ import annotations

import logging
from pathlib import Path

from crewai import Agent, Crew, Task

logger = logging.getLogger("job_application.crew_tailoring")


def build_job_application_crew(
    *,
    output_file: str | Path | None = None,
    verbose: bool = False,
) -> tuple[Crew, Task]:
    """
    Build Researcher → Profiler → Resume Strategist crew.

    Interview Preparer stays disabled (as in L7 notebook).
    Returns (crew, resume_strategy_task) so callers can read task output / file.
    """
    out = str(output_file) if output_file else None

    # Agent 1: Researcher
    researcher = Agent(
        role="Tech Job Researcher",
        goal="Make sure to do amazing analysis on "
        "job posting to help job applicants",
        tools=[],  # job text via {job_posting_text}
        allow_delegation=False,
        max_iter=3,
        verbose=verbose,
        backstory=(
            "As a Job Researcher, your prowess in "
            "navigating and extracting critical "
            "information from job postings is unmatched."
            "Your skills help pinpoint the necessary "
            "qualifications and skills sought "
            "by employers, forming the foundation for "
            "effective application tailoring."
        ),
    )

    # Agent 2: Profiler
    profiler = Agent(
        role="Personal Profiler for Engineers",
        goal="Do increditble research on job applicants "
        "to help them stand out in the job market",
        tools=[],  # resume via {resume_text} only
        allow_delegation=False,
        max_iter=3,
        verbose=verbose,
        backstory=(
            "Equipped with analytical prowess, you dissect "
            "and synthesize information "
            "from diverse sources to craft comprehensive "
            "personal and professional profiles, laying the "
            "groundwork for personalized resume enhancements."
        ),
    )

    # Agent 3: Resume Strategist
    resume_strategist = Agent(
        role="Resume Strategist for Engineers",
        goal="Find all the best ways to make a "
        "resume stand out in the job market.",
        tools=[],  # use context from research + profile only
        allow_delegation=False,
        max_iter=3,
        verbose=verbose,
        backstory=(
            "With a strategic mind and an eye for detail, you "
            "excel at refining resumes to highlight the most "
            "relevant skills and experiences, ensuring they "
            "resonate perfectly with the job's requirements."
        ),
    )

    # Agent 4: Interview Preparer — temporarily disabled
    # interview_preparer = Agent(...)

    research_task = Task(
        description=(
            "Analyze the prepared job posting text below. Extract key skills, "
            "experiences, and qualifications required. Do NOT search the web — "
            "use only this text.\n\n"
            "JOB POSTING TEXT:\n{job_posting_text}"
        ),
        expected_output=(
            "A structured list of job requirements, including necessary "
            "skills, qualifications, and experiences."
        ),
        agent=researcher,
        async_execution=True,
    )

    profile_task = Task(
        description=(
            "Compile a detailed personal and professional profile from the "
            "personal write-up and resume text below only. Do NOT browse GitHub "
            "or the web — projects and skills are already in the resume.\n\n"
            "PERSONAL WRITE-UP:\n{personal_writeup}\n\n"
            "RESUME TEXT:\n{resume_text}"
        ),
        expected_output=(
            "A comprehensive profile document that includes skills, "
            "project experiences, contributions, interests, and "
            "communication style."
        ),
        agent=profiler,
        async_execution=True,
    )

    resume_strategy_kwargs: dict = {
        "description": (
            "Using ONLY the profile and job requirements from previous tasks "
            "(provided as context), write a tailored RESUME (not a profile "
            "essay). Do not invent facts. Do not call tools. Update summary, "
            "work experience, skills, and education for the job posting.\n\n"
            "TARGET COMPANY (exact spelling in the Objective): {company_name}\n"
            "TARGET ROLE (exact title in the Objective — do NOT invent a "
            "different title from the JD): {job_title}\n"
            "If a target says 'extract from job posting', take it from the job "
            "requirements; otherwise copy TARGET ROLE / COMPANY 1:1.\n\n"
            "FORMAT RULES:\n"
            "- First line: '# <Candidate Full Name>' ONLY — never append "
            "'Comprehensive Personal and Professional Profile' or similar.\n"
            "- Under the name: optional short headline = TARGET ROLE only "
            "(or omit). Never use profiler/document titles as the headline.\n"
            "- Then contact line + Markdown links for Xing / GitHub / LinkedIn "
            "with the SAME https URLs as in RESUME TEXT (do not drop GitHub).\n"
            "- Then a short first-person Objective: 'To obtain a <TARGET ROLE> "
            "position at <TARGET COMPANY>, …'. NEVER write '[Company Name]', "
            "'[Job Title]', or invent a role name that differs from TARGET ROLE.\n"
            "- Do not append commentary like 'This updated resume effectively…'."
        ),
        "expected_output": (
            "A complete tailored resume in Markdown: name heading, contact "
            "links with real https URLs, Objective, skills, experience, "
            "education. No profile-document title and no closing commentary."
        ),
        "context": [research_task, profile_task],
        "agent": resume_strategist,
    }
    if out:
        resume_strategy_kwargs["output_file"] = out

    resume_strategy_task = Task(**resume_strategy_kwargs)

    # interview_preparation_task — temporarily disabled

    crew = Crew(
        agents=[researcher, profiler, resume_strategist],
        tasks=[research_task, profile_task, resume_strategy_task],
        verbose=verbose,
    )
    if verbose:
        logger.info("Built L7 job_application_crew (3 agents, interview preparer off)")
    return crew, resume_strategy_task
