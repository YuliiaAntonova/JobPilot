"""FastAPI dependencies (auth, DB, job access)."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError
from sqlalchemy import select
from sqlalchemy.orm import Session

from job_application.utils.auth import decode_access_token
from job_application.models.db import get_db
from job_application.repositories import users as db_users
from job_application.models import Job, User

_bearer = HTTPBearer(auto_error=False)


def _user_from_token(db: Session, token: str | None) -> User | None:
    if not token:
        return None
    try:
        payload = decode_access_token(token)
        user_id = str(payload.get("sub") or "")
    except InvalidTokenError:
        return None
    if not user_id:
        return None
    return db_users.get_user_by_id(db, user_id)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    access_token: str | None = Query(None, description="JWT for PDF download in iframe"),
    db: Session = Depends(get_db),
) -> User:
    token = None
    if credentials is not None and credentials.scheme.lower() == "bearer":
        token = credentials.credentials
    elif access_token:
        token = access_token
    user = _user_from_token(db, token)
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required (Bearer token)")
    return user


def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    access_token: str | None = Query(None, description="JWT for PDF download in iframe"),
    db: Session = Depends(get_db),
) -> User | None:
    token = None
    if credentials is not None and credentials.scheme.lower() == "bearer":
        token = credentials.credentials
    elif access_token:
        token = access_token
    return _user_from_token(db, token)


def assert_job_access(row: Job, user: User | None) -> None:
    """Jobs with user_id are owner-only; legacy jobs without user_id are accessible by id."""
    if row.user_id is None:
        return
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required to access this application")
    if row.user_id != user.id:
        raise HTTPException(status_code=403, detail="No access to this application")


def get_job_with_access(
    job_id: str,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_optional_user),
) -> Job:
    row = db.scalars(select(Job).where(Job.id == job_id)).first()
    if row is None:
        raise HTTPException(status_code=404, detail="job not found")
    assert_job_access(row, user)
    return row
