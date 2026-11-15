"""Dataclasses for jobs and API payloads."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from job_application.models.enums import JobStatus
from job_application.models.exceptions import InvalidJobState


@dataclass(frozen=True, slots=True)
class FormField:
    id: str
    label: str
    hint: str = ""


@dataclass
class JobRecord:
    id: str
    jd_text: str
    status: JobStatus
    user_id: str | None = None
    llm_model: str | None = None
    error_message: str | None = None
    outputs: dict | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def start_processing(self) -> None:
        if self.status not in {JobStatus.QUEUED, JobStatus.DRAFT}:
            raise InvalidJobState(f"Cannot start processing from {self.status}")
        self.status = JobStatus.PROCESSING
        self.error_message = None

    def mark_needs_review(self, outputs: dict) -> None:
        if self.status != JobStatus.PROCESSING:
            raise InvalidJobState(f"Cannot request review from {self.status}")
        self.status = JobStatus.NEEDS_REVIEW
        self.error_message = None
        self.outputs = outputs

    def mark_done(self, outputs: dict | None = None) -> None:
        if self.status != JobStatus.NEEDS_REVIEW:
            raise InvalidJobState(f"Cannot complete from {self.status}")
        self.status = JobStatus.DONE
        self.error_message = None
        if outputs is not None:
            self.outputs = outputs
        elif self.outputs:
            hitl = dict(self.outputs.get("hitl") or {})
            hitl["awaiting_feedback"] = False
            hitl["finalized_at"] = "user"
            self.outputs = {**self.outputs, "hitl": hitl}

    def mark_error(self, reason: str) -> None:
        self.status = JobStatus.ERROR
        self.error_message = reason

    def restart_for_hitl(self) -> None:
        if self.status != JobStatus.NEEDS_REVIEW:
            raise InvalidJobState(f"HITL revise only from needs_review, got {self.status}")
        self.status = JobStatus.PROCESSING
        self.error_message = None


@dataclass(frozen=True, slots=True)
class CreateJobInput:
    user_id: str | None
    jd_text: str
    llm_model: str
    resume_pdf: bytes | None = None
    resume_text: str | None = None
    resume_profile_json: str | None = None
    form_pdf: bytes | None = None
    fields_override: dict | None = None
    has_resume_upload: bool = False


@dataclass(frozen=True, slots=True)
class CreateJobResult:
    job_id: str
    status: str
    model: str
    has_application_form_pdf: bool
    resume_source: str
    user_id: str | None


@dataclass(frozen=True, slots=True)
class OfferDraftPatch:
    jd_text: str | None = None
    analysis: dict | None = None
    cover_letter_text: str | None = None
    tailored_resume_text: str | None = None
    resume_paste: str | None = None
    model: str | None = None


@dataclass(frozen=True, slots=True)
class HitlFeedbackInput:
    finalize: bool = False
    message: str = ""


@dataclass(frozen=True, slots=True)
class HitlFeedbackResult:
    ok: bool = True
    status: str = "done"
    verdict: str | None = None
    schedule_rerun: bool = False
    rerun_message: str = ""


@dataclass(frozen=True, slots=True)
class ReplaceAnswersInput:
    job_id: str
    payload: dict
    regenerate_pdf: bool = False
