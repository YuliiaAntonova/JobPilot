"""Document I/O: plain text extraction and simple PDF rendering."""

from job_application.shared.parsing.pdf_render import render_filled_pdf, render_plain_document_pdf
from job_application.shared.parsing.text_extract import (
    bytes_to_plain_text,
    extract_pdf_bytes,
    extract_pdf_text,
    html_to_plain_text,
    jd_bytes_to_plain_text,
    resume_bytes_to_plain_text,
)

__all__ = [
    "bytes_to_plain_text",
    "extract_pdf_bytes",
    "extract_pdf_text",
    "html_to_plain_text",
    "jd_bytes_to_plain_text",
    "render_filled_pdf",
    "render_plain_document_pdf",
    "resume_bytes_to_plain_text",
]
