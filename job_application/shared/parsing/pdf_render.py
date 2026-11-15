"""Build simple PDFs from plain text or field answers (PyMuPDF)."""

from __future__ import annotations

import textwrap
from pathlib import Path

import fitz  # pymupdf


def _build_plain_text_pdf(lines: list[str]) -> bytes:
    doc = fitz.open()
    margin_x = 56
    margin_y = 56
    page_w, page_h = fitz.paper_rect("a4").width, fitz.paper_rect("a4").height
    fontsize = 11
    line_gap = fontsize * 1.45

    page = doc.new_page(width=page_w, height=page_h)
    y = margin_y

    def new_page() -> None:
        nonlocal page, y
        page = doc.new_page(width=page_w, height=page_h)
        y = margin_y

    for raw_line in lines:
        wrapped = textwrap.wrap(raw_line, width=92) or [""]
        for wl in wrapped:
            if y > page_h - margin_y:
                new_page()
            page.insert_text((margin_x, y), wl[:500], fontsize=fontsize)
            y += line_gap

    pdf_bytes = doc.tobytes(deflate=True)
    doc.close()
    return pdf_bytes


def _render_lines_to_pdf(output_path: Path, lines: list[str]) -> None:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(_build_plain_text_pdf(lines))


def render_filled_pdf(
    output_path: Path,
    answers: list[dict],
    fit_summary: str | None = None,
) -> None:
    """Application form field answers → draft PDF."""
    lines: list[str] = [
        "Filled application (draft — verify before submit)",
        "",
    ]
    if fit_summary:
        lines.append("Summary — role fit")
        lines.extend(textwrap.wrap(fit_summary, width=92))
        lines.append("")
    lines.append("Field answers")
    lines.append("")

    for answer in answers:
        fid = str(answer.get("field_id", ""))
        val = str(answer.get("value", "")).replace("\r", " ")
        conf = answer.get("confidence", "")
        quote = str(answer.get("quote_from_resume", "")).replace("\r", " ")
        lines.append(f"[{fid}]")
        lines.extend(textwrap.wrap(val, width=92) or ["—"])
        lines.append(f"(confidence: {conf})")
        if quote:
            lines.append("Evidence:")
            lines.extend(textwrap.wrap(quote, width=92))
        lines.append("")

    _render_lines_to_pdf(output_path, lines)


def render_plain_document_pdf(output_path: Path, *, title: str, body: str) -> None:
    """Multi-page PDF from plain text (e.g. resume.txt fallback)."""
    lines: list[str] = []
    if title.strip():
        lines.append(title.strip())
        lines.append("")
    for para in (body or "").strip().split("\n\n"):
        p = para.strip()
        if not p:
            lines.append("")
            continue
        lines.extend(textwrap.wrap(p, width=92) or [""])
        lines.append("")
    _render_lines_to_pdf(output_path, lines)


def cover_letter_body_to_pdf_lines(body: str, *, title: str = "") -> list[str]:
    """Plain cover letter text → PDF lines (paragraph blocks preserved)."""
    lines: list[str] = []
    if title.strip():
        lines.append(title.strip())
        lines.append("")
    for para in (body or "").replace("\r\n", "\n").split("\n\n"):
        p = para.strip()
        if not p:
            lines.append("")
            continue
        for sub in p.split("\n"):
            sub = sub.strip()
            if sub:
                lines.extend(textwrap.wrap(sub, width=92) or [""])
        lines.append("")
    return lines


def render_cover_letter_pdf_bytes(body: str, *, title: str = "") -> bytes:
    """Cover letter plain text (block paragraphs) → PDF bytes."""
    return _build_plain_text_pdf(cover_letter_body_to_pdf_lines(body, title=title))
