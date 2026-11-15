"""Job persistence."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import desc, func, select, update
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from job_application.application import offer_draft as offer_draft_store
from job_application.models.db import Job
from job_application.models.enums import JobStatus
from job_application.models.schemas import JobRecord


def _to_record(row: Job) -> JobRecord:
    return JobRecord(
        id=row.id,
        user_id=row.user_id,
        jd_text=row.jd_text,
        status=JobStatus(row.status),
        llm_model=row.llm_model,
        error_message=row.error_message,
        outputs=dict(row.outputs) if row.outputs else None,
        created_at=row.created_at,  # type: ignore[arg-type]
        updated_at=row.updated_at,  # type: ignore[arg-type]
    )


def _apply(row: Job, job: JobRecord) -> None:
    row.status = job.status.value
    row.jd_text = job.jd_text
    row.llm_model = job.llm_model
    row.error_message = job.error_message
    row.outputs = job.outputs
    if job.user_id is not None:
        row.user_id = job.user_id


class JobRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get(self, job_id: str) -> JobRecord | None:
        row = self._db.scalars(select(Job).where(Job.id == job_id)).first()
        return _to_record(row) if row else None

    def save(self, job: JobRecord) -> None:
        row = self._db.scalars(select(Job).where(Job.id == job.id)).first()
        if row is None:
            raise LookupError(f"Job {job.id} not found")
        _apply(row, job)
        if job.outputs is not None:
            flag_modified(row, "outputs")
        row.updated_at = datetime.now(timezone.utc)
        self._db.commit()
        self._db.refresh(row)

    def update_status(self, job_id: str, status: str) -> None:
        """Force-write application_jobs.status (keeps column in sync with tracker UI)."""
        now = datetime.now(timezone.utc)
        self._db.execute(
            update(Job)
            .where(Job.id == job_id)
            .values(status=status, updated_at=now)
        )
        self._db.commit()

    def find_latest_draft(self, user_id: str) -> JobRecord | None:
        row = self._db.scalars(
            select(Job)
            .where(Job.user_id == user_id, Job.status == JobStatus.DRAFT.value)
            .order_by(desc(Job.updated_at))
        ).first()
        return _to_record(row) if row else None

    def find_latest_open_draft(self, user_id: str) -> JobRecord | None:
        """Latest DRAFT that is not yet sealed into the company list (no tailored/tracker)."""
        rows = self._db.scalars(
            select(Job)
            .where(Job.user_id == user_id, Job.status == JobStatus.DRAFT.value)
            .order_by(desc(Job.updated_at))
            .limit(50)
        ).all()
        for row in rows:
            rec = _to_record(row)
            if not offer_draft_store.draft_is_listed(rec.outputs):
                return rec
        return None

    def list_for_user(
        self,
        user_id: str,
        *,
        query: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[JobRecord]:
        stmt = select(Job).where(Job.user_id == user_id).order_by(Job.created_at.desc())
        if query and query.strip():
            stmt = stmt.where(Job.jd_text.ilike(f"%{query.strip()}%"))
        stmt = stmt.limit(limit).offset(offset)
        return [_to_record(row) for row in self._db.scalars(stmt).all()]

    def count_for_user(self, user_id: str, *, query: str | None = None) -> int:
        stmt = select(func.count()).select_from(Job).where(Job.user_id == user_id)
        if query and query.strip():
            stmt = stmt.where(Job.jd_text.ilike(f"%{query.strip()}%"))
        return int(self._db.scalar(stmt) or 0)

    def create(self, job: JobRecord) -> JobRecord:
        row = Job(
            id=job.id,
            user_id=job.user_id,
            status=job.status.value,
            jd_text=job.jd_text,
            llm_model=job.llm_model,
            error_message=job.error_message,
            outputs=job.outputs,
        )
        self._db.add(row)
        self._db.commit()
        self._db.refresh(row)
        return _to_record(row)
