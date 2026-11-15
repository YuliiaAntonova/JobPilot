"""Черновик «Новое предложение»: только PostgreSQL (application_jobs.outputs.offer_flow)."""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Any

from job_application.models.enums import PipelineStatus

OFFER_FLOW_KEY = "offer_flow"
TRACKER_KEY = "tracker"

_PIPELINE_VALUES = {s.value for s in PipelineStatus}

_SKIP_JD_LINES = {
    "about the job",
    "about us",
    "the role",
    "job description",
    "responsibilities",
    "requirements",
    "what you'll do",
    "what you will do",
}

# Never accept these as company_name (section headers / parse artifacts)
_BAD_COMPANY_NAMES = {
    "about",
    "about us",
    "about the job",
    "the role",
    "job description",
    "responsibilities",
    "requirements",
    "is seeking",
    "confidential",
    # JD prose openers mistaken for company ("We are looking…")
    "we",
    "our",
    "they",
    "this",
    "that",
    "you",
    "your",
}


def _is_bad_company_name(name: str) -> bool:
    key = str(name or "").strip().casefold()
    if not key:
        return True
    if key in _BAD_COMPANY_NAMES:
        return True
    if key.startswith("confidential"):
        return True
    return False


def _date_from_listed_at(listed_at: Any) -> str:
    raw = str(listed_at or "").strip()
    if len(raw) >= 10 and raw[4] == "-" and raw[7] == "-":
        return raw[:10]
    return date.today().isoformat()


def read_offer_flow(outputs: dict | None) -> dict[str, Any]:
    if not isinstance(outputs, dict):
        return {}
    flow = outputs.get(OFFER_FLOW_KEY)
    return dict(flow) if isinstance(flow, dict) else {}


