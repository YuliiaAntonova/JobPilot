"""Tests for JobService draft methods + application tracker (slim build)."""

from __future__ import annotations

from datetime import date

import pytest

from job_application.application.job_service import JobService
from job_application.application import offer_draft as offer_draft_store
from job_application.models.enums import JobStatus, PipelineStatus
from job_application.models.exceptions import InvalidJobState
from job_application.models.schemas import JobRecord, OfferDraftPatch


class _FakeJobs:
    def __init__(self, job: JobRecord | None = None) -> None:
        self._jobs: dict[str, JobRecord] = {}
        if job is not None:
            self._jobs[job.id] = job

    def get(self, job_id: str) -> JobRecord | None:
        return self._jobs.get(job_id)

    def save(self, job: JobRecord) -> None:
        self._jobs[job.id] = job

    def find_latest_draft(self, user_id: str) -> JobRecord | None:
        drafts = [
            j
            for j in self._jobs.values()
            if j.status == JobStatus.DRAFT and j.user_id == user_id
        ]
        if not drafts:
            return None
        drafts.sort(key=lambda j: str(j.updated_at or j.created_at or j.id), reverse=True)
        return drafts[0]

    def find_latest_open_draft(self, user_id: str) -> JobRecord | None:
        drafts = [
            j
            for j in self._jobs.values()
            if j.status == JobStatus.DRAFT and j.user_id == user_id
        ]
        drafts.sort(key=lambda j: str(j.updated_at or j.created_at or j.id), reverse=True)
        for j in drafts:
            if not offer_draft_store.draft_is_listed(j.outputs):
                return j
        return None

    def create(self, job: JobRecord) -> JobRecord:
        self._jobs[job.id] = job
        return job

    def list_for_user(self, user_id: str, *, query: str | None = None, limit: int = 50, offset: int = 0):
        rows = [j for j in self._jobs.values() if j.user_id == user_id]
        rows.sort(key=lambda j: str(j.created_at or j.id), reverse=True)
        return rows[offset : offset + limit]


def test_save_offer_draft_rejects_processing():
    job = JobRecord(id="j1", jd_text="x", status=JobStatus.PROCESSING)
    service = JobService(jobs=_FakeJobs(job))
    with pytest.raises(InvalidJobState):
        service.save_offer_draft("j1", OfferDraftPatch(analysis={"score": 1}))


def test_patch_tracker_syncs_column_status():
    job = JobRecord(
        id="j1",
        user_id="u1",
        jd_text="AI Engineer\nAbout the job\nSumsub is great.\n",
        status=JobStatus.DRAFT,
        outputs={
            offer_draft_store.OFFER_FLOW_KEY: {
                "analysis": {},
                "tailored_resume_text": "Tailored " + ("x" * 100),
                "tracker": {
                    "company_name": "Sumsub",
                    "job_title": "AI Engineer",
                    "pipeline_status": "interested",
                    "applied_at": None,
                    "closed": False,
                    "listed_at": "2026-11-15T12:00:00+00:00",
                },
            }
        },
    )
    service = JobService(jobs=_FakeJobs(job))
    out = service.patch_tracker("j1", {"pipeline_status": "applied"})
    assert out["item"]["pipeline_status"] == "applied"
    assert out["item"]["status"] == "applied"
    assert service._jobs.get("j1").status == JobStatus.APPLIED

    out_offer = service.patch_tracker("j1", {"pipeline_status": "offer"})
    assert out_offer["item"]["pipeline_status"] == "offer"
    assert out_offer["item"]["status"] == "offer"
    assert service._jobs.get("j1").status == JobStatus.OFFER


def test_list_dedupes_same_company_title():
    jd = "AI Engineer\nAbout the job\nSumsub is the first.\n"
    older = JobRecord(
        id="old",
        user_id="u1",
        jd_text=jd,
        status=JobStatus.DRAFT,
        outputs={
            offer_draft_store.OFFER_FLOW_KEY: {
                "tailored_resume_text": "Tailored " + ("a" * 100),
                "tracker": {
                    "company_name": "Sumsub",
                    "job_title": "AI Engineer",
                    "pipeline_status": "interested",
                    "applied_at": None,
                    "closed": False,
                    "listed_at": "2026-11-15T10:00:00+00:00",
                },
            }
        },
    )
    newer = JobRecord(
        id="new",
        user_id="u1",
        jd_text=jd,
        status=JobStatus.DRAFT,
        outputs={
            offer_draft_store.OFFER_FLOW_KEY: {
                "tailored_resume_text": "Tailored " + ("b" * 100),
                "tracker": {
                    "company_name": "Sumsub",
                    "job_title": "AI Engineer",
                    "pipeline_status": "offer",
                    "applied_at": "2026-11-15",
                    "closed": False,
                    "listed_at": "2026-11-15T18:00:00+00:00",
                },
            }
        },
    )
    jobs = _FakeJobs(older)
    jobs.create(newer)
    service = JobService(jobs=jobs)
    listed = service.list_applications("u1", include_closed=False)
    assert listed["total"] == 1
    assert listed["items"][0]["job_id"] == "new"
    assert listed["items"][0]["pipeline_status"] == "offer"
    # older duplicate closed
    old_tracker = offer_draft_store.read_tracker(
        offer_draft_store.read_offer_flow(jobs.get("old").outputs)
    )
    assert old_tracker["closed"] is True


