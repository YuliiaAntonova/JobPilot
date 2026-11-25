"""Resume tailoring orchestrator — L7 CrewAI (default) + optional notebook legacy."""

from __future__ import annotations

import logging
from typing import Any

import yaml

from job_application.config import (
    ALLOW_LEGACY_TAILORING,
    JOB_APP_CREW_VERBOSE,
    TAILORING_PIPELINE,
)
from job_application.infra.llm.usage import pack_and_log_token_usage
from job_application.resume.cv_schema import normalize_to_cv
from job_application.resume.jobbert_match import (
    derive_semantic_groups,
    run_jobbert_match_score,
)
from job_application.resume.profile_text import structured_profile_to_plain_text

logger = logging.getLogger("job_application.safe_tailoring")


def structured_to_resume_yaml_text(structured: dict[str, Any]) -> str:
    cv = normalize_to_cv(structured)
    return yaml.safe_dump(cv, sort_keys=False, allow_unicode=True, width=120).strip()


def resolve_resume_yaml_text(
    *,
    structured: dict[str, Any] | None,
    resume_text: str | None,
) -> str:
    if isinstance(structured, dict) and structured:
        return structured_to_resume_yaml_text(structured)
    text = (resume_text or "").strip()
    if not text:
        raise ValueError("structured profile or resume_text (YAML/text) is required.")
    return text


def confirmed_facts_from_selection(
    ask_items: list[dict],
    selected_ids: list[str],
) -> tuple[list[dict], list[dict]]:
    """Legacy helper for tests / UI compatibility (L7 flow has no ask_user)."""
    id_set = {str(x).strip().lower() for x in (selected_ids or []) if str(x).strip()}
    confirmed_facts: list[dict] = []
    confirmation_events: list[dict] = []

    for item in ask_items:
        if not isinstance(item, dict):
            continue
        fact_id = str(item.get("id", "") or "").strip()
        proposed_fact = str(item.get("proposed_fact", "") or "").strip()
        if not fact_id:
            continue

        if fact_id.lower() in id_set:
            if proposed_fact:
                confirmed_facts.append(
                    {
                        "id": fact_id,
                        "fact": proposed_fact,
                        "apply_to": str(item.get("apply_to", "") or "").strip(),
                        "company": str(item.get("company", "") or "").strip(),
                        "required_terms": [
                            str(x).strip()
                            for x in (item.get("required_terms", []) or [])
                            if str(x).strip()
                        ],
                        "semantic_groups": item.get("semantic_groups")
                        or derive_semantic_groups(proposed_fact),
                        "source": "human_batch_selection",
                    }
                )
            confirmation_events.append(
                {
                    "type": "fact_confirmed",
                    "id": fact_id,
                    "section": item.get("section", ""),
                    "fact": proposed_fact,
                    "apply_to": str(item.get("apply_to", "") or "").strip(),
                    "company": str(item.get("company", "") or "").strip(),
                    "required_terms": [
                        str(x).strip()
                        for x in (item.get("required_terms", []) or [])
                        if str(x).strip()
                    ],
                    "source": "human_batch_selection",
                }
            )
        else:
            confirmation_events.append(
                {
                    "type": "fact_rejected",
                    "id": fact_id,
                    "section": item.get("section", ""),
                    "fact": proposed_fact,
                    "source": "human_batch_selection",
                }
            )

    return confirmed_facts, confirmation_events


def _pipeline_mode() -> str:
    mode = (TAILORING_PIPELINE or "crew_l7").strip().lower()
    if mode in ("notebook", "notebook_untitled", "legacy"):
        if not ALLOW_LEGACY_TAILORING:
            raise ValueError(
                "Legacy notebook tailor is disabled. "
                "Set ALLOW_LEGACY_TAILORING=1 or use TAILORING_PIPELINE=crew_l7."
            )
        logger.warning(
            "Using legacy notebook tailor (TAILORING_PIPELINE=%s). Prefer crew_l7.",
            mode,
        )
        return "notebook"
    return "crew_l7"


def _write_preview(tailored_structured: dict[str, Any]) -> dict[str, str] | None:
    cv_preview: dict[str, str] | None = None
    try:
        from job_application.config import CV_PREVIEW_ENABLED
        from job_application.resume.cv_pdf_export import write_job_tailored_draft_preview

        if CV_PREVIEW_ENABLED:
            _yml, html_path = write_job_tailored_draft_preview(tailored_structured)
            cv_preview = {
                "cv_html": str(html_path.name),
                "cv_yml": _yml.name,
                "scope": "job_tailored_draft",
            }
    except Exception as exc:
        logger.warning("job tailored preview render failed: %s", exc)
    return cv_preview


