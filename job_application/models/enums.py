"""Status enums."""

from __future__ import annotations

from enum import StrEnum


class JobStatus(StrEnum):
    DRAFT = "draft"
    QUEUED = "queued"
    PROCESSING = "processing"
    NEEDS_REVIEW = "needs_review"
    DONE = "done"
    ERROR = "error"
    # Application tracker — synced to application_jobs.status after cv_tailored
    INTERESTED = "interested"
    APPLIED = "applied"
    INTERVIEW = "interview"
    OFFER = "offer"
    REJECTED = "rejected"


class PipelineStatus(StrEnum):
    """UI tracker statuses (same string values as JobStatus after listing)."""

    INTERESTED = "interested"
    APPLIED = "applied"
    INTERVIEW = "interview"
    OFFER = "offer"
    REJECTED = "rejected"


# Statuses that still allow editing offer-draft / tracker for a listed vacancy
LISTED_JOB_STATUSES = frozenset(
    {
        JobStatus.DRAFT,
        JobStatus.INTERESTED,
        JobStatus.APPLIED,
        JobStatus.INTERVIEW,
        JobStatus.OFFER,
        JobStatus.REJECTED,
    }
)
