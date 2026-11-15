"""Resume PDF export."""

from __future__ import annotations

from typing import Any

from job_application.documents.pdf import default_renderers


class ExportService:
    def __init__(self, renderers=None) -> None:
        self._renderers = renderers or default_renderers()

    def export_pdf(self, structured: dict[str, Any], *, template: str | None = None) -> bytes:
        renderer = self._pick_renderer(structured, template=template)
        return renderer.render_pdf(structured)

    def _pick_renderer(self, structured: dict[str, Any], *, template: str | None):
        if template:
            for renderer in self._renderers:
                if renderer.name == template:
                    return renderer
            raise ValueError(f"Unknown resume template: {template}")

        for renderer in self._renderers:
            if renderer.supports(structured):
                return renderer

        return self._renderers[-1]
