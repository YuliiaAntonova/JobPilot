"""Сохранение профиля из ответов чат-мастера."""

from __future__ import annotations

import copy
import re
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from job_application.repositories import users as db_users
from job_application.config import APP_LLM_MODEL, RESUME_TEXT_MIN_CHARS, RESUME_PLAIN_TEXT_KEY
from job_application.documents.resume_normalize import _has_structured_experience_bullets

EXPERIENCE_BASELINE_KEY = "_experience_baseline"
from job_application.models import ResumeProfile, User
from job_application.resume.profile_text import (
    _companies_loosely_match,
    _experience_entries_from_structured,
    _experience_text_from_jobs,
    _job_highlights,
    _normalize_llm_job_entry,
    chat_answers_to_structured,
    clamp_desired_role,
    enrich_structured_personal_from_plain,
    structured_profile_to_plain_text,
    structured_to_chat_answers,
)


def attach_experience_baseline(structured: dict, *, reset: bool = False) -> dict:
    """Immutable snapshot of experience bullets from PDF/LLM import — survives tailored saves."""
    data = dict(structured or {})
    if not reset and isinstance(data.get(EXPERIENCE_BASELINE_KEY), list) and data[EXPERIENCE_BASELINE_KEY]:
        return data
    jobs = data.get("experience")
    if isinstance(jobs, list) and jobs:
        data[EXPERIENCE_BASELINE_KEY] = copy.deepcopy(jobs)
    return data


def experience_baseline_jobs(structured: dict) -> list[dict]:
    base = structured.get(EXPERIENCE_BASELINE_KEY) if isinstance(structured, dict) else None
    if isinstance(base, list) and base:
        return copy.deepcopy(base)
    exp = structured.get("experience") if isinstance(structured, dict) else None
    return copy.deepcopy(exp) if isinstance(exp, list) else []


def _bullet_looks_corrupted(text: str) -> bool:
    low = str(text or "").casefold()
    return "orchestration tools daily pipelines" in low


