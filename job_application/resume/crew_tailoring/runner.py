"""Kickoff wrapper: in-memory strings → tailored Markdown → CV JSON."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any

from job_application.config import JOB_APP_CREW_VERBOSE
from job_application.resume.crew_tailoring.crew import build_job_application_crew
from job_application.resume.crew_tailoring.md_to_cv_json import (
    l7_json_to_slim_cv,
    markdown_to_cv_json,
)
from job_application.resume.crew_tailoring.run_usage import (
    crew_usage_to_calls,
    print_crew_usage_summary,
)
from job_application.resume.crew_tailoring.utils import get_openai_model_name
from job_application.resume.cv_schema import normalize_to_cv

logger = logging.getLogger("job_application.crew_tailoring")


def _task_output_text(task: Any, result: Any) -> str:
    for attr in ("output", "result"):
        val = getattr(task, attr, None)
        if val is None:
            continue
        raw = getattr(val, "raw", None)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
        if isinstance(val, str) and val.strip():
            return val.strip()
    if isinstance(result, str) and result.strip():
        return result.strip()
    return str(result or "").strip()


def run_crew_tailoring(
    *,
    personal_writeup: str,
    job_posting_text: str,
    resume_text: str,
    contacts_source: dict[str, Any] | None = None,
    company_name: str | None = None,
    job_title: str | None = None,
    model: str | None = None,
    verbose: bool | None = None,
) -> dict[str, Any]:
    """
    Run L7 crew kickoff then markdown_to_cv_json.

    Returns tailored markdown, structured CV (slim-normalized), and usage calls.
    When verbose (default: JOB_APP_CREW_VERBOSE), CrewAI prints agent progress
    to stdout like the L7 notebook.
    """
    if verbose is None:
        verbose = JOB_APP_CREW_VERBOSE

    company = str(company_name or "").strip() or "extract from job posting"
    title = str(job_title or "").strip() or "extract from job posting"

    with tempfile.TemporaryDirectory(prefix="crew_l7_") as tmp:
        out_md = Path(tmp) / "tailored_resume.md"
        crew, resume_task = build_job_application_crew(
            output_file=out_md,
            verbose=verbose,
        )
        inputs = {
            "personal_writeup": personal_writeup,
            "job_posting_text": job_posting_text,
            "resume_text": resume_text,
            "company_name": company,
            "job_title": title,
        }
        logger.info(
            "L7 crew kickoff: writeup=%s chars, resume=%s chars, jd=%s chars",
            len(personal_writeup or ""),
            len(resume_text or ""),
            len(job_posting_text or ""),
        )
        if verbose:
            print(
                "\n=== L7 crew kickoff start ===\n"
                f"writeup={len(personal_writeup or '')} chars, "
                f"resume={len(resume_text or '')} chars, "
                f"jd={len(job_posting_text or '')} chars\n",
                flush=True,
            )

        result = crew.kickoff(inputs=inputs)

        tailored_md = ""
        if out_md.is_file():
            tailored_md = out_md.read_text(encoding="utf-8").strip()
        if not tailored_md:
            tailored_md = _task_output_text(resume_task, result)
        if not tailored_md or len(tailored_md) < 80:
            raise RuntimeError("Crew returned empty or too-short tailored resume Markdown")

        md_model = model or get_openai_model_name()
        # Strip aisuite-style prefix if UI passed openai:gpt-4o-mini
        if ":" in md_model and not md_model.startswith("gpt"):
            _, _, maybe = md_model.partition(":")
            if maybe:
                md_model = maybe

        if verbose:
            print("\n=== markdown_to_cv_json (OpenAI) ===\n", flush=True)

        filled, md_usage = markdown_to_cv_json(
            markdown=tailored_md,
            contacts_source=contacts_source,
            model=md_model,
        )
        slim_raw = l7_json_to_slim_cv(filled)
        tailored_structured = normalize_to_cv(slim_raw)

        usage_metrics = getattr(crew, "usage_metrics", None)
        calls = crew_usage_to_calls(usage_metrics, label="crew_l7_kickoff")
        md_call = {
            "step": "markdown_to_cv_json",
            "prompt_tokens": int(md_usage.get("prompt_tokens") or 0),
            "completion_tokens": int(md_usage.get("completion_tokens") or 0),
            "total_tokens": int(md_usage.get("total_tokens") or 0),
            "model": md_model,
        }
        calls.append(md_call)

        print_crew_usage_summary(
            usage_metrics,
            label="job_application_crew",
            extra_calls=[md_call],
        )

        if verbose:
            print("\n=== L7 crew kickoff end ===\n", flush=True)

        return {
            "tailored_markdown": tailored_md,
            "tailored_structured": tailored_structured,
            "l7_json": filled,
            "usage_calls": calls,
            "model": md_model,
        }
