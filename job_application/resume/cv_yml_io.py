"""cv.yml I/O — schema, PDF/text → YAML parsing (from cv/pdf_to_yml_llm.py)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import os

import yaml

from job_application.config import APP_LLM_MODEL, CV_YAML_LLM_FALLBACK, REPO_ROOT
from job_application.shared.llm.client import chat_completion_tracked
from job_application.shared.llm.cursor_client import cursor_chat_completion_tracked, is_cursor_model
from job_application.shared.parsing import resume_bytes_to_plain_text

CV_YML_SCHEMA = """
basics:
  name: ""
  headline: ""
  location: ""
  email: ""
  phone: ""
  links:
    - label: ""
      text: ""
      url: ""
  summary: ""
  note: ""

skills:
  - group: ""
    items: []

experience:
  - company: ""
    title: ""
    location: ""
    period: ""
    context: ""
    bullets: []

experience_earlier:
  - period: ""
    company: ""
    role: ""
    location: ""
    stack: []

projects:
  - name: ""
    bullets: []

education:
  - degree: ""
    school: ""
    period: ""
    note: ""

certifications: []

languages:
  - name: ""
    level: ""

recognition:
  books: []
  highlights: []

interests: ""
"""

MONTHS = {
    "January": "Jan",
    "February": "Feb",
    "March": "Mar",
    "April": "Apr",
    "May": "May",
    "June": "Jun",
    "July": "Jul",
    "August": "Aug",
    "September": "Sep",
    "October": "Oct",
    "November": "Nov",
    "December": "Dec",
}

_YAML_PROMPT_RULES = """
Rules:
- Do not use Markdown code fences.
- Do not add explanations before or after the YAML.
- The first line of the response MUST be exactly: basics:
- Do not invent facts, skills, technologies, companies, dates, or achievements.
- Preserve factual information from the resume.
- Normalize obvious PDF extraction artifacts and missing spaces.
- Keep the 3 most recent roles in `experience`.
- Put older roles into `experience_earlier`.
- Always extract basics.location, basics.email, and basics.phone from the resume header/contact block when present.
- Missing values must be "" or [].
- Quote strings that contain ":" (e.g. headlines, titles) with double quotes.
- Group skills into useful categories when supported by the source.
- Preserve links, certifications, education, and languages.
- Keep experience bullets concise while preserving their meaning.
- Output must be valid YAML parseable by PyYAML.
"""

# Root keys from CV_YML_SCHEMA — used to locate the real document start
_CV_ROOT_KEYS = (
    "basics",
    "skills",
    "experience",
    "experience_earlier",
    "projects",
    "education",
    "certifications",
    "languages",
    "recognition",
    "interests",
)
_ROOT_KEY_LINE = re.compile(
    rf"^(?:{'|'.join(_CV_ROOT_KEYS)})\s*:",
    re.MULTILINE,
)


def clean_yaml_output(text: str) -> str:
    """Strip fences/preamble so PyYAML sees a mapping starting at basics:/skills:/…"""
    text = (text or "").strip()
    if not text:
        return ""

    # Prefer fenced block contents when present
    fence = re.search(
        r"```(?:yaml|yml)?\s*\n(.*?)```",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if fence:
        text = fence.group(1).strip()
    else:
        text = re.sub(r"^\s*```(?:yaml|yml)?\s*\n?", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\n?\s*```\s*$", "", text)

    # Drop prose / "Here is the YAML:" before the first schema root key
    match = _ROOT_KEY_LINE.search(text)
    if match:
        text = text[match.start() :].strip()

    # Drop trailing prose after the document (common LLM chatter)
    # Keep from start through last non-empty YAML-looking line; strip --- document end markers
    text = re.sub(r"\n---+\s*$", "", text).strip()
    return text


def _try_load_cv_yaml(yml: str) -> dict[str, Any]:
    data = yaml.safe_load(yml)
    if not isinstance(data, dict):
        raise ValueError("LLM response is valid YAML, but root is not a mapping.")
    return data


def _repair_common_yaml_issues(yml: str) -> str:
    """Best-effort local repairs for frequent LLM YAML mistakes."""
    lines = yml.splitlines()
    fixed: list[str] = []
    # Quote scalar values that contain an unquoted colon after the first mapping colon
    scalar_re = re.compile(r"^(\s*[\w.-]+\s*:\s*)([^\"'\n{[\-|].*)$")
    for line in lines:
        m = scalar_re.match(line)
        if m:
            prefix, value = m.group(1), m.group(2).rstrip()
            # Skip empty, explicit null, booleans, numbers, already complex
            if value and ":" in value and not value.startswith(("|", ">", "&", "*")):
                esc = value.replace("\\", "\\\\").replace('"', '\\"')
                fixed.append(f'{prefix}"{esc}"')
                continue
        fixed.append(line)
    return "\n".join(fixed)


def _normalize_period_text(period: str) -> str:
    text = str(period or "")
    for full, short in MONTHS.items():
        text = re.sub(rf"\b{full}\b", short, text, flags=re.IGNORECASE)
    text = re.sub(r"\s*[-–—]\s*", " – ", text)
    text = re.sub(r"\bCurrent\b", "Present", text, flags=re.IGNORECASE)
    text = re.sub(r"\bNow\b", "Present", text, flags=re.IGNORECASE)
    return text.strip()


EXPERIENCE_RECENT_LIMIT = 3


def _exp_clean(text: object) -> str:
    return str(text or "").strip()


def _unified_experience_job(job: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(job, dict):
        return None
    title = _exp_clean(job.get("title") or job.get("role"))
    company = _exp_clean(job.get("company"))
    if not company and not title:
        return None
    bullets = [_exp_clean(x) for x in (job.get("bullets") or []) if _exp_clean(x)]
    stack = [_exp_clean(x) for x in (job.get("stack") or []) if _exp_clean(x)]
    return {
        "company": company or title,
        "title": title,
        "location": _exp_clean(job.get("location")),
        "period": _exp_clean(job.get("period")),
        "context": _exp_clean(job.get("context") or job.get("project_context")),
        "bullets": bullets,
        "stack": stack,
    }


def _to_experience_entry(job: dict[str, Any]) -> dict[str, Any]:
    bullets = list(job.get("bullets") or [])
    stack = list(job.get("stack") or [])
    if not bullets and stack:
        bullets = list(stack)
    entry: dict[str, Any] = {
        "company": job["company"],
        "title": job["title"],
        "location": job.get("location", ""),
        "period": job.get("period", ""),
        "bullets": bullets,
    }
    if job.get("context"):
        entry["context"] = job["context"]
    return entry


def _to_earlier_entry(job: dict[str, Any]) -> dict[str, Any]:
    stack = list(job.get("stack") or [])
    if not stack:
        stack = list(job.get("bullets") or [])
    return {
        "period": job.get("period", ""),
        "company": job["company"],
        "role": job.get("title", ""),
        "location": job.get("location", ""),
        "stack": stack,
    }


def split_experience_sections(cv: dict[str, Any], limit: int = EXPERIENCE_RECENT_LIMIT) -> dict[str, Any]:
    """Keep the N most recent roles in experience; move the rest to experience_earlier."""
    data = dict(cv or {})
    unified: list[dict[str, Any]] = []
    for job in data.get("experience") or []:
        row = _unified_experience_job(job)
        if row:
            unified.append(row)
    for job in data.get("experience_earlier") or []:
        row = _unified_experience_job(job)
        if row:
            unified.append(row)
    if not unified:
        data.pop("experience", None)
        data.pop("experience_earlier", None)
        return data

    recent = unified[:limit]
    older = unified[limit:]
    data["experience"] = [_to_experience_entry(job) for job in recent]
    if older:
        data["experience_earlier"] = [_to_earlier_entry(job) for job in older]
    else:
        data.pop("experience_earlier", None)
    return data


def enrich_cv_basics_from_plain(cv: dict[str, Any], plain_text: str) -> dict[str, Any]:
    """Fill missing basics contact fields from resume plain text."""
    plain = str(plain_text or "").strip()
    if not plain:
        return cv
    from job_application.resume.profile_text import _extract_contact_from_plain_text, _sanitize_contact_location

    contact = _extract_contact_from_plain_text(plain)
    basics = cv.setdefault("basics", {})
    if not isinstance(basics, dict):
        return cv

    if contact.get("email") and not _exp_clean(basics.get("email")):
        basics["email"] = contact["email"]
    if contact.get("phone") and not _exp_clean(basics.get("phone")):
        basics["phone"] = contact["phone"]

    plain_loc = _sanitize_contact_location(contact.get("location", ""))
    existing_loc = _sanitize_contact_location(str(basics.get("location") or ""))
    if plain_loc and not existing_loc:
        basics["location"] = plain_loc
    elif plain_loc and existing_loc and "," in plain_loc and "," not in existing_loc:
        basics["location"] = plain_loc
    return cv


def normalize_dates(cv: dict[str, Any]) -> dict[str, Any]:
    data = dict(cv or {})
    experience = data.get("experience")
    if isinstance(experience, list):
        for job in experience:
            if not isinstance(job, dict):
                continue
            job["period"] = _normalize_period_text(job.get("period", ""))

    earlier = data.get("experience_earlier")
    if isinstance(earlier, list):
        for job in earlier:
            if not isinstance(job, dict):
                continue
            period = _normalize_period_text(job.get("period", ""))
            years = re.findall(r"\b(?:19|20)\d{2}\b", period)
            if len(years) >= 2:
                job["period"] = f"{years[0]} – {years[-1]}"
            elif len(years) == 1:
                if re.search(r"\bPresent\b", period, re.IGNORECASE):
                    job["period"] = f"{years[0]} – Present"
                else:
                    job["period"] = years[0]
            else:
                job["period"] = period
    return data


def _build_yaml_extraction_prompt(resume_text: str) -> str:
    return f"""