def test_save_offer_draft_merges_analysis():
    job = JobRecord(id="j1", user_id="u1", jd_text="jd", status=JobStatus.DRAFT, outputs={})
    service = JobService(jobs=_FakeJobs(job))
    result = service.save_offer_draft("j1", OfferDraftPatch(analysis={"match_score": 72}))
    assert result["ok"] is True
    assert result["draft"]["analysis"]["match_score"] == 72


def test_tailored_seeds_tracker():
    job = JobRecord(
        id="j1",
        user_id="u1",
        jd_text="x" * 50,
        status=JobStatus.DRAFT,
        outputs={
            offer_draft_store.OFFER_FLOW_KEY: {
                "analysis": {"company_name": "Sumsub", "job_title": "AI Engineer"},
            }
        },
    )
    service = JobService(jobs=_FakeJobs(job))
    result = service.save_offer_draft(
        "j1",
        OfferDraftPatch(tailored_resume_text="Tailored resume text " + ("y" * 80)),
    )
    tracker = result["draft"]["tracker"]
    assert tracker is not None
    assert tracker["company_name"] == "Sumsub"
    assert tracker["job_title"] == "AI Engineer"
    assert tracker["pipeline_status"] == PipelineStatus.INTERESTED.value
    assert tracker["closed"] is False
    assert tracker["listed_at"]


def test_save_jd_draft_reuses_open_draft_then_creates_after_listed():
    jobs = _FakeJobs()
    service = JobService(jobs=jobs)
    first = service.save_jd_draft(
        "u1",
        jd_text="A" * 50,
        analysis={"company_name": "Acme", "job_title": "DE"},
        llm_model="test",
    )
    assert first["reused"] is False
    job_id = first["job_id"]

    second = service.save_jd_draft(
        "u1",
        jd_text="B" * 50,
        analysis={"company_name": "Acme", "job_title": "DE"},
        llm_model="test",
    )
    assert second["reused"] is True
    assert second["job_id"] == job_id

    service.save_offer_draft(
        job_id,
        OfferDraftPatch(
            analysis={"company_name": "Acme", "job_title": "DE"},
            tailored_resume_text="Tailored " + ("z" * 100),
        ),
    )

    third = service.save_jd_draft(
        "u1",
        jd_text="C" * 50,
        analysis={"company_name": "Beta", "job_title": "ML"},
        llm_model="test",
    )
    assert third["reused"] is False
    assert third["job_id"] != job_id
    assert len(jobs._jobs) == 2


def test_list_applications_and_patch_applied_at():
    jobs = _FakeJobs()
    service = JobService(jobs=jobs)
    created = service.save_jd_draft(
        "u1",
        jd_text="JD text for Sumsub role " + ("x" * 40),
        analysis={"company_name": "Sumsub", "job_title": "AI Engineer"},
        llm_model="test",
    )
    job_id = created["job_id"]
    service.save_offer_draft(
        job_id,
        OfferDraftPatch(
            analysis={"company_name": "Sumsub", "job_title": "AI Engineer"},
            tailored_resume_text="Tailored resume " + ("a" * 100),
        ),
    )

    listed = service.list_applications("u1")
    assert listed["total"] == 1
    assert listed["items"][0]["company_name"] == "Sumsub"
    assert listed["items"][0]["pipeline_status"] == "interested"
    # applied_at is seeded on list/seed so the date column is never empty
    assert listed["items"][0]["applied_at"] == date.today().isoformat()

    patched = service.patch_tracker(job_id, {"pipeline_status": "applied"})
    assert patched["ok"] is True
    assert patched["item"]["pipeline_status"] == "applied"
    assert patched["item"]["applied_at"] == date.today().isoformat()

    closed = service.patch_tracker(job_id, {"closed": True})
    assert closed["item"]["closed"] is True
    hidden = service.list_applications("u1", include_closed=False)
    assert hidden["total"] == 0
    shown = service.list_applications("u1", include_closed=True)
    assert shown["total"] == 1


def test_draft_is_listed_helpers():
    assert offer_draft_store.draft_is_listed(None) is False
    assert offer_draft_store.draft_is_listed({}) is False
    assert (
        offer_draft_store.draft_is_listed(
            {
                offer_draft_store.OFFER_FLOW_KEY: {
                    "tailored_resume_text": "hello world tailored",
                }
            }
        )
        is True
    )


def test_infer_company_title_from_jd_sumsub():
    jd = (
        "AI Engineer\n"
        "About the job\n"
        "Sumsub is the first AI-powered trust infrastructure for compliance.\n"
    )
    company, title = offer_draft_store.infer_company_title_from_jd(jd)
    assert company == "Sumsub"
    assert title == "AI Engineer"