def _dedupe_bullet_lines(bullets: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in bullets:
        text = str(raw).strip()
        if not text:
            continue
        key = re.sub(r"\s+", " ", text.casefold())
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


def _dedupe_substring_bullets(bullets: list[str]) -> list[str]:
    """Drop shorter bullets fully contained in a longer one."""
    out: list[str] = []
    for raw in bullets:
        text = str(raw).strip()
        if not text:
            continue
        cf = text.casefold()
        replaced = False
        for idx, existing in enumerate(out):
            ex_cf = existing.casefold()
            if cf == ex_cf:
                replaced = True
                break
            if cf in ex_cf:
                replaced = True
                break
            if ex_cf in cf:
                out[idx] = text
                replaced = True
                break
        if not replaced:
            out.append(text)
    return out


def _prune_superseded_ats_bullets(bullets: list[str], substitutions: list[dict] | None) -> list[str]:
    """Remove pre-ATS wording when JD phrase already present in the same job."""
    out = list(bullets)
    for item in substitutions or []:
        src = str(item.get("resume_phrase") or "").strip()
        dst = str(item.get("jd_phrase") or "").strip()
        if not src or not dst:
            continue
        src_cf, dst_cf = src.casefold(), dst.casefold()
        if not any(dst_cf in b.casefold() for b in out):
            continue
        out = [
            b
            for b in out
            if src_cf not in b.casefold() or dst_cf in b.casefold()
        ]
    return out


def _sync_job_narrative_fields(job: dict) -> dict:
    """Keep highlights/responsibilities/summary in sync — Hursh PDF reads all of them."""
    row = dict(job)
    highlights = row.get("highlights")
    if not isinstance(highlights, list):
        return row
    lines = [str(h).strip() for h in highlights if str(h).strip()]
    if not lines:
        return row
    text = "\n".join(lines)
    row["highlights"] = lines
    row["responsibilities"] = list(lines)
    row["responsibilities_narrative"] = text
    row["raw_description"] = text
    row["summary"] = text
    project = row.get("project")
    if isinstance(project, dict):
        row["project"] = {**project, "description": text}
    return row


def _sync_experience_narrative_fields(structured: dict) -> dict:
    data = dict(structured or {})
    exp = data.get("experience")
    if not isinstance(exp, list):
        return data
    data["experience"] = [_sync_job_narrative_fields(j) for j in exp if isinstance(j, dict)]
    return data


def _sync_experience_text_field(structured: dict) -> dict:
    """Keep top-level experience_text aligned with experience[].highlights (cabinet .txt / API)."""
    data = dict(structured or {})
    exp = data.get("experience")
    if isinstance(exp, list) and exp:
        data["experience_text"] = _experience_text_from_jobs(exp)
    return data


def _finalize_highlight_bullets(
    bullets: list[str],
    *,
    ats_substitutions: list[dict] | None = None,
) -> list[str]:
    from job_application.scoring.ats import apply_ats_entity_substitutions

    chosen = [str(h).strip() for h in bullets if str(h).strip()]
    if ats_substitutions:
        chosen = [apply_ats_entity_substitutions(h, ats_substitutions) for h in chosen]
        chosen = _prune_superseded_ats_bullets(chosen, ats_substitutions)
    chosen = _dedupe_bullet_lines(chosen)
    return _dedupe_substring_bullets(chosen)


def _union_bullet_lines(*sources: list[str]) -> list[str]:
    """Union bullet lines; prefer longer / non-corrupted wording."""
    merged: list[str] = []
    for source in sources:
        for raw in source:
            text = str(raw).strip()
            if not text:
                continue
            norm = text.casefold()
            found = False
            for i, existing in enumerate(merged):
                ex = existing.casefold()
                if norm == ex:
                    if len(text) > len(existing):
                        merged[i] = text
                    found = True
                    break
                if norm in ex or ex in norm:
                    candidates = [existing, text]
                    pick = max(candidates, key=len)
                    if _bullet_looks_corrupted(pick):
                        for c in candidates:
                            if not _bullet_looks_corrupted(c):
                                pick = c
                                break
                    merged[i] = pick
                    found = True
                    break
            if not found:
                merged.append(text)
    return merged


def _experience_bullet_lines(job: dict) -> list[str]:
    """Bullet lines for PDF merge — prefer structured highlights[]."""
    raw = job.get("highlights") or job.get("bullets") or job.get("responsibilities")
    if isinstance(raw, list):
        lines = [str(x).strip() for x in raw if str(x).strip()]
        if lines:
            return lines
    return _job_highlights(job)


def _merge_experience_keep_richest(
    *job_groups: list,
    ats_substitutions: list[dict] | None = None,
) -> list[dict]:
    """Union bullets from baseline + previous + current experience; apply ATS once."""

    groups = [[j for j in g if isinstance(j, dict)] for g in job_groups if isinstance(g, list) and g]
    if not groups:
        return []

    def total_bullets(group: list[dict]) -> int:
        return sum(len(_experience_bullet_lines(job)) for job in group)

    anchor_group = max(groups, key=total_bullets)
    out: list[dict] = []
    for anchor_job in anchor_group:
        pools: list[list[str]] = []
        company = str(anchor_job.get("company") or "").strip()
        for group in groups:
            for job in group:
                if _companies_loosely_match(company, str(job.get("company") or "")):
                    pools.append(_experience_bullet_lines(job))
                    break
        if ats_substitutions:
            chosen = _finalize_highlight_bullets(
                _union_bullet_lines(*pools),
                ats_substitutions=ats_substitutions,
            )
        elif pools:
            richest = max(pools, key=len)
            latest = pools[-1]
            chosen = richest if len(richest) > len(latest) else latest
            chosen = _dedupe_substring_bullets(_dedupe_bullet_lines(list(chosen)))
        else:
            chosen = []
        row = dict(_normalize_llm_job_entry(anchor_job))
        row["highlights"] = chosen
        out.append(row)
    return out


def canonical_profile_text_from_structured(structured: dict) -> str:
    """Plain text for cabinet/UI — mirrors structured JSON used by PDF render."""
    return structured_profile_to_plain_text(structured).strip()


def profile_dict_from_structured(
    structured: dict,
    *,
    profile_text: str = "",
    desired_role: str | None = None,
    source: str | None = None,
    chat_answers: dict | None = None,
) -> dict:
    """API-представление профиля без записи в PostgreSQL."""
    from job_application.resume.cv_schema import desired_role_from_cv, is_cv_structured, normalize_to_cv

    if is_cv_structured(structured):
        structured = dict(structured)
    else:
        enriched = enrich_structured_personal_from_plain(dict(structured))
        canonical_jobs = _experience_entries_from_structured(enriched)
        if canonical_jobs and not enriched.get("_keep_stored_experience_bullets"):
            enriched["experience"] = canonical_jobs
        structured = normalize_to_cv(enriched)

    structured = attach_experience_baseline(structured, reset=True)

    plain = (profile_text or "").strip() or structured_profile_to_plain_text(structured)
    resolved_answers = chat_answers
    if not resolved_answers:
        resolved_answers = structured_to_chat_answers(structured, desired_role=desired_role)
    resolved_desired = clamp_desired_role(desired_role or desired_role_from_cv(structured) or "")
    template_hint = str(structured.get("resume_template") or structured.get("resume_layout") or "harvard").strip().lower()
    structured = attach_resume_template(structured, fallback=template_hint or "harvard")
    return {
        "structured": structured,
        "profile_text": plain,
        "desired_role": resolved_desired,
        "source": source,
        "chat_answers": resolved_answers or {},
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def profile_dict_from_chat_answers(answers: dict[str, str]) -> dict:
    structured = chat_answers_to_structured(answers)
    pdf_plain = str(answers.get(RESUME_PLAIN_TEXT_KEY) or "").strip()
    if pdf_plain:
        structured = attach_resume_plain_text(structured, pdf_plain)
    structured = attach_resume_template(structured)
    plain = structured_profile_to_plain_text(structured)
    desired_role = clamp_desired_role(
        str(
            answers.get("headline")
            or answers.get("desiredPosition")
            or answers.get("desiredPositions")
            or answers.get("objective")
            or answers.get("position")
            or ""
        )
    )
    return profile_dict_from_structured(
        structured,
        profile_text=plain,
        desired_role=desired_role,
        source="chat",
        chat_answers=answers,
    )


def build_profile_plain_text(profile: ResumeProfile) -> str:
    answers = profile.chat_answers if isinstance(profile.chat_answers, dict) else {}
    if answers:
        return structured_profile_to_plain_text(chat_answers_to_structured(answers)).strip()
    return (profile.profile_text or "").strip()


def structured_for_render_from_profile(profile: ResumeProfile) -> dict:
    """Structured JSON for PDF/DOCX — tailored profile uses stored structured, not stale chat_answers."""
    stored = profile.structured if isinstance(profile.structured, dict) else {}
    answers = profile.chat_answers if isinstance(profile.chat_answers, dict) else {}
    pdf_plain = str(stored.get(RESUME_PLAIN_TEXT_KEY) or answers.get(RESUME_PLAIN_TEXT_KEY) or "").strip()

    if profile.source == "tailored" and stored:
        structured = dict(stored)
    elif answers:
        structured = chat_answers_to_structured(answers)
        if stored:
            structured = _merge_personal_fields(stored, structured)
    else:
        structured = dict(stored)

    if pdf_plain:
        structured = attach_resume_plain_text(structured, pdf_plain)
    template_hint = str(stored.get("resume_template") or stored.get("resume_layout") or "").strip().lower()
    structured = attach_resume_template(structured, fallback=template_hint or None)
    return enrich_structured_personal_from_plain(structured)


_DESIRED_ROLE_LINE = re.compile(r"^\s*Desired role:\s*(.+?)\s*$", re.I | re.M)


def normalize_tailored_profile_text(text: str, *, fallback_desired_role: str = "") -> tuple[str, str]:
    """Remove Desired role lines from body; return (clean_text, desired_role from last line in file)."""
    raw = (text or "").strip()
    matches = list(_DESIRED_ROLE_LINE.finditer(raw))
    desired = matches[-1].group(1).strip() if matches else (fallback_desired_role or "").strip()
    clean = _DESIRED_ROLE_LINE.sub("", raw)
    clean = re.sub(r"\n{3,}", "\n\n", clean).strip()
    return clean, desired


def _merge_cv_structured(old: dict, new: dict) -> dict:
    """Merge cv.yml-shaped profiles, preserving contact fields from the stored profile."""
    from job_application.resume.cv_schema import normalize_to_cv

    old_cv = normalize_to_cv(old)
    new_cv = normalize_to_cv(new)
    merged = dict(new_cv)

    old_b = old_cv.get("basics") if isinstance(old_cv.get("basics"), dict) else {}
    new_b = merged.get("basics") if isinstance(merged.get("basics"), dict) else {}
    out_b = dict(new_b)
    for key in ("name", "email", "phone", "location", "headline", "summary"):
        if not str(out_b.get(key) or "").strip() and str(old_b.get(key) or "").strip():
            out_b[key] = old_b[key]
    if not out_b.get("links") and old_b.get("links"):
        out_b["links"] = old_b["links"]
    merged["basics"] = out_b

    baseline = old.get("_experience_baseline") or old_cv.get("_experience_baseline")
    if isinstance(baseline, list) and baseline:
        merged["_experience_baseline"] = baseline
    return merged


def _merge_personal_fields(old: dict, new: dict) -> dict:
    from job_application.resume.profile_text import _sanitize_contact_location

    merged = dict(new)
    old_p = old.get("personal") if isinstance(old.get("personal"), dict) else {}
    new_p = merged.get("personal") if isinstance(merged.get("personal"), dict) else {}
    out_p = dict(new_p)
    link_keys = () if str(out_p.get("portfolio") or "").strip() else ("linkedin", "github", "xing")
    for key in ("full_name", "first_name", "last_name", "email", "phone", *link_keys, "location"):
        if not str(out_p.get(key) or "").strip() and str(old_p.get(key) or "").strip():
            out_p[key] = old_p[key]
    stored_loc = _sanitize_contact_location(str(old_p.get("location") or old_p.get("city") or ""))
    new_loc = _sanitize_contact_location(str(out_p.get("location") or out_p.get("city") or ""))
    if stored_loc and not new_loc:
        out_p["location"] = stored_loc
    merged["personal"] = out_p
    return merged


def _run_coro_sync(coro):
    """Run async RAG helpers from sync FastAPI routes / tests."""
    import asyncio

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    import nest_asyncio

    nest_asyncio.apply()
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(coro)


def _rebuild_structured_from_tailored_plain(
    row: ResumeProfile,
    plain: str,
    *,
    desired_role: str = "",
    llm_model: str | None = None,
) -> dict:
    from job_application.resume.cv_schema import normalize_to_cv
    from job_application.resume.cv_yaml import harvard_cv_to_structured
    from job_application.resume.rag_prepare import fill_cv_from_text
    from job_application.resume.rag_prepare.normalize import l7_json_to_slim_cv

    old_structured = row.structured if isinstance(row.structured, dict) else {}
    old_answers = row.chat_answers if isinstance(row.chat_answers, dict) else {}
    filled, _plain, _usage = _run_coro_sync(
        fill_cv_from_text(plain, llm_model=llm_model or APP_LLM_MODEL)
    )
    if not isinstance(filled, dict):
        raise ValueError("LLM returned an invalid resume structure")
    extracted = harvard_cv_to_structured(normalize_to_cv(l7_json_to_slim_cv(filled)))

    merged = _merge_cv_structured(old_structured, extracted)
    merged = attach_resume_plain_text(merged, plain)
    canonical_jobs = _experience_entries_from_structured(merged)
    if canonical_jobs:
        merged["experience"] = canonical_jobs

    resolved_role = (desired_role or row.desired_role or "").strip()
    new_answers = structured_to_chat_answers(merged, desired_role=resolved_role)
    for key in ("fullName", "email", "phone", "links", "city"):
        if old_answers.get(key) and not new_answers.get(key):
            new_answers[key] = old_answers[key]
    new_answers = chat_answers_with_resume_plain_text(new_answers, plain)
    merged_payload = profile_dict_from_structured(
        merged,
        profile_text=plain,
        desired_role=resolved_role,
        source="tailored",
        chat_answers=new_answers,
    )
    return merged_payload


def merge_structured_for_scoring(profile: ResumeProfile) -> dict:
    """Structured для JobBERT: chat_answers + _resume_plain_text из сохранённого PDF."""
    return structured_for_render_from_profile(profile)


def attach_resume_plain_text(structured: dict, pdf_plain: str) -> dict:
    """Ensure structured JSON keeps original PDF plain text for JobBERT."""
    data = dict(structured or {})
    plain = (pdf_plain or "").strip()
    if plain:
        data[RESUME_PLAIN_TEXT_KEY] = plain
    return data


def attach_resume_template(structured: dict, *, fallback: str | None = None) -> dict:
    """Lock PDF layout to workshop Harvard cv.yml renderer."""
    from job_application.resume.cv_schema import CV_CHAT_FORMAT

    _ = fallback
    data = dict(structured or {})
    data["resume_template"] = "harvard"
    data["chat_format"] = CV_CHAT_FORMAT
    return data


def chat_answers_with_resume_plain_text(answers: dict[str, str], pdf_plain: str) -> dict[str, str]:
    merged = {k: str(v).strip() for k, v in (answers or {}).items() if str(v).strip()}
    plain = (pdf_plain or "").strip()
    if plain:
        merged[RESUME_PLAIN_TEXT_KEY] = plain
    return merged


def pick_resume_text_for_jobbert(structured: dict | None, profile_text: str = "") -> tuple[str, str]:
    """
    Текст резюме для JobBERT — тот же источник, что в Untitled1_skillmatch_fixed.ipynb:
    сырой PDF-текст (_resume_plain_text), не formatted profile_text.
    """
    data = structured if isinstance(structured, dict) else {}
    pdf_plain = str(data.get(RESUME_PLAIN_TEXT_KEY) or "").strip()
    if len(pdf_plain) >= RESUME_TEXT_MIN_CHARS:
        return pdf_plain, "pdf_plain"
    rebuilt = structured_profile_to_plain_text(data).strip() if data else ""
    if len(rebuilt) >= RESUME_TEXT_MIN_CHARS:
        return rebuilt, "profile_rebuild"
    fallback = (profile_text or "").strip()
    if len(fallback) >= RESUME_TEXT_MIN_CHARS:
        return fallback, "profile_text"
    return "", "none"


def resolve_resume_text_for_jobbert_scoring(
    db: Session,
    user: User | None,
    resume_text: str | None,
    *,
    resume_plain_text: str | None = None,
) -> tuple[str | None, dict | None, str]:
    """
    Резюме для POST /analyze/job-description (JobBERT).

    Как в Untitled_skillmatch.ipynb: сырой PDF-текст (_resume_plain_text), не formatted profile.
    """
    _ = resume_plain_text
    structured: dict | None = None
    prof = None
    if user is not None:
        prof = db_users.get_profile_for_user(db, user.id)
        if prof is not None:
            structured = _structured_for_scoring_from_profile(prof)

    explicit = (resume_text or "").strip()
    if len(explicit) >= RESUME_TEXT_MIN_CHARS:
        return explicit, structured, "profile_parsed"

    if prof is not None:
        text, source = pick_resume_text_for_jobbert(structured, prof.profile_text or "")
        if len(text) >= RESUME_TEXT_MIN_CHARS:
            return text, structured, source

    return None, structured, "none"


def _structured_for_scoring_from_profile(prof: ResumeProfile) -> dict:
    """Same canonical structured as PDF render — tailored profile must not use stale chat_answers."""
    return structured_for_render_from_profile(prof)


def resolve_resume_text_for_scoring(
    db: Session,
    user: User | None,
    resume_text: str | None,
) -> tuple[str | None, dict | None]:
    """
    Форматированный текст резюме для письма / LLM (profile_text).
    Для JobBERT score используйте resolve_resume_text_for_jobbert_scoring.

    Явный resume_text в запросе имеет приоритет над профилем в кабинете
    (пересчёт score с подогнанным резюме на шаге 2).
    """
    structured: dict | None = None
    prof = None
    if user is not None:
        prof = db_users.get_profile_for_user(db, user.id)

    explicit = (resume_text or "").strip()
    if len(explicit) >= RESUME_TEXT_MIN_CHARS:
        if prof is not None:
            structured = _structured_for_scoring_from_profile(prof)
        return explicit, structured

    if prof is not None:
        structured = _structured_for_scoring_from_profile(prof)
        text, _ = pick_resume_text_for_jobbert(structured, prof.profile_text or "")
        if len(text) >= RESUME_TEXT_MIN_CHARS:
            return text, structured

    return None, structured


def update_profile_plain_text(
    db: Session,
    user_id: str,
    profile_text: str,
    *,
    reparse_structured: bool = True,
    llm_model: str | None = None,
    ats_substitutions: list[dict] | None = None,
) -> ResumeProfile:
    """Обновить plain-text резюме в кабинете (после AI-подгонки на шаге 2)."""
    row = db_users.get_profile_for_user(db, user_id)
    if row is None:
        raise ValueError("Profile not found. Create a resume via chat or PDF first.")

    plain, desired_role = normalize_tailored_profile_text(
        profile_text,
        fallback_desired_role=row.desired_role or "",
    )
    if len(plain) < RESUME_TEXT_MIN_CHARS:
        raise ValueError(f"profile_text is too short (minimum {RESUME_TEXT_MIN_CHARS} characters)")

    if reparse_structured:
        try:
            payload = _rebuild_structured_from_tailored_plain(
                row, plain, desired_role=desired_role, llm_model=llm_model
            )
            if desired_role:
                payload["desired_role"] = desired_role
            return db_users.upsert_profile(
                db,
                user_id,
                structured=payload["structured"],
                profile_text=payload["profile_text"],
                desired_role=payload.get("desired_role") or desired_role or row.desired_role,
                source="tailored",
                chat_answers=payload.get("chat_answers"),
            )
        except Exception:
            pass

    from job_application.resume.profile_text import skills_from_plain_resume_text, structured_skills_list

    structured = dict(row.structured) if isinstance(row.structured, dict) else {}
    # profile_text column = tailored body; keep original PDF extract in _resume_plain_text for scoring/render.
    old_pdf_plain = str(structured.get(RESUME_PLAIN_TEXT_KEY) or "").strip()
    # Preserve experience/education JSON when only plain text was tailored (ATS edits).
    if isinstance(row.structured, dict):
        for key in ("experience", "education", "personal", "summary", "courses"):
            if key in row.structured and key not in structured:
                structured[key] = row.structured[key]
    plain_skills = skills_from_plain_resume_text(plain)
    if plain_skills:
        merged = list(dict.fromkeys(structured_skills_list(structured) + plain_skills))
        if merged:
            structured["skills"] = merged

    old_jobs = (row.structured or {}).get("experience") if isinstance(row.structured, dict) else []
    baseline_jobs = experience_baseline_jobs(structured)
    new_jobs = structured.get("experience") if isinstance(structured.get("experience"), list) else []
    # Baseline restores dropped bullets only when applying ATS; otherwise keep current PDF wording.
    if ats_substitutions:
        merge_groups = [g for g in (baseline_jobs, old_jobs, new_jobs) if isinstance(g, list) and g]
    else:
        merge_groups = [g for g in (old_jobs, new_jobs) if isinstance(g, list) and g]
    if merge_groups:
        structured["experience"] = _merge_experience_keep_richest(
            *merge_groups,
            ats_substitutions=ats_substitutions,
        )
        structured = _sync_experience_narrative_fields(structured)
        structured = _sync_experience_text_field(structured)
    elif isinstance(structured.get("experience"), list):
        structured = _sync_experience_narrative_fields(structured)
        structured = _sync_experience_text_field(structured)

    canonical_plain = canonical_profile_text_from_structured(structured)
    if ats_substitutions:
        plain_for_db = canonical_plain if len(canonical_plain) >= RESUME_TEXT_MIN_CHARS else plain
    else:
        # LLM tailor / ручная правка: structured ещё старый — сохраняем переданный plain.
        structured = attach_resume_plain_text(structured, plain)
        plain_for_db = plain

    old_answers = dict(row.chat_answers) if isinstance(row.chat_answers, dict) else {}
    answers = structured_to_chat_answers(structured, desired_role=desired_role or row.desired_role)
    for key in ("fullName", "email", "phone", "links", "city", "linkedin", "github"):
        if old_answers.get(key) and not answers.get(key):
            answers[key] = old_answers[key]
    if ats_substitutions:
        if old_pdf_plain:
            answers = chat_answers_with_resume_plain_text(answers, old_pdf_plain)
    else:
        answers = chat_answers_with_resume_plain_text(answers, plain)
    if not answers and old_answers:
        answers = old_answers

    template_hint = str(
        (row.structured or {}).get("resume_template")
        or (row.structured or {}).get("resume_layout")
        or structured.get("resume_template")
        or ""
    ).strip().lower()
    structured = attach_resume_template(structured, fallback=template_hint or None)
    if ats_substitutions:
        structured["_keep_stored_experience_bullets"] = True

    return db_users.upsert_profile(
        db,
        user_id,
        structured=structured,
        profile_text=plain_for_db,
        desired_role=desired_role or row.desired_role,
        source="tailored",
        chat_answers=answers if answers else row.chat_answers,
    )


def save_profile_from_chat_answers(
    db: Session,
    user_id: str,
    answers: dict[str, str],
    *,
    resume_plain_text: str | None = None,
) -> ResumeProfile:
    plain_from_answers = str(answers.get(RESUME_PLAIN_TEXT_KEY) or "").strip()
    pdf_plain = (resume_plain_text or plain_from_answers or "").strip()
    payload = profile_dict_from_chat_answers(answers)
    if pdf_plain:
        payload["structured"] = attach_resume_plain_text(payload["structured"], pdf_plain)
        payload["chat_answers"] = chat_answers_with_resume_plain_text(payload["chat_answers"], pdf_plain)

    existing = db_users.get_profile_for_user(db, user_id)
    if existing and isinstance(existing.structured, dict):
        old_plain = str(existing.structured.get(RESUME_PLAIN_TEXT_KEY) or "").strip()
        if old_plain and not str(payload["structured"].get(RESUME_PLAIN_TEXT_KEY) or "").strip():
            payload["structured"] = attach_resume_plain_text(payload["structured"], old_plain)
            payload["chat_answers"] = chat_answers_with_resume_plain_text(payload["chat_answers"], old_plain)
        payload["structured"] = attach_resume_template(payload["structured"])
        if not str(answers.get("summary") or "").strip():
            old_summary = str(existing.structured.get("summary") or "").strip()
            if old_summary:
                payload["structured"]["summary"] = old_summary
                payload["profile_text"] = structured_profile_to_plain_text(payload["structured"])
    row = db_users.upsert_profile(
        db,
        user_id,
        structured=payload["structured"],
        profile_text=payload["profile_text"],
        desired_role=payload["desired_role"] or None,
        source=payload["source"],
        chat_answers=payload["chat_answers"],
    )
    from job_application.resume.cv_preview_files import write_cv_preview_files

    write_cv_preview_files(payload["structured"])
    return row
