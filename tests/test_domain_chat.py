"""Tests for cv.yml profile model."""

from __future__ import annotations

from job_application.resume.profile_model import ResumeProfile


def test_resume_profile_from_answers():
    profile = ResumeProfile.from_chat_answers(
        {
            "name": "Jane",
            "headline": "Data Engineer",
            "email": "j@example.com",
            "exp_0_company": "Acme",
            "exp_0_title": "Engineer",
            "exp_0_period": "2020 – Present",
            "exp_0_bullets": "Built pipelines.",
        }
    )
    assert profile.to_api_dict()["chat_answers"]["name"] == "Jane"
    assert profile.to_api_dict()["structured"]["basics"]["name"] == "Jane"
