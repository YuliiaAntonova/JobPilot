"""Document text extraction — PDF, HTML, TXT bytes → plain text."""

from __future__ import annotations

from typing import Literal

from job_application.shared.parsing._pdf_core import extract_pdf_bytes, extract_pdf_text, html_to_plain_text

DocumentKind = Literal["resume", "jd"]

__all__ = [
    "DocumentKind",
    "bytes_to_plain_text",
    "extract_pdf_bytes",
    "extract_pdf_text",
    "html_to_plain_text",
    "jd_bytes_to_plain_text",
    "resume_bytes_to_plain_text",
]


def bytes_to_plain_text(
    filename: str | None,
    raw: bytes,
    *,
    kind: DocumentKind = "resume",
) -> str:
    if not raw:
        if kind == "jd":
            return ""
        raise ValueError("File is empty")

    name = (filename or "").lower()

    if name.endswith(".pdf"):
        return extract_pdf_bytes(raw)

    if kind == "jd" and (name.endswith(".html") or name.endswith(".htm")):
        return html_to_plain_text(raw.decode("utf-8", errors="replace"))

    if kind == "resume" and name.endswith(".txt"):
        return raw.decode("utf-8", errors="replace").strip()

    if kind == "jd":
        return raw.decode("utf-8", errors="replace").strip()

    raise ValueError(
        "For resumes only PDF or TXT is supported. For DOCX, paste the text into resume_text for now."
    )


def resume_bytes_to_plain_text(filename: str | None, raw: bytes) -> str:
    return bytes_to_plain_text(filename, raw, kind="resume")


def jd_bytes_to_plain_text(filename: str | None, raw: bytes) -> str:
    return bytes_to_plain_text(filename, raw, kind="jd")