def _resolve_job_meta(
    *,
    company_name: str | None = None,
    job_title: str | None = None,
    analysis: dict[str, Any] | None = None,
) -> tuple[str, str]:
    company = str(company_name or "").strip()
    title = str(job_title or "").strip()
    if isinstance(analysis, dict):
        if not company:
            company = str(
                analysis.get("company_name")
                or analysis.get("company")
                or ""
            ).strip()
        if not title:
            title = str(
                analysis.get("job_title")
                or analysis.get("target_job_title")
                or ""
            ).strip()
    return company, title


def _apply_target_meta_to_structured(
    tailored_structured: dict[str, Any],
    *,
    company_name: str = "",
    job_title: str = "",
) -> None:
    """Replace leftover LLM placeholders like [Company Name] in summary/headline."""
    company = str(company_name or "").strip()
    title = str(job_title or "").strip()
    if not company and not title:
        return
    basics = tailored_structured.get("basics")
    if not isinstance(basics, dict):
        return

    def _scrub(text: str) -> str:
        out = text
        if company:
            for ph in (
                "[Company Name]",
                "[company name]",
                "[COMPANY NAME]",
                "[Company]",
                "[company]",
            ):
                out = out.replace(ph, company)
        if title:
            for ph in (
                "[Job Title]",
                "[job title]",
                "[JOB TITLE]",
                "[Role]",
                "[role]",
                "[Position]",
                "[position]",
            ):
                out = out.replace(ph, title)
        return out

    for key in ("summary", "headline", "label"):
        raw = basics.get(key)
        if isinstance(raw, str) and raw.strip():
            basics[key] = _scrub(raw)


# ---------------------------------------------------------------------------
# L7 CrewAI path
# ---------------------------------------------------------------------------


def _run_analyze_crew_l7(
    *,
    job_description: str,
    structured: dict[str, Any] | None = None,
    resume_text: str | None = None,
    model: str | None = None,
    include_jobbert: bool = True,
    company_name: str | None = None,
    job_title: str | None = None,
) -> dict[str, Any]:
    from job_application.resume.crew_tailoring.adapter import build_crew_kickoff_inputs

    jd = (job_description or "").strip()
    if len(jd) < 40:
        raise ValueError("job_description is too short")

    if not isinstance(structured, dict) or not structured:
        # Allow plain resume_text only for length check; generate still needs structured
        plain_fallback = (resume_text or "").strip()
        if len(plain_fallback) < 80:
            raise ValueError("structured profile is required (chat or PDF → cv.yml) for L7 tailoring")
        raise ValueError("structured profile is required (chat or PDF → cv.yml) for L7 tailoring")

    company, title = _resolve_job_meta(company_name=company_name, job_title=job_title)
    inputs = build_crew_kickoff_inputs(
        structured=structured,
        job_description=jd,
        company_name=company,
        job_title=title,
    )
    resume_md = inputs["resume_text"]
    if len(resume_md) < 80:
        raise ValueError("Resume is too short for tailoring")

    resume_yaml = structured_to_resume_yaml_text(structured)
    parsed_cv = inputs["cv"]

    jobbert_before = None
    if include_jobbert:
        jobbert_before = run_jobbert_match_score(
            resume_yaml,
            jd,
            structured=parsed_cv,
            phase="before crew_l7 tailoring",
        )

    analysis = {
        "pipeline": "crew_l7",
        "personal_writeup": inputs["personal_writeup"],
        "resume_text": resume_md,
        "job_posting_text": inputs["job_posting_text"],
        "github_url": inputs.get("github_url") or "",
        "resume_plain_text": structured_profile_to_plain_text(parsed_cv),
        "company_name": company,
        "job_title": title,
    }

    token_usage = pack_and_log_token_usage(
        "crew_l7_analyze",
        model or "openai",
        [],
    )

    return {
        "phase": "ready_to_generate",
        "resume_yaml": resume_yaml,
        "analysis": analysis,
        "ask_user": [],
        "suppressed_confirmations": [],
        "rejected_ask_user": [],
        "jobbert_score_before": jobbert_before,
        "token_usage": token_usage,
    }


