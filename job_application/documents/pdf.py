"""Resume PDF — workshop cv/ pipeline (render.py + Chrome headless)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Protocol

from job_application.documents.resume_normalize import normalize_structured_for_render


class ResumeRenderer(Protocol):
    name: str

    def supports(self, structured: dict[str, Any]) -> bool: ...

    def render_pdf(self, structured: dict[str, Any]) -> bytes: ...


class BaseResumeRenderer(ABC):
    name: str

    def render_pdf(self, structured: dict[str, Any]) -> bytes:
        data = normalize_structured_for_render(structured)
        return self.render_bytes(data)

    @abstractmethod
    def supports(self, structured: dict[str, Any]) -> bool: ...

    @abstractmethod
    def render_bytes(self, data: dict[str, Any]) -> bytes: ...


class WorkshopCvRenderer(BaseResumeRenderer):
    """cv/pdf_to_yml_llm → cv/render.py → Chrome --print-to-pdf."""

    name = "workshop"

    def supports(self, structured: dict[str, Any]) -> bool:
        return True

    def render_bytes(self, data: dict[str, Any]) -> bytes:
        from job_application.resume.cv_pdf_export import render_structured_resume_pdf_bytes

        return render_structured_resume_pdf_bytes(data)


def default_renderers() -> list[ResumeRenderer]:
    return [WorkshopCvRenderer()]
