"""Low-level PDF/HTML extraction helpers (used by extractors)."""

from __future__ import annotations

import re
import tempfile
from html import unescape
from pathlib import Path


def html_to_plain_text(html: str) -> str:
    if not html or not html.strip():
        return ""
    t = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", html)
    t = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", t)
    t = re.sub(r"<[^>]+>", " ", t)
    t = unescape(t)
    return re.sub(r"\s+", " ", t).strip()


def extract_pdf_text(path: Path | str) -> str:
    path = Path(path)
    text_parts: list[str] = []

    try:
        import fitz  # pymupdf

        doc = fitz.open(path)
        try:
            for page in doc:
                text_parts.append(page.get_text("text") or "")
        finally:
            doc.close()
    except Exception:
        from pdfminer.high_level import extract_text as pdfminer_extract

        text_parts.append(pdfminer_extract(str(path)) or "")

    out = "\n".join(t for t in text_parts if t).strip()
    if not out:
        raise ValueError(f"No text extracted from PDF: {path}")
    return out


def extract_pdf_bytes(raw: bytes) -> str:
    if not raw:
        raise ValueError("PDF payload is empty")
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(raw)
        tmp_path = Path(tmp.name)
    try:
        return extract_pdf_text(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)