def _run_generate_crew_l7(
    *,
    job_description: str,
    analysis: dict,
    structured: dict[str, Any] | None = None,
    resume_text: str | None = None,
    selected_ids: list[str] | None = None,
    model: str | None = None,
    include_jobbert: bool = True,
    company_name: str | None = None,
    job_title: str | None = None,
) -> dict[str, Any]:
    del selected_ids, resume_text

    from job_application.resume.crew_tailoring.adapter import (
        build_crew_kickoff_inputs,
        enrich_job_posting_text,
    )
    from job_application.resume.crew_tailoring.runner import run_crew_tailoring
    from job_application.resume.crew_tailoring.utils import get_openai_model_name

    jd = (job_description or "").strip()
    if len(jd) < 40:
        raise ValueError("job_description is too short")
    if not isinstance(analysis, dict):
        raise ValueError("analysis must be a mapping")
    if not isinstance(structured, dict) or not structured:
        raise ValueError("structured profile is required to generate cv_tailored (chat or PDF → cv.yml).")

    company, title = _resolve_job_meta(
        company_name=company_name,
        job_title=job_title,
        analysis=analysis,
    )

    personal_writeup = str(analysis.get("personal_writeup") or "").strip()
    resume_md = str(analysis.get("resume_text") or "").strip()
    job_posting = str(analysis.get("job_posting_text") or jd).strip() or jd
    job_posting = enrich_job_posting_text(
        job_posting,
        company_name=company,
        job_title=title,
    )

    if not personal_writeup or not resume_md:
        rebuilt = build_crew_kickoff_inputs(
            structured=structured,
            job_description=jd,
            company_name=company,
            job_title=title,
        )
        personal_writeup = personal_writeup or rebuilt["personal_writeup"]
        resume_md = resume_md or rebuilt["resume_text"]
        job_posting = rebuilt["job_posting_text"]

    openai_model = get_openai_model_name()
    # Prefer OPENAI_MODEL_NAME; ignore cursor:/groq: UI model for exact L7
    if model and str(model).startswith("openai:"):
        openai_model = str(model).split(":", 1)[1].strip() or openai_model

    crew_out = run_crew_tailoring(
        personal_writeup=personal_writeup,
        job_posting_text=job_posting,
        resume_text=resume_md,
        contacts_source=normalize_to_cv(structured),
        company_name=company,
        job_title=title,
        model=openai_model,
        verbose=JOB_APP_CREW_VERBOSE,
    )

    tailored_structured = crew_out["tailored_structured"]
    # Preserve name from original if LLM dropped it
    src_basics = (normalize_to_cv(structured).get("basics") or {})
    dst_basics = tailored_structured.setdefault("basics", {})
    if isinstance(dst_basics, dict) and isinstance(src_basics, dict):
        if not str(dst_basics.get("name") or "").strip() and src_basics.get("name"):
            dst_basics["name"] = src_basics["name"]

    _apply_target_meta_to_structured(
        tailored_structured,
        company_name=company,
        job_title=title,
    )

    cv_preview = _write_preview(tailored_structured)
    tailored_yaml = yaml.safe_dump(
        tailored_structured, sort_keys=False, allow_unicode=True, width=120
    ).strip()
    plain_out = structured_profile_to_plain_text(tailored_structured)

    jobbert_after = None
    if include_jobbert:
        jobbert_after = run_jobbert_match_score(
            tailored_yaml,
            jd,
            structured=tailored_structured,
            phase="after crew_l7 tailoring",
        )

    token_usage = pack_and_log_token_usage(
        "crew_l7_generate",
        crew_out.get("model") or openai_model,
        crew_out.get("usage_calls") or [],
    )

    safety = {
        "manual_review_required": False,
        "pipeline": "crew_l7",
    }

    headline = ""
    b = tailored_structured.get("basics") if isinstance(tailored_structured.get("basics"), dict) else {}
    if isinstance(b, dict):
        headline = str(b.get("headline") or "").strip()

    return {
        "phase": "done",
        "tailored_yaml": tailored_yaml,
        "tailored_structured": tailored_structured,
        "tailored_resume_text": plain_out,
        "tailored_markdown": crew_out.get("tailored_markdown") or "",
        "cover_letter": "",
        "optimization_report": {},
        "notebook_result": {
            "pipeline": "crew_l7",
        },
        "confirmed_facts": [],
        "confirmation_events": [],
        "application_audit": {},
        "safety_check": safety,
        "jobbert_score_after": jobbert_after,
        "token_usage": token_usage,
        "cv_preview": cv_preview,
        "target_job_title": headline,
    }


# ---------------------------------------------------------------------------
# Legacy notebook path (TAILORING_PIPELINE=notebook)
# ---------------------------------------------------------------------------


