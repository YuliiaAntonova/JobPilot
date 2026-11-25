"""Backward-compatible accessors for PDF/YAML helpers (no importlib)."""

from __future__ import annotations

from types import ModuleType

from job_application.resume import cv_yml_io, pdf


def pdf_to_yml_module() -> ModuleType:
    return cv_yml_io


def render_module() -> ModuleType:
    return pdf.render
