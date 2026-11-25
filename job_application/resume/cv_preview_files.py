"""Write workshop cv.yml + cv.html via cv/pdf_to_yml_llm.py and cv/render.py."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from job_application.config import CV_PREVIEW_ENABLED
from job_application.resume.cv_pdf_export import (
    _path_for_log,
    write_workshop_yml_and_html,
)

logger = logging.getLogger(__name__)


def write_cv_preview_files(structured: dict[str, Any]) -> tuple[Path, Path] | None:
    if not CV_PREVIEW_ENABLED:
        return None
    if not isinstance(structured, dict) or not structured:
        return None

    yml_path, html_path = write_workshop_yml_and_html(structured)
    logger.info(
        "CV preview updated (workshop): %s (%s bytes), %s (%s bytes)",
        _path_for_log(yml_path),
        yml_path.stat().st_size,
        _path_for_log(html_path),
        html_path.stat().st_size,
    )
    return yml_path, html_path


def cv_preview_paths_api() -> dict[str, str]:
    from job_application.resume.cv_pdf_export import cv_export_paths_api

    return cv_export_paths_api()