def _run_analyze_notebook(
    *,
    job_description: str,
    structured: dict[str, Any] | None = None,
    resume_text: str | None = None,
    model: str | None = None,
    include_jobbert: bool = True,
) -> dict[str, Any]:
    from job_application.resume.notebook_tailoring import pipeline as nb
    from job_application.resume.notebook_tailoring.cv_bridge import (
        resume_plain_text_for_tailoring,
    )
    from job_application.resume.notebook_tailoring.pipeline import flatten_skills

    jd = (job_description or "").strip()
    if len(jd) < 40:
        raise ValueError("job_description is too short")

    plain = resume_plain_text_for_tailoring(structured=structured, resume_text=resume_text)
    if len(plain) < 80:
        raise ValueError("Resume is too short for tailoring")

    resume_yaml = resolve_resume_yaml_text(structured=structured, resume_text=resume_text)
    parsed_cv = normalize_to_cv(structured) if structured else None

    jobbert_before = None
    if include_jobbert and parsed_cv is not None:
        jobbert_before = run_jobbert_match_score(
            resume_yaml,
            jd,
            structured=parsed_cv,
            phase="before notebook tailoring",
        )

    nb.llm.configure(model)
    nb.llm.reset_usage()
    resume_info = nb.parse_resume(plain)
    job_info = nb.parse_job_description(jd)
    job_skills = list(job_info.get("required_skills") or []) + list(
        job_info.get("preferred_skills") or []
    )
    resume_skills = flatten_skills(resume_info.get("skills") or [])
    initial_score, matched_skills, missing_skills = nb.get_skill_match_score(
        resume_skills, job_skills
    )

    analysis = {
        "pipeline": "notebook_untitled",
        "resume_info": resume_info,
        "job_info": job_info,
        "initial_match_score": initial_score,
        "matched_skills": matched_skills,
        "missing_skills": missing_skills,
        "resume_plain_text": plain,
    }

    token_usage = pack_and_log_token_usage("notebook_tailoring_analyze", model, nb.llm.get_usage_calls())

    return {
        "phase": "ready_to_generate",
        "resume_yaml": resume_yaml,
        "analysis": analysis,
        "ask_user": [],
        "suppressed_confirmations": [],
        "rejected_ask_user": [],
        "jobbert_score_before": jobbert_before,
        "token_usage": token_usage,
    }


