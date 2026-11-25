"""PDF export: structured CV → cv.yml → Harvard HTML → Chrome headless."""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
from typing import Any

from job_application.config import CV_CHROME_BIN, CV_PDF_FILENAME, CV_PREVIEW_DIR, REPO_ROOT
from job_application.resume.cv_schema import CV_META_KEYS, normalize_to_cv
from job_application.resume.cv_yml_io import write_cv_yml
from job_application.resume.pdf import render_cv_yml_to_html

logger = logging.getLogger(__name__)


def _chrome_container_flags() -> list[str]:
    """Headless Chromium in Docker needs --no-sandbox / smaller /dev/shm."""
    forced = os.getenv("JOB_APP_CHROME_NO_SANDBOX", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    if forced or Path("/.dockerenv").is_file():
        return ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
    return []


def cv_preview_paths() -> tuple[Path, Path]:
    base = CV_PREVIEW_DIR
    return base / "cv.yml", base / "cv.html"


def job_tailored_draft_preview_paths() -> tuple[Path, Path]:
    """Preview files for JD-specific tailoring (does not overwrite cabinet cv.html)."""
    base = CV_PREVIEW_DIR
    return base / "cv_tailored_draft.yml", base / "cv_tailored_draft.html"


def write_job_tailored_draft_preview(structured: dict[str, Any]) -> tuple[Path, Path]:
    """Render tailoring preview to cv_tailored_draft.html (cabinet cv.html unchanged)."""
    if not isinstance(structured, dict) or not structured:
        raise ValueError("structured profile is empty")

    CV_PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    yml_path, html_path = job_tailored_draft_preview_paths()
    cv = structured_to_workshop_cv(structured)

    yml_path = write_cv_yml(cv, yml_path)
    render_cv_yml_to_html(yml_path, html_path)
    return yml_path, html_path


def cv_pdf_path() -> Path:
    return CV_PREVIEW_DIR / CV_PDF_FILENAME


def structured_to_workshop_cv(structured: dict[str, Any]) -> dict[str, Any]:
    data = normalize_to_cv(structured)
    return {
        k: v
        for k, v in data.items()
        if k not in CV_META_KEYS and not str(k).startswith("_")
    }


def write_workshop_yml_and_html(structured: dict[str, Any]) -> tuple[Path, Path]:
    """normalize → write_cv_yml + render_cv_yml_to_html."""
    if not isinstance(structured, dict) or not structured:
        raise ValueError("structured profile is empty")

    CV_PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    yml_path, html_path = cv_preview_paths()
    cv = structured_to_workshop_cv(structured)

    yml_path = write_cv_yml(cv, yml_path)
    render_cv_yml_to_html(yml_path, html_path)
    return yml_path, html_path


def chrome_html_to_pdf(html_path: Path, pdf_path: Path) -> None:
    """
    Print HTML to PDF via headless Chrome.

    "/Applications/Google Chrome.app/.../Google Chrome"
      --headless --no-pdf-header-footer
      --print-to-pdf=.../yevgen_cv.pdf file://.../cv.html
    """
    chrome = Path(CV_CHROME_BIN)
    if not chrome.is_file():
        raise FileNotFoundError(
            f"Chrome not found at {chrome}. Set CV_CHROME_BIN in .env to your Google Chrome binary."
        )

    pdf_path = pdf_path.expanduser().resolve()
    html_path = html_path.expanduser().resolve()
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    if pdf_path.exists():
        pdf_path.unlink()

    cmd = [
        str(chrome),
        "--headless",
        "--no-pdf-header-footer",
        *_chrome_container_flags(),
        f"--print-to-pdf={pdf_path}",
        html_path.as_uri(),
    ]
    logger.info("Chrome PDF: %s", " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if proc.returncode != 0 or not pdf_path.is_file():
        detail = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(f"Chrome print-to-pdf failed (exit {proc.returncode}): {detail}")


def render_structured_resume_pdf_bytes(structured: dict[str, Any]) -> bytes:
    """structured JSON → cv.yml → cv.html → PDF (Chrome)."""
    _yml_path, html_path = write_workshop_yml_and_html(structured)
    pdf_path = cv_pdf_path()
    chrome_html_to_pdf(html_path, pdf_path)
    data = pdf_path.read_bytes()
    logger.info(
        "Workshop PDF: %s (%s bytes) from %s",
        _path_for_log(pdf_path),
        len(data),
        _path_for_log(html_path),
    )
    return data


def html_to_pdf_bytes(html_content: str, *, html_path: Path | None = None) -> bytes:
    """Write HTML to disk and print with Chrome."""
    CV_PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    target_html = html_path or (CV_PREVIEW_DIR / "_print.html")
    target_html.write_text(html_content, encoding="utf-8")
    pdf_path = cv_pdf_path()
    chrome_html_to_pdf(target_html, pdf_path)
    return pdf_path.read_bytes()


def _path_for_log(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def cv_export_paths_api() -> dict[str, str]:
    yml_path, html_path = cv_preview_paths()
    pdf_path = cv_pdf_path()
    return {
        "cv_yml": _path_for_log(yml_path),
        "cv_html": _path_for_log(html_path),
        "cv_pdf": _path_for_log(pdf_path),
        "cv_dir": _path_for_log(CV_PREVIEW_DIR),
    }
