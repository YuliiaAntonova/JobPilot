"""
Resume ↔ JD match score via JobBERT knowledge extraction (see jobbert_skill_match.py).

Used by: POST /analyze/job-description, cover letter template, CLI.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from job_application.config import JOBS_DIR, REPO_ROOT, RESUME_TEXT_MIN_CHARS
from job_application.models import Job, ResumeProfile, User
from job_application.resume.profile_text import chat_answers_to_structured, structured_profile_to_plain_text
from job_application.scoring.jobbert import (
    compute_jobbert_skill_match,
    extract_job_skills_from_jd,
    warmup_jobbert_models,
)
from job_application.config import MIN_PHRASE_SIM, PHRASE_DISCOVERY_THRESHOLD
from job_application.scoring.ats import (
    apply_ats_entity_substitutions,
    build_ats_suggestions,
    filter_confident_ats_suggestions,
    merge_ats_suggestions,
)
from job_application.scoring.ats_phrase import (
    build_phrase_ats_suggestions,
    extract_resume_phrases,
    resume_text_for_phrase_ats,
)
from job_application.scoring.ats_llm import llm_refine_ats_suggestions

JD_MIN_CHARS = 40
JD_PREFERRED_CHARS = 200


@dataclass
class LoadedResume:
    text: str | None
    structured: dict
    has_resume: bool
    source: str
    user_email: str | None
    profile_id: str | None
    user_id: str | None


@dataclass
class LoadedJobDescription:
    text: str | None
    source: str
    job_id: str | None


def _valid_resume_text(raw: str | None) -> str | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text or len(text) < RESUME_TEXT_MIN_CHARS:
        return None
    return text


def _read_text_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8").strip() or None


def _latest_job_dirs(limit: int = 20) -> list[Path]:
    if not JOBS_DIR.is_dir():
        return []
    dirs = [p for p in JOBS_DIR.iterdir() if p.is_dir()]
    dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return dirs[:limit]


def build_resume_text_from_profile(profile: ResumeProfile) -> str:
    answers = profile.chat_answers if isinstance(profile.chat_answers, dict) else {}
    if answers:
        structured = chat_answers_to_structured(answers)
    else:
        structured = profile.structured if isinstance(profile.structured, dict) else {}
    return structured_profile_to_plain_text(structured).strip()


def _is_placeholder_jd(text: str) -> bool:
    t = text.strip()
    if not t:
        return True
    lower = t.lower()
    if "xxxxxxxx" in lower:
        return True
    if lower.count("x") / max(len(lower), 1) > 0.25:
        return True
    return False


def _jd_rank(text: str, *, recency_ts: float = 0.0, user_owned: bool = False) -> tuple:
    t = text.strip()
    if _is_placeholder_jd(t):
        return (0, 0, 0, 0)
    quality = 2 if len(t) >= JD_PREFERRED_CHARS else 1
    ownership = 1 if user_owned else 0
    return (ownership, quality, len(t), int(recency_ts))


def _pick_best_jd(candidates: list[tuple[str, str, str | None, float, bool]]) -> LoadedJobDescription | None:
    ranked: list[tuple[tuple, str, str, str | None]] = []
    for text, source, job_id, recency_ts, user_owned in candidates:
        t = text.strip()
        if len(t) < JD_MIN_CHARS:
            continue
        ranked.append((_jd_rank(t, recency_ts=recency_ts, user_owned=user_owned), t, source, job_id))
    if not ranked:
        return None
    ranked.sort(key=lambda item: item[0], reverse=True)
    _, text, source, job_id = ranked[0]
    return LoadedJobDescription(text=text, source=source, job_id=job_id)


def load_resume_from_project(db: Session) -> LoadedResume:
    profiles = db.scalars(select(ResumeProfile).order_by(desc(ResumeProfile.updated_at))).all()
    for profile in profiles:
        text = _valid_resume_text(build_resume_text_from_profile(profile))
        if text is None:
            continue
        user = db.scalars(select(User).where(User.id == profile.user_id)).first()
        answers = profile.chat_answers if isinstance(profile.chat_answers, dict) else {}
        structured = chat_answers_to_structured(answers) if answers else (
            profile.structured if isinstance(profile.structured, dict) else {}
        )
        return LoadedResume(
            text=text,
            structured=structured,
            has_resume=True,
            source="resume_profiles (PostgreSQL, rebuilt from chat_answers)",
            user_email=user.email if user else None,
            profile_id=profile.id,
            user_id=profile.user_id,
        )

    for folder in _latest_job_dirs():
        resume_path = folder / "resume.txt"
        text = _valid_resume_text(_read_text_file(resume_path))
        if text is None:
            continue
        structured: dict = {}
        profile_path = folder / "resume_profile.json"
        if profile_path.is_file():
            try:
                raw = json.loads(profile_path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    structured = raw
            except Exception:
                pass
        return LoadedResume(
            text=text,
            structured=structured,
            has_resume=True,
            source=f"data/jobs/{folder.name}/resume.txt",
            user_email=None,
            profile_id=None,
            user_id=None,
        )

    return LoadedResume(
        text=None,
        structured={},
        has_resume=False,
        source="not found",
        user_email=None,
        profile_id=None,
        user_id=None,
    )


def load_job_description_from_project(db: Session, user_id: str | None = None) -> LoadedJobDescription:
    candidates: list[tuple[str, str, str | None, float, bool]] = []

    if user_id:
        user_jobs = db.scalars(select(Job).where(Job.user_id == user_id).order_by(desc(Job.updated_at))).all()
        for job in user_jobs:
            jd = (job.jd_text or "").strip()
            if not jd:
                continue
            ts = job.updated_at.timestamp() if job.updated_at else 0.0
            candidates.append((jd, f"application_jobs/{job.id} [{job.status}]", job.id, ts, True))

    all_jobs = db.scalars(select(Job).order_by(desc(Job.updated_at)).limit(80)).all()
    for job in all_jobs:
        jd = (job.jd_text or "").strip()
        if not jd:
            continue
        ts = job.updated_at.timestamp() if job.updated_at else 0.0
        owned = bool(user_id and job.user_id == user_id)
        candidates.append((jd, f"application_jobs/{job.id} [{job.status}]", job.id, ts, owned))

    for folder in _latest_job_dirs():
        jd_path = folder / "jd.txt"
        jd = _read_text_file(jd_path)
        if jd:
            candidates.append((jd, f"data/jobs/{folder.name}/jd.txt", folder.name, jd_path.stat().st_mtime, False))

    agency_job = REPO_ROOT / "cv_agency" / "job.txt"
    jd = _read_text_file(agency_job)
    if jd:
        candidates.append((jd, "cv_agency/job.txt", None, agency_job.stat().st_mtime, False))

    fallback = REPO_ROOT / "data" / "job_desc.txt"
    jd = _read_text_file(fallback)
    if jd:
        candidates.append((jd, str(fallback.relative_to(REPO_ROOT)), None, fallback.stat().st_mtime, False))

    picked = _pick_best_jd(candidates)
    if picked is not None:
        return picked
    return LoadedJobDescription(text=None, source="not found", job_id=None)


def _load_resume_for_user(db: Session, user_id: str) -> LoadedResume:
    profile = db.scalars(
        select(ResumeProfile).where(ResumeProfile.user_id == user_id).order_by(desc(ResumeProfile.updated_at))
    ).first()
    if profile is None:
        return LoadedResume(
            text=None,
            structured={},
            has_resume=False,
            source="not found",
            user_email=None,
            profile_id=None,
            user_id=user_id,
        )
    text = _valid_resume_text(build_resume_text_from_profile(profile))
    answers = profile.chat_answers if isinstance(profile.chat_answers, dict) else {}
    structured = chat_answers_to_structured(answers) if answers else (
        profile.structured if isinstance(profile.structured, dict) else {}
    )
    user = db.scalars(select(User).where(User.id == user_id)).first()
    return LoadedResume(
        text=text,
        structured=structured,
        has_resume=text is not None,
        source="resume_profiles (PostgreSQL)",
        user_email=user.email if user else None,
        profile_id=profile.id,
        user_id=user_id,
    )


def run_analysis_from_db(db: Session, *, user_id: str | None = None, include_ats: bool = False) -> dict[str, Any]:
    if user_id:
        loaded_resume = _load_resume_for_user(db, user_id)
    else:
        loaded_resume = load_resume_from_project(db)
    loaded_jd = load_job_description_from_project(db, user_id=loaded_resume.user_id)

    if not loaded_resume.has_resume or not loaded_resume.text or not loaded_jd.text:
        return {
            "scoring_ready": False,
            "loaded_resume": loaded_resume,
            "loaded_jd": loaded_jd,
        }

    result = compute_hybrid_match_score(loaded_resume.text, loaded_jd.text, include_ats=include_ats)
    result["scoring_ready"] = True
    result["loaded_resume"] = loaded_resume
    result["loaded_jd"] = loaded_jd
    return result


def match_rank_label(score: int) -> str:
    if score >= 75:
        return "Strong match"
    if score >= 55:
        return "Good match"
    if score >= 40:
        return "Moderate match"
    return "Weak match"


def normalize_skills_list(skills: list[str] | None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in skills or []:
        text = str(raw).strip()
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


def resolve_required_skills(
    jd_text: str,
    structured: dict | None = None,
    *,
    explicit: list[str] | None = None,
) -> tuple[list[str], str]:
    _ = structured
    if explicit:
        normalized = normalize_skills_list(explicit)
        if normalized:
            return normalized, "explicit"
    skills, _ = extract_job_skills_from_jd(jd_text)
    if skills:
        return skills, "jobbert_requirements_section"
    return [], "none"


def extract_required_skills_from_jd(
    jd_text: str,
    structured: dict | None = None,
    *,
    explicit: list[str] | None = None,
) -> list[str]:
    skills, _ = resolve_required_skills(jd_text, structured, explicit=explicit)
    return skills


def warmup_embedding_model() -> None:
    """Backward-compatible alias for app startup."""
    warmup_jobbert_models()


def compute_hybrid_match_score(
    resume_text: str,
    jd_text: str,
    *,
    structured: dict | None = None,
    include_ats: bool = False,
    include_ats_llm: bool = False,
    phrase_discovery_threshold: float | None = None,
    min_phrase_sim: float | None = None,
) -> dict[str, Any]:
    result = compute_jobbert_skill_match(resume_text, jd_text, structured=structured)
    result["match_rank_label"] = match_rank_label(result["match_score"])
    if include_ats:
        requirements_text = str(result.get("requirements_text") or jd_text)
        matched_details = list(result.get("matched_details") or [])
        missing_details = list(result.get("missing_details") or [])
        resume_for_entities = str(result.get("resume_entities_text") or resume_text)

        entity_ats = build_ats_suggestions(
            resume_for_entities,
            requirements_text,
            matched_details,
            missing_details,
        )
        discovery_th = PHRASE_DISCOVERY_THRESHOLD if phrase_discovery_threshold is None else phrase_discovery_threshold
        confident_th = MIN_PHRASE_SIM if min_phrase_sim is None else min_phrase_sim

        phrase_resume_text = resume_text_for_phrase_ats(resume_text, structured)
        phrase_suggestions = build_phrase_ats_suggestions(
            phrase_resume_text,
            requirements_text,
            missing_details,
            matched_details,
            structured,
            resume_skills=list(result.get("resume_skills") or []),
            required_skills=list(result.get("required_skills") or []),
            phrase_threshold=discovery_th,
        )
        combined = merge_ats_suggestions(
            phrase_suggestions,
            entity_ats.get("suggestions") or [],
        )
        confident = filter_confident_ats_suggestions(
            combined,
            min_phrase_sim=confident_th,
            phrase_discovery_threshold=discovery_th,
        )

        if include_ats_llm:
            llm_ats = llm_refine_ats_suggestions(
                matched_details,
                missing_details,
                list(result.get("resume_skills") or []),
            )
            ats = {
                **llm_ats,
                **entity_ats,
                "suggestions": combined,
                "confident_suggestions": confident,
                "phrase_suggestions": phrase_suggestions,
                "phrase_suggestions_confident": filter_confident_ats_suggestions(
                    phrase_suggestions,
                    min_phrase_sim=confident_th,
                    phrase_discovery_threshold=discovery_th,
                ),
                "entity_suggestions": entity_ats.get("suggestions") or [],
                "rule_suggestions": entity_ats.get("suggestions") or [],
                "resume_phrases": extract_resume_phrases(phrase_resume_text, structured),
                "phrase_resume_text_source": "merged_plain_and_structured",
                "phrase_resume_text": phrase_resume_text,
                "min_phrase_sim": confident_th,
                "phrase_discovery_threshold": discovery_th,
            }
        else:
            ats = {
                **entity_ats,
                "suggestions": combined,
                "confident_suggestions": confident,
                "phrase_suggestions": phrase_suggestions,
                "phrase_suggestions_confident": filter_confident_ats_suggestions(
                    phrase_suggestions,
                    min_phrase_sim=confident_th,
                    phrase_discovery_threshold=discovery_th,
                ),
                "entity_suggestions": entity_ats.get("suggestions") or [],
                "resume_phrases": extract_resume_phrases(phrase_resume_text, structured),
                "phrase_resume_text_source": "merged_plain_and_structured",
                "phrase_resume_text": phrase_resume_text,
                "min_phrase_sim": confident_th,
                "phrase_discovery_threshold": discovery_th,
            }
        ats["preview_text"] = apply_ats_entity_substitutions(resume_text, confident)
        ats["preview_text_all"] = apply_ats_entity_substitutions(resume_text, combined)
        result["ats"] = ats
    return result


def main() -> None:
    from job_application.models.db import SessionLocal

    db = SessionLocal()
    try:
        out = run_analysis_from_db(db)
    finally:
        db.close()

    if not out.get("scoring_ready"):
        print("Скоринг не считаем: резюме или JD не найдены.")
        return

    resume = out["loaded_resume"]
    jd = out["loaded_jd"]
    print("=== Резюме ===")
    print("source:", resume.source, "| user:", resume.user_email)
    print("=== JD ===")
    print("source:", jd.source, "| job_id:", jd.job_id)
    print("--- JobBERT ---")
    print("match_score:", out["match_score"], out["match_rank_label"])
    print("required_skills:", out["required_skills"])
    print("matched_skills:", out["matched_skills"])
    print("unmatched_skills:", out["unmatched_skills"])
    print(out["comparison_summary"])


if __name__ == "__main__":
    main()
