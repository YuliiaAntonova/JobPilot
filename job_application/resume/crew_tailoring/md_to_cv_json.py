"""Map a free-form tailored resume Markdown into cv_template.json shape."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from openai import OpenAI

from job_application.resume.template_extractor import get_target_fields, validate_shape
from job_application.resume.crew_tailoring.utils import get_openai_api_key, get_openai_model_name

_RESUME_DIR = Path(__file__).resolve().parent.parent
DEFAULT_TEMPLATE = _RESUME_DIR / "cv_template.json"


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        text = text.rsplit("```", 1)[0]
    return text.strip()


def _cert_to_scalar(item: Any) -> str:
    """Flatten LLM cert objects into one display string."""
    if isinstance(item, str):
        return item.strip()
    if not isinstance(item, dict):
        return str(item)
    name = str(item.get("name") or item.get("title") or "").strip()
    issuer = str(item.get("issuer") or item.get("organization") or "").strip()
    when = str(
        item.get("date")
        or item.get("year")
        or item.get("period")
        or item.get("issued")
        or ""
    ).strip()
    if name and issuer and name.lower().startswith(issuer.lower()):
        base = name
    elif name and issuer:
        base = f"{issuer} - {name}"
    else:
        base = name or issuer or json.dumps(item, ensure_ascii=False)
    if when and when not in base:
        return f"{base} ({when})"
    return base


def _coerce_empty_array_fields(filled: dict[str, Any], template: dict[str, Any]) -> None:
    for key, shape in template.items():
        if shape != [] or key not in filled:
            continue
        raw = filled[key]
        if not isinstance(raw, list):
            continue
        if key == "certifications":
            filled[key] = [_cert_to_scalar(x) for x in raw if x is not None]
        else:
            filled[key] = [
                x if not isinstance(x, (dict, list)) else json.dumps(x, ensure_ascii=False)
                for x in raw
            ]


_CONTACT_SCALAR_KEYS = ("location", "email", "phone")


def _looks_like_placeholder(value: Any) -> bool:
    if value is None:
        return True
    if not isinstance(value, str):
        return False
    text = value.strip()
    if not text:
        return True
    low = text.lower()
    if text.startswith("[") and text.endswith("]"):
        return True
    stub_markers = (
        "ihr wohnort",
        "ihre e-mail",
        "ihre telefon",
        "ihr xing",
        "ihr github",
        "ihr linkedin",
        "your location",
        "your email",
        "your phone",
        "your xing",
        "your github",
        "your linkedin",
        "unternehmensname",
        "company name",
        "example.com",
    )
    return any(m in low for m in stub_markers)


def _links_need_backfill(links: Any) -> bool:
    if not isinstance(links, list) or not links:
        return True
    for ln in links:
        if not isinstance(ln, dict):
            return True
        url = str(ln.get("url") or "").strip()
        if not url.startswith(("http://", "https://")) or _looks_like_placeholder(url):
            return True
    return False


def _infer_link_label(url: str, text: str = "") -> str:
    low = str(url or "").strip().lower()
    if "linkedin.com" in low:
        return "LinkedIn"
    if "github.com" in low or "github.io" in low:
        return "GitHub"
    if "xing.com" in low:
        return "Xing"
    return str(text or "").strip() or "Link"


def normalize_basics_link_labels(filled: dict[str, Any]) -> None:
    """Ensure basics.links use platform labels (LinkedIn/GitHub), not raw handles."""
    basics = filled.get("basics")
    if not isinstance(basics, dict):
        return
    links = basics.get("links")
    if not isinstance(links, list):
        return
    for ln in links:
        if not isinstance(ln, dict):
            continue
        url = str(ln.get("url") or "").strip()
        text = str(ln.get("text") or "").strip()
        label = str(ln.get("label") or "").strip()
        inferred = _infer_link_label(url, text)
        if inferred in {"LinkedIn", "GitHub", "Xing"} and (
            not label or label.casefold() == text.casefold()
        ):
            ln["label"] = inferred


def backfill_basics_contacts(
    filled: dict[str, Any],
    contacts_source: dict[str, Any] | None,
) -> None:
    """Prefer real contacts from contacts_source for the HTML header."""
    if not contacts_source:
        normalize_basics_link_labels(filled)
        return
    src_basics = contacts_source.get("basics") or {}
    dst_basics = filled.setdefault("basics", {})
    for key in _CONTACT_SCALAR_KEYS:
        src_val = src_basics.get(key)
        if not src_val:
            continue
        if _looks_like_placeholder(dst_basics.get(key)):
            dst_basics[key] = src_val
    src_links = src_basics.get("links") or []
    if src_links and _links_need_backfill(dst_basics.get("links")):
        dst_basics["links"] = src_links
    else:
        # Keep tailored URLs, but restore platform labels from the source profile
        dst_links = dst_basics.get("links")
        if isinstance(dst_links, list) and isinstance(src_links, list) and src_links:
            by_host: dict[str, dict[str, Any]] = {}
            for src in src_links:
                if not isinstance(src, dict):
                    continue
                url = str(src.get("url") or "").strip().lower()
                for host in ("linkedin.com", "github.com", "xing.com"):
                    if host in url:
                        by_host[host] = src
            for dst in dst_links:
                if not isinstance(dst, dict):
                    continue
                url = str(dst.get("url") or "").strip().lower()
                for host, src in by_host.items():
                    if host not in url:
                        continue
                    src_label = str(src.get("label") or "").strip()
                    if src_label:
                        dst["label"] = src_label
                    if src.get("url") and _looks_like_placeholder(dst.get("url")):
                        dst["url"] = src["url"]
                    break
    normalize_basics_link_labels(filled)


def _resolve_markdown(
    markdown: str | Path | None,
    md_path: str | Path | None,
) -> str:
    if isinstance(markdown, str) and markdown.strip():
        return markdown
    if markdown is not None and not isinstance(markdown, str):
        return Path(markdown).read_text(encoding="utf-8")
    if md_path is not None:
        return Path(md_path).read_text(encoding="utf-8")
    raise ValueError("markdown or md_path required")


def markdown_to_cv_json(
    md_path: str | Path | None = None,
    template_path: str | Path | None = None,
    out_path: str | Path | None = None,
    *,
    markdown: str | None = None,
    contacts_path: str | Path | None = None,
    contacts_source: dict[str, Any] | None = None,
    model: str | None = None,
) -> tuple[dict[str, Any], dict[str, int]]:
    """
    Use OpenAI to fit tailored Markdown into the CV JSON template.

    Prefer in-memory ``markdown`` + ``contacts_source`` for the API path.
    File paths remain for notebook parity.

    Returns ``(filled_cv, token_usage)``.
    """
    md = _resolve_markdown(markdown, md_path)
    template_path = Path(template_path or DEFAULT_TEMPLATE)
    template = json.loads(template_path.read_text(encoding="utf-8"))
    shape = get_target_fields(template_path)
    model_name = model or get_openai_model_name()

    if contacts_source is None and contacts_path:
        cpath = Path(contacts_path)
        if cpath.is_file():
            loaded = json.loads(cpath.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                contacts_source = loaded

    prompt = f"""