Convert the resume below into EXACTLY the YAML schema provided.

Return RAW YAML only.

{_YAML_PROMPT_RULES}

YAML SCHEMA:

{CV_YML_SCHEMA}

RESUME:

{resume_text[:120000]}
"""


def _parse_yaml_response(raw: str) -> dict[str, Any]:
    yml = clean_yaml_output(raw)
    errors: list[str] = []
    for candidate in (yml, _repair_common_yaml_issues(yml)):
        if not candidate.strip():
            continue
        try:
            data = _try_load_cv_yaml(candidate)
            return normalize_dates(data)
        except (yaml.YAMLError, ValueError) as exc:
            errors.append(str(exc))

    # Last resort: JSON object mistaken for YAML
    stripped = yml.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        import json

        try:
            data = json.loads(stripped)
            if isinstance(data, dict):
                return normalize_dates(data)
        except json.JSONDecodeError as exc:
            errors.append(f"json: {exc}")

    detail = errors[-1] if errors else "empty document"
    raise ValueError(f"LLM returned invalid YAML: {detail}")


def _yaml_llm_fallback_models() -> list[str]:
    """Ordered fallbacks when primary model fails (Groq → OpenAI by default)."""
    models: list[str] = []
    seen: set[str] = set()

    def add(model: str | None) -> None:
        m = (model or "").strip()
        if m and m not in seen:
            seen.add(m)
            models.append(m)

    add(CV_YAML_LLM_FALLBACK)
    if os.getenv("GROQ_API_KEY", "").strip():
        add(os.getenv("CV_YAML_LLM_FALLBACK_GROQ", "groq:qwen/qwen3.8-27b"))
    if os.getenv("OPENAI_API_KEY", "").strip():
        add(os.getenv("CV_YAML_LLM_FALLBACK_OPENAI", "openai:gpt-4o-mini"))
    return models


def _resume_yaml_llm_raw(prompt: str, *, model: str | None) -> str:
    """LLM call for resume → YAML (Cursor without tools, optional aisuite fallback)."""
    chosen = model or APP_LLM_MODEL
    primary_err: Exception | None = None

    try:
        if is_cursor_model(chosen):
            raw, _usage = cursor_chat_completion_tracked(
                chosen,
                "",
                prompt,
                call_label="resume_text_to_cv",
                tools=[],
            )
            return raw
        raw, _usage = chat_completion_tracked(
            chosen,
            "",
            prompt,
            call_label="resume_text_to_cv",
        )
        return raw
    except Exception as exc:
        primary_err = exc

    errors = [f"Primary model ({chosen}):\n{primary_err}"]
    for fallback in _yaml_llm_fallback_models():
        if fallback == chosen:
            continue
        try:
            raw, _usage = chat_completion_tracked(
                fallback,
                "",
                prompt,
                call_label="resume_text_to_cv_fallback",
            )
            return raw
        except Exception as fallback_err:
            errors.append(f"Fallback model ({fallback}):\n{fallback_err}")

    hint = ""
    joined = "\n\n".join(errors)
    if "unexpected keyword argument 'proxies'" in joined:
        hint = (
            "\n\nHint: update dependencies (pip install -r requirements.txt) — "
            "requires groq>=1.0 and httpx<0.28."
        )
    raise RuntimeError(
        "Failed to parse resume via LLM.\n\n" + joined + hint
    ) from primary_err


def resume_text_to_cv(resume_text: str, *, model: str | None = None) -> dict[str, Any]:
    """Plain resume text → cv.yml dict via LLM (same prompt as cv/pdf_to_yml_llm.py)."""
    text = (resume_text or "").strip()
    if len(text) < 20:
        raise ValueError("Resume has too little text for recognition.")
    prompt = _build_yaml_extraction_prompt(text)
    raw = _resume_yaml_llm_raw(prompt, model=model)
    try:
        return _parse_yaml_response(raw)
    except ValueError:
        # One repair pass: ask the same model to emit clean YAML starting at basics:
        repair_prompt = f"""The previous YAML was invalid.