def _run_generate_notebook(
    *,
    job_description: str,
    analysis: dict,
    structured: dict[str, Any] | None = None,
    resume_text: str | None = None,
    selected_ids: list[str] | None = None,
    model: str | None = None,
    include_jobbert: bool = True,
) -> dict[str, Any]:
    del selected_ids

    from job_application.resume.notebook_tailoring import pipeline as nb
    from job_application.resume.notebook_tailoring.cv_bridge import (
        apply_notebook_resume_to_cv,
        resume_plain_text_for_tailoring,
    )

    jd = (job_description or "").strip()
    if len(jd) < 40:
        raise ValueError("job_description is too short")
    if not isinstance(analysis, dict):
        raise ValueError("analysis must be a mapping")

    plain = str(analysis.get("resume_plain_text") or "").strip()
    if not plain:
        plain = resume_plain_text_for_tailoring(structured=structured, resume_text=resume_text)

    if not isinstance(structured, dict) or not structured:
        raise ValueError("structured profile is required to generate cv_tailored (chat or PDF → cv.yml).")

    result = nb.tailor_resume(
        plain,
        jd,
        model=model,
        include_cover_letter=True,
        include_optimization_report=True,
        verbose=False,
    )

    job_info = result.get("job_info") or analysis.get("job_info") or {}
    tailored_structured = apply_notebook_resume_to_cv(
        structured,
        result["resume"],
        job_info=job_info,
    )
    tailored_structured = normalize_to_cv(tailored_structured)
    basics = tailored_structured.setdefault("basics", {})
    if isinstance(basics, dict):
        old_headline = str(basics.get("headline") or "").strip()
        old_summary = str(basics.get("summary") or "").strip()
        new_headline, new_summary = nb.tailor_headline_and_summary(
            old_headline,
            old_summary,
            job_info,
        )
        basics["headline"] = new_headline
        basics["summary"] = new_summary

    cv_preview = _write_preview(tailored_structured)
    tailored_yaml = yaml.safe_dump(
        tailored_structured, sort_keys=False, allow_unicode=True, width=120
    ).strip()
    plain_out = structured_profile_to_plain_text(tailored_structured)

    jobbert_after = None
    if include_jobbert:
        jobbert_after = run_jobbert_match_score(
            tailored_yaml,
            jd,
            structured=tailored_structured,
            phase="after notebook tailoring",
        )

    token_usage = pack_and_log_token_usage(
        "notebook_tailoring_generate",
        model,
        nb.llm.get_usage_calls() or result.get("llm_calls") or [],
    )

    safety = {
        "manual_review_required": False,
        "pipeline": "notebook_untitled",
        "initial_match_score": result.get("initial_match_score"),
        "final_match_score": result.get("final_match_score"),
    }

    return {
        "phase": "done",
        "tailored_yaml": tailored_yaml,
        "tailored_structured": tailored_structured,
        "tailored_resume_text": plain_out,
        "cover_letter": result.get("cover_letter") or "",
        "optimization_report": result.get("optimization_report") or {},
        "notebook_result": {
            "matched_skills": result.get("matched_skills"),
            "missing_skills": result.get("missing_skills"),
            "token_totals": result.get("token_totals"),
        },
        "confirmed_facts": [],
        "confirmation_events": [],
        "application_audit": {},
        "safety_check": safety,
        "jobbert_score_after": jobbert_after,
        "token_usage": token_usage,
        "cv_preview": cv_preview,
        "target_job_title": str(job_info.get("job_title") or "").strip(),
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_analyze(
    *,
    job_description: str,
    structured: dict[str, Any] | None = None,
    resume_text: str | None = None,
    model: str | None = None,
    include_jobbert: bool = True,
    company_name: str | None = None,
    job_title: str | None = None,
) -> dict[str, Any]:
    if _pipeline_mode() == "notebook":
        return _run_analyze_notebook(
            job_description=job_description,
            structured=structured,
            resume_text=resume_text,
            model=model,
            include_jobbert=include_jobbert,
        )
    return _run_analyze_crew_l7(
        job_description=job_description,
        structured=structured,
        resume_text=resume_text,
        model=model,
        include_jobbert=include_jobbert,
        company_name=company_name,
        job_title=job_title,
    )


def run_generate(
    *,
    job_description: str,
    analysis: dict,
    structured: dict[str, Any] | None = None,
    resume_text: str | None = None,
    selected_ids: list[str] | None = None,
    model: str | None = None,
    include_jobbert: bool = True,
    company_name: str | None = None,
    job_title: str | None = None,
) -> dict[str, Any]:
    # Honor analysis.pipeline if present (session started on a given mode)
    analysis_pipeline = ""
    if isinstance(analysis, dict):
        analysis_pipeline = str(analysis.get("pipeline") or "").strip().lower()

    use_notebook = analysis_pipeline in ("notebook_untitled", "notebook", "legacy") or (
        not analysis_pipeline and _pipeline_mode() == "notebook"
    )
    if use_notebook:
        return _run_generate_notebook(
            job_description=job_description,
            analysis=analysis,
            structured=structured,
            resume_text=resume_text,
            selected_ids=selected_ids,
            model=model,
            include_jobbert=include_jobbert,
        )
    return _run_generate_crew_l7(
        job_description=job_description,
        analysis=analysis,
        structured=structured,
        resume_text=resume_text,
        selected_ids=selected_ids,
        model=model,
        include_jobbert=include_jobbert,
        company_name=company_name,
        job_title=job_title,
    )


def run_preview_render(
    *,
    tailored_structured: dict[str, Any] | None = None,
    tailored_yaml: str | None = None,
) -> dict[str, Any]:
    """Re-render cv_tailored_draft.html from edited structured JSON or YAML (no DB write)."""
    from job_application.config import CV_PREVIEW_ENABLED
    from job_application.resume.cv_pdf_export import write_job_tailored_draft_preview

    if not CV_PREVIEW_ENABLED:
        raise ValueError("CV preview disabled (CV_PREVIEW_ENABLED=0)")
    if (tailored_yaml or "").strip():
        parsed = yaml.safe_load(tailored_yaml)
        if not isinstance(parsed, dict):
            raise ValueError("tailored_yaml must be a YAML object (mapping)")
        cv = normalize_to_cv(parsed)
    elif isinstance(tailored_structured, dict) and tailored_structured:
        cv = normalize_to_cv(tailored_structured)
    else:
        raise ValueError("tailored_structured or tailored_yaml is required")
    _yml, html_path = write_job_tailored_draft_preview(cv)
    plain_out = structured_profile_to_plain_text(cv)
    tailored_yaml_out = yaml.safe_dump(cv, sort_keys=False, allow_unicode=True, width=120).strip()
    return {
        "cv_preview": {
            "cv_html": html_path.name,
            "cv_yml": _yml.name,
            "scope": "job_tailored_draft",
        },
        "tailored_structured": cv,
        "tailored_yaml": tailored_yaml_out,
        "tailored_resume_text": plain_out,
    }