def read_tracker(flow: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(flow, dict):
        return {}
    tracker = flow.get(TRACKER_KEY)
    return dict(tracker) if isinstance(tracker, dict) else {}


def draft_is_listed(outputs: dict | None) -> bool:
    """Listed = sealed for jd-draft reuse (has tracker.listed_at or tailored text)."""
    flow = read_offer_flow(outputs)
    tracker = read_tracker(flow)
    if str(tracker.get("listed_at") or "").strip():
        return True
    tailored = flow.get("tailored_resume_text")
    return isinstance(tailored, str) and bool(tailored.strip())


def infer_company_title_from_jd(jd_text: str) -> tuple[str, str]:
    """
    Heuristic from LinkedIn / careers postings, e.g.:
      AI Engineer / About the job / Sumsub is …
      Python Platform Engineer / About Revolut / People deserve …
    """
    text = (jd_text or "").strip()
    if not text:
        return "", ""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    title = ""
    company = ""

    if lines:
        first = lines[0]
        if len(first) <= 120 and first.casefold() not in _SKIP_JD_LINES:
            title = first

    # "About Revolut" / "About Acme Inc" (not "About the job")
    m_about_co = re.search(
        r"(?im)^About\s+(?!the\b|us\b)([A-Z][A-Za-z0-9&.'\-]*(?:\s+[A-Z][A-Za-z0-9&.'\-]*){0,3})\s*$",
        text,
    )
    if m_about_co:
        company = m_about_co.group(1).strip()

    if not company:
        m = re.search(
            r"(?is)(?:about the job|about us)\s+"
            r"([A-Z][A-Za-z0-9&.'\-]*(?:\s+[A-Z][A-Za-z0-9&.'\-]*){0,3})"
            r"\s+(?:is|are|helps|provides|builds|offers|connects)\b",
            text,
        )
        if m:
            company = m.group(1).strip()

    if not company:
        m2 = re.search(r"(?i)\bat\s+([A-Z][A-Za-z0-9&.'\-]{1,40})\b", text[:800])
        if m2:
            company = m2.group(1).strip()

    if not company:
        for ln in lines[1:]:
            if ln.casefold() in _SKIP_JD_LINES:
                continue
            # "About Revolut" on one line (fallback if multiline flag missed)
            m_line = re.match(
                r"(?i)^About\s+(?!the\b|us\b)([A-Z][A-Za-z0-9&.'\-]*(?:\s+[A-Z][A-Za-z0-9&.'\-]*){0,3})\s*$",
                ln,
            )
            if m_line:
                company = m_line.group(1).strip()
                break
            m3 = re.match(r"^([A-Z][A-Za-z0-9&.'\-]{1,40})\b", ln)
            if m3 and not _is_bad_company_name(m3.group(1)):
                company = m3.group(1)
                break

    if _is_bad_company_name(company):
        company = ""
    return company, title


def _company_title_from_analysis(analysis: Any) -> tuple[str, str]:
    if not isinstance(analysis, dict):
        return "", ""
    company = str(
        analysis.get("company_name")
        or analysis.get("company")
        or ""
    ).strip()
    title = str(
        analysis.get("job_title")
        or analysis.get("target_job_title")
        or analysis.get("title")
        or ""
    ).strip()
    rt = analysis.get("resume_tailoring")
    if isinstance(rt, dict):
        title = title or str(rt.get("target_job_title") or "").strip()
    if _is_bad_company_name(company):
        company = ""
    return company, title


def resolve_company_title(flow: dict[str, Any] | None, jd_text: str = "") -> tuple[str, str]:
    flow = flow if isinstance(flow, dict) else {}
    company, title = _company_title_from_analysis(flow.get("analysis"))
    if _is_bad_company_name(company):
        company = ""
    if not company or not title:
        jd_c, jd_t = infer_company_title_from_jd(jd_text)
        company = company or jd_c
        title = title or jd_t
    if _is_bad_company_name(company):
        company = ""
    return company, title


def ensure_tracker_on_tailored(
    flow: dict[str, Any],
    *,
    jd_text: str = "",
) -> dict[str, Any]:
    """
    When tailored_resume_text appears, seed tracker (interested, listed_at, applied_at).
    Also repairs empty/bad company and missing applied_at when already listed.
    """
    tailored = flow.get("tailored_resume_text")
    if not isinstance(tailored, str) or not tailored.strip():
        return flow

    tracker = read_tracker(flow)
    company, title = resolve_company_title(flow, jd_text)

    if str(tracker.get("listed_at") or "").strip():
        changed = False
        out_tracker = dict(tracker)
        cur_co = str(out_tracker.get("company_name") or "").strip()
        if (not cur_co or _is_bad_company_name(cur_co)) and company:
            out_tracker["company_name"] = company
            changed = True
        if not str(out_tracker.get("job_title") or "").strip() and title:
            out_tracker["job_title"] = title
            changed = True
        if not str(out_tracker.get("applied_at") or "").strip():
            out_tracker["applied_at"] = _date_from_listed_at(out_tracker.get("listed_at"))
            changed = True
        if not changed:
            return flow
        out = dict(flow)
        out[TRACKER_KEY] = out_tracker
        return out

    now = datetime.now(timezone.utc).isoformat()
    applied = str(tracker.get("applied_at") or "").strip() or date.today().isoformat()
    tracker = {
        **tracker,
        "company_name": str(tracker.get("company_name") or company or "").strip(),
        "job_title": str(tracker.get("job_title") or title or "").strip(),
        "pipeline_status": str(
            tracker.get("pipeline_status") or PipelineStatus.INTERESTED.value
        ),
        "applied_at": applied,
        "closed": bool(tracker.get("closed", False)),
        "listed_at": now,
    }
    if _is_bad_company_name(tracker["company_name"]):
        tracker["company_name"] = company
    if tracker["pipeline_status"] not in _PIPELINE_VALUES:
        tracker["pipeline_status"] = PipelineStatus.INTERESTED.value

    out = dict(flow)
    out[TRACKER_KEY] = tracker
    return out


def merge_tracker_patch(
    existing: dict[str, Any],
    patch: dict[str, Any],
) -> dict[str, Any]:
    """Merge user edits into tracker; auto-fill applied_at when entering applied."""
    tracker = dict(existing) if existing else {}
    if "company_name" in patch and patch["company_name"] is not None:
        tracker["company_name"] = str(patch["company_name"]).strip()
    if "job_title" in patch and patch["job_title"] is not None:
        tracker["job_title"] = str(patch["job_title"]).strip()
    if "closed" in patch and patch["closed"] is not None:
        tracker["closed"] = bool(patch["closed"])

    new_status = patch.get("pipeline_status")
    if new_status is not None:
        status = str(new_status).strip().lower()
        if status not in _PIPELINE_VALUES:
            raise ValueError(
                f"pipeline_status must be one of: {', '.join(sorted(_PIPELINE_VALUES))}"
            )
        tracker["pipeline_status"] = status

    if "applied_at" in patch:
        raw = patch["applied_at"]
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            tracker["applied_at"] = None
        else:
            tracker["applied_at"] = str(raw).strip()[:32]

    # Auto applied_at when moving to applied
    if tracker.get("pipeline_status") == PipelineStatus.APPLIED.value:
        if not str(tracker.get("applied_at") or "").strip():
            tracker["applied_at"] = date.today().isoformat()

    if not str(tracker.get("listed_at") or "").strip():
        tracker["listed_at"] = datetime.now(timezone.utc).isoformat()
    if "pipeline_status" not in tracker or tracker["pipeline_status"] not in _PIPELINE_VALUES:
        tracker["pipeline_status"] = PipelineStatus.INTERESTED.value
    if "closed" not in tracker:
        tracker["closed"] = False

    return tracker


def merge_offer_flow(
    existing: dict[str, Any],
    patch: dict[str, Any],
    *,
    jd_text: str = "",
) -> dict[str, Any]:
    merged = {**existing}
    for key, value in patch.items():
        if value is None:
            continue
        if key == "analysis" and isinstance(value, dict):
            # Полная замена: иначе в БД остаются артефакты (например test: true из ручных проверок).
            merged["analysis"] = dict(value)
        elif key == TRACKER_KEY and isinstance(value, dict):
            merged[TRACKER_KEY] = dict(value)
        else:
            merged[key] = value
    merged["saved_at"] = datetime.now(timezone.utc).isoformat()
    merged = ensure_tracker_on_tailored(merged, jd_text=jd_text)
    return merged


def build_offer_draft_payload(job_id: str, jd_text: str, outputs: dict | None) -> dict[str, Any]:
    flow = read_offer_flow(outputs)
    analysis = flow.get("analysis") if isinstance(flow.get("analysis"), dict) else None
    cover = flow.get("cover_letter_text") if isinstance(flow.get("cover_letter_text"), str) else ""
    tailored = flow.get("tailored_resume_text") if isinstance(flow.get("tailored_resume_text"), str) else ""
    resume_paste = flow.get("resume_paste") if isinstance(flow.get("resume_paste"), str) else ""
    tracker = read_tracker(flow)
    return {
        "job_id": job_id,
        "jd_text": (jd_text or "").strip(),
        "analysis": analysis,
        "cover_letter_text": cover,
        "tailored_resume_text": tailored,
        "resume_paste": resume_paste,
        "model": flow.get("model") if isinstance(flow.get("model"), str) else "",
        "saved_at": flow.get("saved_at"),
        "tracker": tracker or None,
    }


_SKILL_NOISE = {
    "experience",
    "skills",
    "requirements",
    "qualifications",
    "responsibility",
    "responsibilities",
    "nice to have",
    "must have",
    "the role",
    "about the job",
}


def _normalize_skill_list(raw: Any, *, limit: int = 24) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        skill = str(item or "").strip()
        if not skill or len(skill) < 2:
            continue
        key = skill.casefold()
        if key in _SKILL_NOISE or key in seen:
            continue
        seen.add(key)
        out.append(skill)
        if len(out) >= limit:
            break
    return out


def skills_from_analysis(analysis: Any) -> list[str]:
    """Prefer JobBERT required_entities; else required_skills; else matched∪unmatched."""
    if not isinstance(analysis, dict):
        return []
    for key in ("required_entities", "required_skills"):
        skills = _normalize_skill_list(analysis.get(key))
        if skills:
            return skills
    merged: list[Any] = []
    for key in ("matched_skills", "unmatched_skills"):
        part = analysis.get(key)
        if isinstance(part, list):
            merged.extend(part)
    return _normalize_skill_list(merged)


def skills_from_ats(analysis: Any) -> list[str]:
    """ATS phrase suggestions → JD-side entities/phrases."""
    if not isinstance(analysis, dict):
        return []
    collected: list[str] = []
    for key in ("ats_confident_suggestions", "ats_suggestions", "ats_phrase_suggestions"):
        rows = analysis.get(key)
        if not isinstance(rows, list):
            continue
        for row in rows:
            if isinstance(row, dict):
                for field in ("jd_entity", "jd_phrase", "required_skill"):
                    val = str(row.get(field) or "").strip()
                    if val:
                        collected.append(val)
                        break
            elif isinstance(row, str) and row.strip():
                collected.append(row.strip())
    return _normalize_skill_list(collected)


_JD_SKILL_SECTION = re.compile(
    r"(?im)^\s*(?:requirements|skills(?:\s*&\s*requirements)?|must[- ]have|"
    r"what you(?:'|’)(?:ll| will) need|qualifications|tech(?:nical)?\s*stack|"
    r"technologies|nice[- ]to[- ]have)\s*:?\s*$"
)
_JD_BULLET = re.compile(r"^\s*(?:[-*•▪◦]|\d+[.)])\s+")


def skills_from_jd_text(jd_text: str, *, limit: int = 24) -> list[str]:
    """Lightweight bullet scrape under Requirements/Skills (no JobBERT)."""
    text = (jd_text or "").strip()
    if not text:
        return []
    lines = text.splitlines()
    collecting = False
    raw: list[str] = []
    for ln in lines:
        stripped = ln.strip()
        if not stripped:
            if collecting and raw:
                # blank line inside section — keep collecting a bit
                continue
            continue
        if _JD_SKILL_SECTION.match(stripped):
            collecting = True
            continue
        if collecting:
            # stop at next all-caps-ish section header without bullets
            if (
                not _JD_BULLET.match(stripped)
                and len(stripped) <= 60
                and stripped.endswith(":")
            ):
                break
            if _JD_SKILL_SECTION.match(stripped):
                continue
            item = _JD_BULLET.sub("", stripped).strip()
            # Prefer short skill-like lines; skip long prose bullets
            if item and len(item) <= 80:
                # comma-separated stack lines
                if "," in item and len(item) <= 120:
                    parts = [p.strip() for p in item.split(",")]
                    raw.extend(p for p in parts if 1 < len(p) <= 40)
                else:
                    raw.append(item)
            if len(raw) >= limit * 2:
                break
    return _normalize_skill_list(raw, limit=limit)


def resolve_application_skills(
    outputs: dict | None,
    jd_text: str = "",
    *,
    limit: int = 24,
) -> list[str]:
    """
    Skills for Saved Companies list.
    Priority: tracker snapshot → analysis/JobBERT → ATS phrases → JD bullets.
    """
    flow = read_offer_flow(outputs)
    tracker = read_tracker(flow)
    snap = tracker.get("skills") or tracker.get("required_skills")
    if isinstance(snap, list) and snap:
        return _normalize_skill_list(snap, limit=limit)

    analysis = flow.get("analysis") if isinstance(flow.get("analysis"), dict) else {}
    for resolver in (skills_from_analysis, skills_from_ats):
        skills = resolver(analysis)
        if skills:
            return skills[:limit]

    # Top-level outputs.ats if ever stored separately
    top_ats = outputs.get("ats") if isinstance(outputs, dict) else None
    if isinstance(top_ats, dict):
        skills = skills_from_ats(top_ats) or _normalize_skill_list(
            top_ats.get("required_skills") or top_ats.get("skills")
        )
        if skills:
            return skills[:limit]

    return skills_from_jd_text(jd_text, limit=limit)


def build_application_row(job_id: str, jd_text: str, outputs: dict | None) -> dict[str, Any] | None:
    """One list row for GET /jobs/applications; None if not listed."""
    flow = read_offer_flow(outputs)
    tracker = read_tracker(flow)
    if not draft_is_listed(outputs):
        return None

    company, title = resolve_company_title(flow, jd_text)
    if not str(tracker.get("listed_at") or "").strip():
        tracker = {
            "company_name": company,
            "job_title": title,
            "pipeline_status": PipelineStatus.INTERESTED.value,
            "applied_at": None,
            "closed": False,
            "listed_at": None,
        }
    else:
        cur_co = str(tracker.get("company_name") or "").strip()
        cur_title = str(tracker.get("job_title") or "").strip()
        if not cur_co or _is_bad_company_name(cur_co):
            cur_co = company
        if not cur_title:
            cur_title = title
        tracker = {
            **tracker,
            "company_name": cur_co,
            "job_title": cur_title,
        }

    skills = resolve_application_skills(outputs, jd_text)
    jd = (jd_text or "").strip()
    preview = jd[:240] + ("…" if len(jd) > 240 else "")
    return {
        "job_id": job_id,
        "company_name": str(tracker.get("company_name") or "").strip(),
        "job_title": str(tracker.get("job_title") or "").strip(),
        "pipeline_status": str(
            tracker.get("pipeline_status") or PipelineStatus.INTERESTED.value
        ),
        "applied_at": tracker.get("applied_at"),
        "closed": bool(tracker.get("closed", False)),
        "listed_at": tracker.get("listed_at"),
        "skills": skills,
        "jd_preview": preview,
    }
