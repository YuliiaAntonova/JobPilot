"""Job use cases — JD / offer drafts + application tracker (slim build)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from job_application.application import offer_draft as offer_draft_store
from job_application.models.enums import LISTED_JOB_STATUSES, JobStatus, PipelineStatus
from job_application.models.exceptions import InvalidJobState, JobNotFound
from job_application.models.schemas import JobRecord, OfferDraftPatch
from job_application.repositories.jobs import JobRepository

_PIPELINE_VALUES = {s.value for s in PipelineStatus}


def _sync_row_status_from_tracker(job: JobRecord, tracker: dict[str, Any] | None) -> bool:
    """Set application_jobs.status = tracker.pipeline_status. Returns True if changed."""
    if not tracker:
        return False
    ps = str(tracker.get("pipeline_status") or "").strip()
    if ps not in _PIPELINE_VALUES:
        return False
    new_status = JobStatus(ps)
    if job.status == new_status:
        return False
    job.status = new_status
    return True


def _dedupe_key(row: dict[str, Any]) -> tuple[str, str]:
    return (
        str(row.get("company_name") or "").strip().casefold(),
        str(row.get("job_title") or "").strip().casefold(),
    )


class JobService:
    def __init__(
        self,
        db: Session | None = None,
        *,
        jobs: JobRepository | None = None,
    ) -> None:
        if jobs is None:
            if db is None:
                raise ValueError("JobService requires db or jobs")
            jobs = JobRepository(db)
        self._jobs = jobs
        self._db = db

    def save_jd_draft(
        self,
        user_id: str,
        *,
        jd_text: str,
        analysis: dict | None = None,
        llm_model: str,
    ) -> dict[str, Any]:
        jd_clean = jd_text.strip()
        flow_patch: dict = {}
        if analysis:
            flow_patch["analysis"] = analysis

        # Reuse only an open (not-yet-listed) draft — listed/tailored rows stay in the company list.
        find_open = getattr(self._jobs, "find_latest_open_draft", None)
        if callable(find_open):
            existing = find_open(user_id)
        else:
            existing = self._jobs.find_latest_draft(user_id)
            if existing is not None and offer_draft_store.draft_is_listed(existing.outputs):
                existing = None

        if existing is not None:
            existing.jd_text = jd_clean
            existing.updated_at = datetime.now(timezone.utc)
            if flow_patch:
                outputs = dict(existing.outputs or {})
                flow = offer_draft_store.merge_offer_flow(
                    offer_draft_store.read_offer_flow(outputs),
                    flow_patch,
                    jd_text=jd_clean,
                )
                outputs[offer_draft_store.OFFER_FLOW_KEY] = flow
                existing.outputs = outputs
            self._jobs.save(existing)
            return {
                "job_id": existing.id,
                "status": existing.status.value,
                "jd_chars": len(jd_clean),
                "reused": True,
            }

        job_id = uuid.uuid4().hex
        outputs_val = None
        if flow_patch:
            outputs_val = {
                offer_draft_store.OFFER_FLOW_KEY: offer_draft_store.merge_offer_flow(
                    {}, flow_patch, jd_text=jd_clean
                ),
            }
        job = JobRecord(
            id=job_id,
            user_id=user_id,
            jd_text=jd_clean,
            status=JobStatus.DRAFT,
            llm_model=llm_model,
            outputs=outputs_val,
        )
        self._jobs.create(job)
        return {
            "job_id": job_id,
            "status": JobStatus.DRAFT.value,
            "jd_chars": len(jd_clean),
            "reused": False,
        }

    def get_latest_offer_draft(self, user_id: str) -> dict[str, Any]:
        find_open = getattr(self._jobs, "find_latest_open_draft", None)
        row = find_open(user_id) if callable(find_open) else None
        if row is None:
            row = self._jobs.find_latest_draft(user_id)
        if row is None:
            return {"draft": None}
        return {"draft": self._offer_draft(row)}

    def get_offer_draft(self, job_id: str) -> dict[str, Any]:
        return self._offer_draft(self._require(job_id))

    def save_offer_draft(self, job_id: str, patch: OfferDraftPatch) -> dict[str, Any]:
        job = self._require(job_id)
        if job.status not in LISTED_JOB_STATUSES:
            raise InvalidJobState(
                f"offer-draft is not available for status {job.status.value}"
            )

        flow_patch: dict = {}
        if patch.analysis is not None:
            flow_patch["analysis"] = patch.analysis
        if patch.cover_letter_text is not None:
            flow_patch["cover_letter_text"] = patch.cover_letter_text
        if patch.tailored_resume_text is not None:
            flow_patch["tailored_resume_text"] = patch.tailored_resume_text
        if patch.resume_paste is not None:
            flow_patch["resume_paste"] = patch.resume_paste
        if patch.model is not None:
            flow_patch["model"] = patch.model

        outputs = dict(job.outputs or {})
        jd_for_tracker = (patch.jd_text or job.jd_text or "").strip()
        flow = offer_draft_store.merge_offer_flow(
            offer_draft_store.read_offer_flow(outputs),
            flow_patch,
            jd_text=jd_for_tracker,
        )
        outputs[offer_draft_store.OFFER_FLOW_KEY] = flow
        job.outputs = outputs

        if patch.jd_text and patch.jd_text.strip():
            job.jd_text = patch.jd_text.strip()

        # After cv_tailored, column status follows tracker.pipeline_status
        _sync_row_status_from_tracker(job, offer_draft_store.read_tracker(flow))

        job.updated_at = datetime.now(timezone.utc)
        self._jobs.save(job)
        return {"ok": True, "draft": self._offer_draft(job)}

    def list_applications(
        self,
        user_id: str,
        *,
        include_closed: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        rows = self._jobs.list_for_user(user_id, limit=max(limit, 200), offset=0)
        items: list[dict[str, Any]] = []
        jobs_by_id = {j.id: j for j in rows}

        for job in rows:
            outputs = dict(job.outputs or {})
            flow = offer_draft_store.read_offer_flow(outputs)
            if offer_draft_store.draft_is_listed(outputs):
                before = offer_draft_store.read_tracker(flow)
                repaired = offer_draft_store.ensure_tracker_on_tailored(
                    flow, jd_text=job.jd_text or ""
                )
                after = offer_draft_store.read_tracker(repaired)
                status_changed = _sync_row_status_from_tracker(job, after)
                if after != before or status_changed:
                    outputs[offer_draft_store.OFFER_FLOW_KEY] = repaired
                    job.outputs = outputs
                    self._jobs.save(job)

            row = offer_draft_store.build_application_row(job.id, job.jd_text, job.outputs)
            if row is None:
                continue
            row["status"] = job.status.value
            items.append(row)

        # Collapse duplicates: same company+title → keep newest, close older
        items.sort(key=lambda r: str(r.get("listed_at") or ""), reverse=True)
        seen: set[tuple[str, str]] = set()
        unique: list[dict[str, Any]] = []
        for row in items:
            key = _dedupe_key(row)
            if key == ("", ""):
                unique.append(row)
                continue
            if key in seen:
                job = jobs_by_id.get(row["job_id"])
                if job is not None and not row.get("closed"):
                    self._close_duplicate(job)
                continue
            seen.add(key)
            unique.append(row)

        if not include_closed:
            unique = [r for r in unique if not r.get("closed")]

        sliced = unique[offset : offset + limit]
        return {"items": sliced, "total": len(unique)}

    def _close_duplicate(self, job: JobRecord) -> None:
        outputs = dict(job.outputs or {})
        flow = offer_draft_store.read_offer_flow(outputs)
        tracker = offer_draft_store.read_tracker(flow)
        if tracker.get("closed"):
            return
        tracker = offer_draft_store.merge_tracker_patch(tracker, {"closed": True})
        flow = dict(flow)
        flow[offer_draft_store.TRACKER_KEY] = tracker
        outputs[offer_draft_store.OFFER_FLOW_KEY] = flow
        job.outputs = outputs
        _sync_row_status_from_tracker(job, tracker)
        job.updated_at = datetime.now(timezone.utc)
        self._jobs.save(job)

    def patch_tracker(self, job_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        job = self._require(job_id)
        outputs = dict(job.outputs or {})
        flow = offer_draft_store.read_offer_flow(outputs)
        if not offer_draft_store.draft_is_listed(outputs):
            raise InvalidJobState("Tracker is available after cv_tailored is generated")

        try:
            tracker = offer_draft_store.merge_tracker_patch(
                offer_draft_store.read_tracker(flow),
                patch,
            )
        except ValueError as e:
            raise InvalidJobState(str(e)) from e

        flow = dict(flow)
        flow[offer_draft_store.TRACKER_KEY] = tracker
        outputs[offer_draft_store.OFFER_FLOW_KEY] = flow
        job.outputs = outputs

        # Always mirror pipeline_status → application_jobs.status
        ps = str(tracker.get("pipeline_status") or "").strip()
        if ps in _PIPELINE_VALUES:
            job.status = JobStatus(ps)

        job.updated_at = datetime.now(timezone.utc)
        self._jobs.save(job)
        # Second write: guarantees column update even if ORM identity-map is stale
        if ps in _PIPELINE_VALUES and hasattr(self._jobs, "update_status"):
            self._jobs.update_status(job_id, ps)

        verified = self._jobs.get(job_id) or job
        row = offer_draft_store.build_application_row(
            verified.id, verified.jd_text, verified.outputs
        )
        if row is not None:
            row["status"] = verified.status.value
        return {"ok": True, "item": row}

    def _require(self, job_id: str) -> JobRecord:
        job = self._jobs.get(job_id)
        if job is None:
            raise JobNotFound(f"Job {job_id} not found")
        return job

    def _offer_draft(self, job: JobRecord) -> dict[str, Any]:
        return offer_draft_store.build_offer_draft_payload(job.id, job.jd_text, job.outputs)
