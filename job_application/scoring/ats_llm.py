"""LLM refinement of ATS substitutions from JobBERT MATCHED + MISSING only."""

from __future__ import annotations

from typing import Any

from job_application.config import APP_LLM_MODEL


def format_jobbert_match_report(
    matched_details: list[dict[str, Any]],
    missing_details: list[dict[str, Any]],
) -> str:
    lines = ["=== MATCHED ==="]
    if matched_details:
        for item in matched_details:
            req = str(item.get("required_skill") or "").strip()
            res = str(item.get("resume_skill") or "").strip()
            mt = str(item.get("match_type") or "")
            sim = float(item.get("similarity") or 0.0)
            lines.append(f"✅ {req} -> {res} [{mt}, {sim:.2f}]")
    else:
        lines.append("(none)")

    lines.append("")
    lines.append("=== MISSING ===")
    if missing_details:
        for item in missing_details:
            req = str(item.get("required_skill") or "").strip()
            best = str(item.get("best_candidate") or "").strip()
            sim = float(item.get("similarity") or 0.0)
            lines.append(f"❌ {req} | closest: {best} [{sim:.2f}]")
    else:
        lines.append("(none)")

    return "\n".join(lines)


def _normalize_substitutions(
    raw: object,
    resume_skills: list[str],
    *,
    max_items: int,
) -> list[dict[str, Any]]:
    resume_by_cf = {str(s).casefold(): str(s).strip() for s in resume_skills if str(s).strip()}
    allowed_jd = set()
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        rp_raw = str(item.get("resume_phrase") or "").strip()
        jp = str(item.get("jd_phrase") or "").strip()
        if not rp_raw or not jp or rp_raw.casefold() == jp.casefold():
            continue
        rp = resume_by_cf.get(rp_raw.casefold())
        if not rp:
            continue
        key = (rp.casefold(), jp.casefold())
        if key in seen:
            continue
        seen.add(key)
        confidence = item.get("confidence")
        try:
            sim = float(confidence)
        except (TypeError, ValueError):
            sim = 0.75
        sim = max(0.0, min(1.0, sim))
        out.append(
            {
                "resume_phrase": rp,
                "jd_phrase": jp,
                "match_type": "llm",
                "similarity": round(sim, 4),
                "reason": str(item.get("reason") or "").strip(),
            }
        )
        if len(out) >= max_items:
            break
    return out


def llm_refine_ats_suggestions(
    matched_details: list[dict[str, Any]],
    missing_details: list[dict[str, Any]],
    resume_skills: list[str],
    *,
    model: str | None = None,
    max_items: int = 10,
) -> dict[str, Any]:
    """
    Cheap LLM pass: only MATCHED + MISSING + resume skills list (~500–1500 tokens).

    Returns ATS-shaped dict with LLM-picked substitutions and audit fields.
    """
    from job_application.shared.llm.client import complete_json_tracked

    skills = [str(s).strip() for s in resume_skills if str(s).strip()]
    report = format_jobbert_match_report(matched_details, missing_details)
    skills_line = ", ".join(skills[:80])

    system = (
        "You refine ATS keyword substitutions for resume tailoring. "
        "JobBERT already computed entity matches. Reply with JSON ONLY, no markdown."
    )
    user = (
        "Resume skills (ONLY these strings may be used as resume_phrase — do not invent):\n"
        f"{skills_line}\n\n"
        f"{report}\n\n"
        "Tasks:\n"
        "1. Treat standalone JD fragments as noise (e.g. programming, language, modern, degree, "
        "Computer, Science, Engineering when they are prose fragments, not real skill names).\n"
        "2. Mark implicit coverage when MATCHED already satisfies a MISSING item "
        "(e.g. programming covered by Python exact match).\n"
        "3. Suggest substitutions resume_phrase → jd_phrase ONLY when:\n"
        "   - resume_phrase is exactly one of the resume skills above;\n"
        "   - jd_phrase comes from a MISSING required_skill (or non-exact MATCHED required_skill);\n"
        "   - the swap improves ATS keyword alignment without lying about experience;\n"
        "   - semantic link is clear (similarity in report may help).\n"
        "4. Do NOT suggest substitutions for exact MATCHED pairs.\n"
        "5. Max "
        f"{max_items} substitutions.\n\n"
        "Return one JSON object:\n"
        "{\n"
        '  "substitutions": [{"resume_phrase": "...", "jd_phrase": "...", "reason": "...", "confidence": 0.0}],\n'
        '  "noise": ["jd fragments to ignore"],\n'
        '  "implicit_covered": [{"jd_phrase": "...", "covered_by": "..."}],\n'
        '  "real_gaps": ["skills truly missing from resume"],\n'
        '  "summary_ru": "1-3 sentences in Russian for the candidate"\n'
        "}"
    )

    data, token_usage = complete_json_tracked(
        model or APP_LLM_MODEL,
        system,
        user,
        call_label="ats_llm_refine",
    )
    if not isinstance(data, dict):
        raise ValueError("ats_llm_refine: expected JSON object")

    suggestions = _normalize_substitutions(
        data.get("substitutions"),
        skills,
        max_items=max_items,
    )

    def _str_list(key: str) -> list[str]:
        raw = data.get(key)
        if not isinstance(raw, list):
            return []
        return [str(x).strip() for x in raw if str(x).strip()]

    implicit: list[dict[str, str]] = []
    for item in data.get("implicit_covered") or []:
        if not isinstance(item, dict):
            continue
        jd_phrase = str(item.get("jd_phrase") or "").strip()
        covered_by = str(item.get("covered_by") or "").strip()
        if jd_phrase and covered_by:
            implicit.append({"jd_phrase": jd_phrase, "covered_by": covered_by})

    return {
        "source": "llm_refined",
        "suggestions": suggestions,
        "noise": _str_list("noise"),
        "implicit_covered": implicit,
        "real_gaps": _str_list("real_gaps"),
        "summary_ru": str(data.get("summary_ru") or "").strip(),
        "token_usage": token_usage,
        "input_report": report,
    }