You convert a tailored resume written in Markdown into ONE JSON object.

Rules:
- Keep EXACTLY the target keys and hierarchy; add no keys.
- Fill values only from the Markdown; never invent employers, dates, skills, or degrees.
- Replace null placeholders with facts from the Markdown; missing scalars remain null.
- Expand arrays of objects to one object per relevant record.
- Fill empty arrays with relevant scalar strings when Markdown lists them; keep [] if unsupported.
- certifications must be a JSON array of strings only
  (e.g. "DeepLearning.ai - Agentic AI (May 2026)"), never objects.
- Map "Professional Summary" / Summary / Ziel / Objective into basics.summary.
- Map Skills groups into skills[].group + skills[].items.
- skills[].items must be atomic keywords/short phrases, never full sentences.
  If a skill line is prose that lists domains/industries (e.g. "Experience in
  X, Y, and Z industries, with a focus on …"), extract only the named domains
  as separate items and drop the filler wording.
- Map jobs into experience[] (title, company, location, period, project_context, bullets).
- Earlier / older roles may go to experience_earlier[] when clearly secondary.
- Preserve contact header when present in Markdown: location, email, phone.
- Links (GitHub, LinkedIn, Xing) go to basics.links[] with:
  label = platform name (GitHub / LinkedIn / Xing),
  text = profile handle or display name,
  url = full https URL (never omit the URL).
- Return valid JSON only (no Markdown fences).

TARGET JSON TEMPLATE:
{json.dumps(template, ensure_ascii=False, indent=2)}

TAILORED RESUME MARKDOWN:
{md}
"""

    api_key = get_openai_api_key()
    if not api_key:
        raise ValueError("OPENAI_API_KEY required for markdown_to_cv_json (L7 crew path)")

    client = OpenAI(api_key=api_key)
    resp = client.chat.completions.create(
        model=model_name,
        messages=[
            {
                "role": "system",
                "content": "You output only valid JSON matching the given CV template.",
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0,
    )
    raw = resp.choices[0].message.content or ""
    filled = json.loads(_strip_code_fence(raw))
    _coerce_empty_array_fields(filled, template)
    backfill_basics_contacts(filled, contacts_source)
    validate_shape(filled, shape)

    usage_obj = getattr(resp, "usage", None)
    token_usage = {
        "prompt_tokens": int(getattr(usage_obj, "prompt_tokens", 0) or 0),
        "completion_tokens": int(getattr(usage_obj, "completion_tokens", 0) or 0),
        "total_tokens": int(getattr(usage_obj, "total_tokens", 0) or 0),
    }

    if out_path is not None:
        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(filled, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return filled, token_usage


def l7_json_to_slim_cv(filled: dict[str, Any]) -> dict[str, Any]:
    """Map L7 template keys (selected_projects) onto slim cv.yml before normalize_to_cv."""
    from job_application.resume.rag_prepare.normalize import l7_json_to_slim_cv as _map

    return _map(filled)
