"""Backward-compatible re-export — prefer job_application.domain.profile.entity."""

from job_application.domain.profile.entity import ProfileEntity, ResumeProfile

__all__ = ["ProfileEntity", "ResumeProfile"]
