"""Tests for renderer base classes."""

from __future__ import annotations

from job_application.documents.pdf import BaseResumeRenderer, WorkshopCvRenderer


def test_resume_renderer_base():
    assert isinstance(WorkshopCvRenderer(), BaseResumeRenderer)
