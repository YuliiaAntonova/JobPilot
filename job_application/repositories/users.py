"""CRUD for users and resume profiles."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from job_application.models import ResumeProfile, User
from job_application.config import RESUME_PLAIN_TEXT_KEY, RESUME_TEXT_MIN_CHARS
from job_application.documents.resume_normalize import _has_structured_experience_bullets
from job_application.resume.profile_text import clamp_desired_role, structured_profile_to_plain_text


def _profile_plain_for_api(
    structured: dict | None,
    profile_text_col: str,
    *,
    source: str | None = None,
) -> str:
    """
    Text shown in cabinet / «Подставлять из кабинета».
    Prefer structured rebuild (all experience bullets) over raw _resume_plain_text PDF extract.
    """
    data = structured if isinstance(structured, dict) else {}
    col = (profile_text_col or "").strip()
    rebuilt = structured_profile_to_plain_text(data).strip() if data else ""

    if _has_structured_experience_bullets(data) and len(rebuilt) >= RESUME_TEXT_MIN_CHARS:
        return rebuilt

    if source == "tailored" and len(col) >= RESUME_TEXT_MIN_CHARS:
        return col

    pdf_plain = str(data.get(RESUME_PLAIN_TEXT_KEY) or "").strip()
    if len(pdf_plain) >= RESUME_TEXT_MIN_CHARS:
        return pdf_plain
    if len(col) >= RESUME_TEXT_MIN_CHARS:
        return col
    if len(rebuilt) >= RESUME_TEXT_MIN_CHARS:
        return rebuilt
    return col or pdf_plain or rebuilt


def get_user_by_id(db: Session, user_id: str) -> User | None:
    return db.scalars(select(User).where(User.id == user_id)).first()


def get_user_by_email(db: Session, email: str) -> User | None:
    em = email.strip().lower()
    return db.scalars(select(User).where(User.email == em)).first()


def create_user(db: Session, email: str, password_hash: str) -> User:
    user = User(
        id=str(uuid.uuid4()),
        email=email.strip().lower(),
        password_hash=password_hash,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_profile_for_user(db: Session, user_id: str) -> ResumeProfile | None:
    return db.scalars(select(ResumeProfile).where(ResumeProfile.user_id == user_id)).first()


def upsert_profile(
    db: Session,
    user_id: str,
    *,
    structured: dict,
    profile_text: str,
    desired_role: str | None = None,
    source: str | None = None,
    chat_answers: dict | None = None,
) -> ResumeProfile:
    row = get_profile_for_user(db, user_id)
    now = datetime.now(timezone.utc)
    incoming = dict(structured or {})
    incoming_answers = dict(chat_answers or {}) if chat_answers is not None else None
    if desired_role is not None:
        desired_role = clamp_desired_role(desired_role) or None

    if row is not None and isinstance(row.structured, dict):
        old_plain = str(row.structured.get(RESUME_PLAIN_TEXT_KEY) or "").strip()
        if old_plain and not str(incoming.get(RESUME_PLAIN_TEXT_KEY) or "").strip():
            incoming[RESUME_PLAIN_TEXT_KEY] = old_plain
            if incoming_answers is not None and RESUME_PLAIN_TEXT_KEY not in incoming_answers:
                incoming_answers[RESUME_PLAIN_TEXT_KEY] = old_plain

    if row is None:
        row = ResumeProfile(
            id=str(uuid.uuid4()),
            user_id=user_id,
            structured=incoming,
            profile_text=profile_text,
            desired_role=desired_role,
            source=source,
            chat_answers=incoming_answers if incoming_answers is not None else chat_answers,
            updated_at=now,
        )
        db.add(row)
    else:
        row.structured = incoming
        row.profile_text = profile_text
        if desired_role is not None:
            row.desired_role = desired_role
        if source is not None:
            row.source = source
        if incoming_answers is not None:
            row.chat_answers = incoming_answers
        row.updated_at = now
    db.commit()
    db.refresh(row)
    return row


def update_profile_fields(
    db: Session,
    user_id: str,
    *,
    desired_role: str | None = None,
) -> ResumeProfile | None:
    row = get_profile_for_user(db, user_id)
    if row is None:
        return None
    if desired_role is not None:
        row.desired_role = clamp_desired_role(desired_role) or None
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return row


def delete_profile_for_user(db: Session, user_id: str) -> bool:
    row = get_profile_for_user(db, user_id)
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True


def profile_to_api_dict(row: ResumeProfile | None) -> dict | None:
    if row is None:
        return None
    updated = row.updated_at
    structured = row.structured if isinstance(row.structured, dict) else {}
    plain = _profile_plain_for_api(structured, row.profile_text or "", source=row.source)
    return {
        "structured": structured or {},
        "profile_text": plain,
        "desired_role": row.desired_role or "",
        "source": row.source,
        "chat_answers": row.chat_answers or {},
        "updated_at": updated.isoformat() if updated else None,
    }