def test_skills_from_analysis_and_ats():
    skills = offer_draft_store.skills_from_analysis(
        {
            "required_entities": ["Python", "AWS", "Python", "", "Experience"],
            "matched_skills": ["SQL"],
        }
    )
    assert skills == ["Python", "AWS"]
    fallback = offer_draft_store.skills_from_analysis(
        {"matched_skills": ["SQL"], "unmatched_skills": ["Spark"]}
    )
    assert fallback == ["SQL", "Spark"]
    ats = offer_draft_store.skills_from_ats(
        {
            "ats_suggestions": [
                {"jd_entity": "data pipelines", "jd_phrase": "build data pipelines"},
                {"jd_phrase": "Kubernetes"},
            ]
        }
    )
    assert ats == ["data pipelines", "Kubernetes"]


def test_skills_from_jd_text():
    jd = (
        "Data Engineer\n"
        "About the job\n"
        "We build things.\n"
        "Requirements:\n"
        "- Python\n"
        "- SQL, Spark, Airflow\n"
        "- 5+ years experience with cloud platforms\n"
        "Benefits:\n"
        "- Free lunch\n"
    )
    skills = offer_draft_store.skills_from_jd_text(jd)
    assert "Python" in skills
    assert "SQL" in skills
    assert "Spark" in skills
    assert "Airflow" in skills


def test_application_row_includes_skills():
    outputs = {
        offer_draft_store.OFFER_FLOW_KEY: {
            "tailored_resume_text": "Tailored " + ("x" * 100),
            "analysis": {
                "required_entities": ["Python", "Docker"],
                "matched_skills": ["Python"],
            },
            "tracker": {
                "company_name": "Acme",
                "job_title": "Engineer",
                "pipeline_status": "interested",
                "applied_at": None,
                "closed": False,
                "listed_at": "2026-11-15T12:00:00+00:00",
            },
        }
    }
    row = offer_draft_store.build_application_row("j1", "JD", outputs)
    assert row is not None
    assert row["skills"] == ["Python", "Docker"]


def test_we_is_bad_company_name():
    assert offer_draft_store._is_bad_company_name("We")
    assert offer_draft_store._is_bad_company_name("we")
    assert not offer_draft_store._is_bad_company_name("Databricks")


def test_infer_company_title_from_jd_about_revolut():
    jd = (
        "Python Platform Engineer\n"
        "About Revolut\n\n"
        "People deserve more from their money. More visibility, more control.\n"
    )
    company, title = offer_draft_store.infer_company_title_from_jd(jd)
    assert company == "Revolut"
    assert title == "Python Platform Engineer"


def test_ensure_tracker_seeds_applied_at_and_repairs_about():
    jd = (
        "Python Platform Engineer\n"
        "About Revolut\n\n"
        "People deserve more from their money.\n"
    )
    flow = {
        "analysis": {},
        "tailored_resume_text": "Tailored " + ("x" * 100),
        "tracker": {
            "company_name": "About",
            "job_title": "Python Platform Engineer",
            "pipeline_status": "interested",
            "applied_at": None,
            "closed": False,
            "listed_at": "2026-11-15T18:11:09.676407+00:00",
        },
    }
    out = offer_draft_store.ensure_tracker_on_tailored(flow, jd_text=jd)
    tracker = offer_draft_store.read_tracker(out)
    assert tracker["company_name"] == "Revolut"
    assert tracker["applied_at"] == "2026-11-15"

    fresh = offer_draft_store.ensure_tracker_on_tailored(
        {
            "analysis": {},
            "tailored_resume_text": "Tailored " + ("y" * 100),
        },
        jd_text=jd,
    )
    fresh_tr = offer_draft_store.read_tracker(fresh)
    assert fresh_tr["company_name"] == "Revolut"
    assert fresh_tr["applied_at"]
    assert fresh_tr["listed_at"]


def test_tracker_backfill_from_jd_when_analysis_empty():
    jd = (
        "AI Engineer\nAbout the job\n"
        "Sumsub is the first AI-powered trust infrastructure.\n"
    )
    job = JobRecord(
        id="j1",
        user_id="u1",
        jd_text=jd,
        status=JobStatus.DRAFT,
        outputs={
            offer_draft_store.OFFER_FLOW_KEY: {
                "analysis": {"match_score": 70},
                "tailored_resume_text": "Tailored " + ("x" * 100),
                "tracker": {
                    "company_name": "",
                    "job_title": "",
                    "pipeline_status": "interested",
                    "applied_at": None,
                    "closed": False,
                    "listed_at": "2026-11-15T12:00:00+00:00",
                },
            }
        },
    )
    service = JobService(jobs=_FakeJobs(job))
    listed = service.list_applications("u1")
    assert listed["total"] == 1
    assert listed["items"][0]["company_name"] == "Sumsub"
    assert listed["items"][0]["job_title"] == "AI Engineer"
    saved = service._jobs.get("j1")
    tracker = offer_draft_store.read_tracker(
        offer_draft_store.read_offer_flow(saved.outputs)
    )
    assert tracker["company_name"] == "Sumsub"
    assert tracker["job_title"] == "AI Engineer"
