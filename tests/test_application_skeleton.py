"""Smoke tests for simplified architecture."""

from __future__ import annotations

from job_application.application.export_service import ExportService
from job_application.resume.profile_model import ResumeProfile
from job_application.documents.pdf import WorkshopCvRenderer, default_renderers


def test_resume_profile_from_chat_answers_roundtrip_keys():
    answers = {
        "fullName": "Jane Doe",
        "email": "jane@example.com",
        "phone": "+1 555 0100",
        "desiredPosition": "Data Engineer",
    }
    profile = ResumeProfile.from_chat_answers(answers)
    api = profile.to_api_dict()

    assert api["chat_answers"]["fullName"] == "Jane Doe"
    assert api["chat_answers"]["email"] == "jane@example.com"
    assert isinstance(api["structured"], dict)
    assert len(api["profile_text"]) >= 10


def test_export_service_picks_workshop_renderer():
    service = ExportService(renderers=default_renderers())
    structured = {
        "basics": {"name": "Yuliia Antonova", "email": "y@e.com"},
        "resume_template": "harvard",
    }
    renderer = service._pick_renderer(structured, template=None)
    assert isinstance(renderer, WorkshopCvRenderer)


def test_export_service_explicit_workshop_template():
    service = ExportService(renderers=default_renderers())
    structured = {"basics": {"name": "Test User", "email": "t@e.com"}}
    renderer = service._pick_renderer(structured, template="workshop")
    assert isinstance(renderer, WorkshopCvRenderer)
