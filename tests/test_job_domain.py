"""Tests for job domain entity and form field mapper."""

from __future__ import annotations

import pytest

from job_application.models.exceptions import InvalidJobState
from job_application.models.schemas import JobRecord
from job_application.models.enums import JobStatus


def test_job_start_processing():
    job = JobRecord(id="j1", jd_text="desc", status=JobStatus.QUEUED)
    job.start_processing()
    assert job.status == JobStatus.PROCESSING
    assert job.error_message is None


def test_job_invalid_transition():
    job = JobRecord(id="j1", jd_text="desc", status=JobStatus.DONE)
    with pytest.raises(InvalidJobState):
        job.start_processing()
