"""PDF / HTML rendering for Harvard CV (Chrome print + YAML→HTML)."""

from __future__ import annotations

from job_application.resume.pdf.render import build_html, render_cv_yml_to_html

__all__ = ["build_html", "render_cv_yml_to_html"]