Return ONLY valid YAML for this schema. First line must be exactly: basics:
No markdown fences. No commentary. Quote any scalar that contains a colon.

SCHEMA:
{CV_YML_SCHEMA}

BROKEN OUTPUT TO FIX:
{clean_yaml_output(raw)[:80000]}

RESUME (source of truth — do not invent facts):
{text[:80000]}
"""
        repaired = _resume_yaml_llm_raw(repair_prompt, model=model)
        return _parse_yaml_response(repaired)


def _pdf_bytes_to_markdown(filename: str | None, raw: bytes) -> str:
    try:
        from liteparse import LiteParse

        parser = LiteParse(
            output_format="markdown",
            image_mode="off",
            extract_links=True,
            ocr_enabled=True,
        )
        suffix = Path(filename or "resume.pdf").suffix or ".pdf"
        tmp = REPO_ROOT / "data" / "_tmp_resume_parse"
        tmp.mkdir(parents=True, exist_ok=True)
        path = tmp / f"upload{suffix}"
        path.write_bytes(raw)
        try:
            return parser.parse(str(path)).text.strip()
        finally:
            path.unlink(missing_ok=True)
    except ImportError:
        return resume_bytes_to_plain_text(filename, raw).strip()


def resume_bytes_to_cv(
    filename: str | None,
    raw: bytes,
    *,
    model: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """PDF/TXT bytes → (plain text, cv.yml dict). PDF uses LiteParse when available."""
    if not raw:
        raise ValueError("Resume file is empty")

    name = (filename or "").lower()
    if name.endswith(".pdf"):
        md = _pdf_bytes_to_markdown(filename, raw)
        plain = resume_bytes_to_plain_text(filename, raw).strip() or md
        source = md if len(md) >= 20 else plain
    else:
        plain = resume_bytes_to_plain_text(filename, raw).strip()
        source = plain

    if len(source) < 20:
        raise ValueError("Resume has too little text for recognition.")

    cv = resume_text_to_cv(source, model=model)
    return plain, cv


def resume_text_to_structured(resume_text: str, *, model: str | None = None) -> dict[str, Any]:
    """Plain resume text → cv.yml structured dict (for DB / pipeline)."""
    from job_application.resume.cv_yaml import harvard_cv_to_structured

    return harvard_cv_to_structured(resume_text_to_cv(resume_text, model=model))
