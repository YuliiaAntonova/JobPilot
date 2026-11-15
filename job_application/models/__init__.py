"""Models package — DB connection, ORM tables, dataclasses."""

from job_application.models.db import (
    Base,
    Job,
    ResumeProfile,
    SessionLocal,
    User,
    engine,
    get_db,
)
from job_application.models.enums import JobStatus, PipelineStatus
from job_application.models.exceptions import (
    ApplicationError,
    ArtifactNotFound,
    InvalidApplicationForm,
    InvalidJobState,
    JobNotFound,
    ResumeMissing,
)
from job_application.models.schemas import (
    CreateJobInput,
    CreateJobResult,
    FormField,
    HitlFeedbackInput,
    HitlFeedbackResult,
    JobRecord,
    OfferDraftPatch,
    ReplaceAnswersInput,
)

__all__ = [
    "ApplicationError",
    "ArtifactNotFound",
    "Base",
    "CreateJobInput",
    "CreateJobResult",
    "FormField",
    "HitlFeedbackInput",
    "HitlFeedbackResult",
    "InvalidApplicationForm",
    "InvalidJobState",
    "Job",
    "JobNotFound",
    "JobRecord",
    "JobStatus",
    "OfferDraftPatch",
    "PipelineStatus",
    "ReplaceAnswersInput",
    "ResumeMissing",
    "ResumeProfile",
    "SessionLocal",
    "User",
    "engine",
    "get_db",
]
