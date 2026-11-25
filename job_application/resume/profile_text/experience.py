"""Experience, contact, education, and project parsing helpers."""

from __future__ import annotations

import json
import re

from job_application.resume.cv_constants import (
    IMPROVEMENTS_NO_MEASURABLE_ANSWER,
    RESULT_NO_MEASURABLE_ANSWER_LEGACY,
)
from job_application.config import DESIRED_ROLE_MAX_LEN

def _normalize_resume_line(line: str) -> str:
    return re.sub(r"[\u200b\u200c\u200d\ufeff]", "", str(line or "")).strip()


def _split_lines(text: str) -> list[str]:
    return [_normalize_resume_line(ln) for ln in (text or "").splitlines()]


def _parse_contact_links(text: str) -> dict[str, str]:
    links = {"github": "", "linkedin": "", "xing": ""}
    extra: list[str] = []
    for raw in _split_lines(text):
        line = raw.strip()
        if not line:
            continue
        low = line.lower()
        if low.startswith("github") or "github.com" in low:
            links["github"] = line.split(":", 1)[-1].strip() if ":" in line else line
        elif low.startswith("linkedin") or "linkedin.com" in low:
            links["linkedin"] = line.split(":", 1)[-1].strip() if ":" in line else line
        elif low.startswith("xing") or "xing.com" in low:
            links["xing"] = line.split(":", 1)[-1].strip() if ":" in line else line
        else:
            extra.append(line)
    if extra:
        links["_extra"] = "\n".join(extra)
    return links


_PORTFOLIO_LINE_RE = re.compile(r"^\s*portfolio\s*:\s*(.+?)\s*$", re.I)


def _normalize_web_url(raw: str) -> str:
    text = str(raw or "").strip().strip("-•")
    if not text:
        return ""
    if text.lower().startswith(("http://", "https://")):
        return text
    if "@" in text and "://" not in text:
        return text
    return f"https://{text.lstrip('/')}"


def _extract_portfolio_from_plain_text(text: str) -> str:
    """Строки «Portfolio: …» и GitHub Pages (.github.io) из текста PDF."""
    urls: list[str] = []
    seen: set[str] = set()

    def add(raw: str) -> None:
        token = str(raw or "").strip().strip("-•")
        if not token:
            return
        if token.lower().startswith("portfolio:"):
            token = token.split(":", 1)[-1].strip()
        low = token.lower()
        if "linkedin.com" in low or "xing.com" in low:
            return
        if "github.com/" in low and ".github.io" not in low:
            return
        is_url = (
            "://" in low
            or ".github.io" in low
            or re.match(r"^[\w-]+\.github\.io/?$", low)
            or re.match(r"^[\w.-]+\.(io|dev|app|me|site)(?:/[\w./-]*)?$", low)
        )
        if not is_url:
            return
        url = _normalize_web_url(token)
        key = url.lower().rstrip("/")
        if key in seen:
            return
        seen.add(key)
        urls.append(url)

    for raw in _split_lines(text):
        line = raw.strip()
        match = _PORTFOLIO_LINE_RE.match(line)
        if match:
            add(match.group(1))
            continue
        if line.lower().startswith("portfolio:"):
            add(line.split(":", 1)[-1])

    sections = _extract_named_sections(text)
    for line in sections.get("SKILLS") or []:
        if str(line or "").lower().startswith("portfolio:"):
            add(str(line).split(":", 1)[-1])

    return "\n".join(urls)


def _parse_social_links(text: str) -> dict[str, str]:
    """Извлекает GitHub/LinkedIn/Xing/Portfolio из текста (строки, запятые, пробелы)."""
    result = {"github": "", "linkedin": "", "xing": "", "portfolio": ""}
    for raw in re.split(r"[\n,]+|\s+", str(text or "")):
        token = raw.strip().strip("-•")
        if not token:
            continue
        if token.lower().startswith(("github:", "linkedin:", "xing:", "portfolio:")):
            token = token.split(":", 1)[-1].strip()
        low = token.lower()
        if "github.com" in low or low.startswith("github"):
            result["github"] = result["github"] or _normalize_web_url(token)
        elif ".github.io" in low or re.match(r"^[\w-]+\.github\.io/?$", low):
            url = _normalize_web_url(token)
            result["portfolio"] = result["portfolio"] or url
            result["github"] = result["github"] or url
        elif "linkedin.com" in low or low.startswith("linkedin"):
            result["linkedin"] = result["linkedin"] or _normalize_web_url(token)
        elif "xing.com" in low or low.startswith("xing"):
            result["xing"] = result["xing"] or _normalize_web_url(token)
    portfolio_block = _extract_portfolio_from_plain_text(str(text or ""))
    if portfolio_block and not result["portfolio"]:
        result["portfolio"] = portfolio_block.splitlines()[0].strip()
    return result


def _compose_links_text(*sources: str) -> str:
    """Собирает поле links для чата: LinkedIn + GitHub + прочие URL без дублей."""
    merged = _parse_social_links("\n".join(str(s or "").strip() for s in sources if str(s or "").strip()))
    lines = [merged[key] for key in ("linkedin", "github", "xing") if merged.get(key)]
    if merged.get("portfolio"):
        pf = str(merged["portfolio"]).strip()
        pf_key = pf.lower().rstrip("/")
        if pf_key not in {line.lower().rstrip("/") for line in lines}:
            lines.append(pf)
    seen = {line.lower().rstrip("/") for line in lines}
    for source in sources:
        for raw in re.split(r"[\n,]+|\s+", str(source or "")):
            token = raw.strip().strip("-•")
            if not token:
                continue
            if token.lower().startswith(("github:", "linkedin:", "xing:")):
                token = token.split(":", 1)[-1].strip()
            low = token.lower()
            if any(host in low for host in ("github.com", "linkedin.com", "xing.com")):
                continue
            norm = low.rstrip("/")
            if norm not in seen:
                seen.add(norm)
                lines.append(token)
    return "\n".join(lines)


def _merge_social_links(*sources: str) -> tuple[str, dict[str, str]]:
    """По одной ссылке на тип: ранние источники важнее, поздние заполняют только пробелы."""
    merged = {"linkedin": "", "github": "", "xing": "", "portfolio": ""}
    for source in sources:
        text = str(source or "").strip()
        if not text:
            continue
        parsed = _parse_social_links(text)
        for key in ("linkedin", "github", "xing", "portfolio"):
            if not merged[key] and parsed.get(key):
                merged[key] = parsed[key]
    lines = [merged[k] for k in ("linkedin", "github", "xing") if merged[k]]
    if merged["portfolio"]:
        pf = merged["portfolio"]
        if pf.lower().rstrip("/") not in {x.lower().rstrip("/") for x in lines}:
            lines.append(pf)
    return "\n".join(lines), merged


def _seed_personal_links_from_plain(structured: dict) -> dict:
    """После LLM/PDF: дополнить personal.linkedin/github из текста резюме, не затирая portfolio."""
    data = dict(structured or {})
    plain = str(data.get("_resume_plain_text") or "").strip()
    if not plain:
        return data
    pers = data.get("personal") if isinstance(data.get("personal"), dict) else {}
    pers = dict(pers)
    contact = _extract_contact_from_plain_text(plain)
    portfolio = str(pers.get("portfolio") or "").strip()
    parsed_pf = _parse_social_links(portfolio)
    if not parsed_pf["linkedin"] and not str(pers.get("linkedin") or "").strip() and contact.get("linkedin"):
        pers["linkedin"] = contact["linkedin"]
    if not parsed_pf["github"] and not str(pers.get("github") or "").strip() and contact.get("github"):
        pers["github"] = contact["github"]
    if not portfolio and contact.get("portfolio"):
        pers["portfolio"] = contact["portfolio"]
    data["personal"] = pers
    return data


def _looks_like_contact_line(line: str) -> bool:
    text = str(line or "").strip()
    low = text.lower()
    if "@" in text:
        return True
    if re.search(r"\+?\d[\d\s().-]{7,}\d", text) and ("|" in text or "phone" in low or "whatsapp" in low):
        return True
    if "|" in text:
        parts = [p.strip() for p in text.split("|")]
        if any("@" in p for p in parts) and any(re.search(r"\+?\d", p) for p in parts):
            return True
    return False


def _looks_like_invalid_job_company(company: str) -> bool:
    text = str(company or "").strip()
    if not text:
        return True
    if "@" in text:
        return True
    if re.fullmatch(r"\+?\d[\d\s().-]{7,}\d", text):
        return True
    if _looks_like_contact_line(text):
        return True
    return False


def _is_valid_job_header(job: dict) -> bool:
    company = str(job.get("company") or "").strip()
    title = str(job.get("title") or job.get("position") or "").strip()
    if not company or not title:
        return False
    return not _looks_like_invalid_job_company(company)


def _looks_like_fake_experience_job(job: dict) -> bool:
    """Курсы, сертификаты и образование — не места работы."""
    company = str(job.get("company") or "").strip()
    title = str(job.get("position") or job.get("title") or "").strip()
    blob = f"{company} {title}".strip()
    low = blob.lower()
    if not blob:
        return True
    if _looks_like_course_line(blob) or _looks_like_education_line(blob):
        return True
    if low.startswith(("certificates:", "certificate:", "certi")):
        return True
    if "certi" in low and ("google" in low or "udemy" in low or "professional data engineer" in low):
        return True
    fake_markers = (
        "udemy",
        "coursera",
        "bootcamp",
        "education academy",
        "university",
        "college",
        "master's degree",
        "masters degree",
        "bachelor",
        "degree in",
        "coursework",
        "google analytics iq",
        "google ads",
        "google cloud professional",
    )
    if any(marker in low for marker in fake_markers):
        return True
    return False


def _is_plausible_experience_job(job: dict) -> bool:
    if not isinstance(job, dict):
        return False
    if not _is_valid_job_header(job):
        return False
    return not _looks_like_fake_experience_job(job)


def _dedupe_experience_jobs(jobs: list[dict]) -> list[dict]:
    seen: set[tuple[str, str]] = set()
    out: list[dict] = []
    for job in jobs:
        if not _is_plausible_experience_job(job):
            continue
        company = str(job.get("company") or "").strip()
        dates = str(job.get("dates") or "").strip()
        sig = (_company_match_key(company), dates[:48])
        if sig in seen:
            continue
        seen.add(sig)
        out.append(job)
    return out


def _parse_experience_header_line(line: str) -> dict | None:
    """Разбирает строку заголовка места работы без явного JSON."""
    text = str(line or "").strip()
    if not text or text.startswith("-") or text.startswith("•"):
        return None
    if _looks_like_contact_line(text):
        return None
    if _is_dates_only_line(text):
        return None
    if _looks_like_language_line(text):
        return None

    dot_job = _parse_dot_format_job_line(text)
    if dot_job:
        return dot_job

    paren_job = _parse_paren_company_job_line(text)
    if paren_job:
        return paren_job

    if "|" in text:
        parts = [p.strip() for p in text.split("|") if p.strip()]
        company = parts[1] if len(parts) > 1 else ""
        if _looks_like_invalid_job_company(company):
            return None
        return {
            "title": parts[0] if parts else "",
            "company": company,
            "dates": parts[2] if len(parts) > 2 else "",
            "summary": "",
            "highlights": [],
        }

    if "," in text and "|" not in text:
        if not (re.search(r"\([^)]*\d{4}[^)]*\)", text) and _ROLE_LINE_HINT.search(text)):
            if len(text) <= 100 and not _looks_like_duty_line(text) and _ROLE_LINE_HINT.search(text):
                parts = [p.strip() for p in text.split(",") if p.strip()]
                if len(parts) >= 2:
                    title = parts[0]
                    company = parts[1]
                    dates = ", ".join(parts[2:]) if len(parts) > 2 else ""
                    if re.search(r"\d{4}", company) and not re.search(r"\d{4}", dates):
                        dates = ", ".join(parts[1:])
                        company = ""
                    if not _looks_like_invalid_job_company(company):
                        return {"title": title, "company": company, "dates": dates, "summary": "", "highlights": []}

    for sep in (" — ", " – ", " - "):
        if sep in text:
            left, right = text.split(sep, 1)
            left, right = left.strip(), right.strip()
            if left and right:
                if re.search(r"\d{4}", right) or re.search(r"(present|current|настоящ)", right, re.I):
                    if _ROLE_LINE_HINT.search(left):
                        return {"title": left, "company": "", "dates": right, "summary": "", "highlights": []}
                elif _ROLE_LINE_HINT.search(left) or _ROLE_LINE_HINT.search(right):
                    return {"title": right, "company": left, "dates": "", "summary": "", "highlights": []}

    match = re.search(r"\s+at\s+", text, flags=re.I)
    if match:
        return {
            "title": text[: match.start()].strip(),
            "company": text[match.end() :].strip(),
            "dates": "",
            "summary": "",
            "highlights": [],
        }

    return None


_ROLE_LINE_HINT = re.compile(
    r"(?:Engineer|Developer|Analyst|Architect|Manager|Consultant|Scientist|Intern|Assistant|Lead|Director|Specialist|Researcher)",
    re.I,
)


_MONTH_NAME = (
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|"
    r"Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
)


_DATE_TAIL_RE = re.compile(
    rf"(?P<dates>{_MONTH_NAME}[\w\s\.\-–—/]*(?:\d{{4}}|Current|Present)?"
    rf"[\w\s\.\-–—/]*(?:{_MONTH_NAME}[\w\s\.\-–—/]*\d{{4}}|Current|Present|\d{{4}})?)\s*$",
    re.I,
)


def _normalize_dates_fragment(text: str) -> str:
    raw = str(text or "").strip()
    raw = re.sub(r"(\d{4})([A-Za-z])", r"\1 - \2", raw)
    raw = re.sub(r"([a-z])(\d{4})", r"\1 \2", raw)
    raw = re.sub(r"(\w)(Current|Present)", r"\1 - \2", raw, flags=re.I)
    raw = re.sub(r"\s+", " ", raw)
    return raw.strip(" .-")


def _parse_dot_format_job_line(line: str) -> dict | None:
    """
    PDF-формат: «DataEngineer.Selfemployed. August2023-February2024»
    или «Big Data Engineer. Trinetix. February 2024 - Current».
    """
    text = str(line or "").strip()
    if not text or "|" in text or not _ROLE_LINE_HINT.search(text):
        return None
    if text.lower().startswith(("udemy", "it education", "course", "master", "degree", "phone", "e-mail", "email")):
        return None

    dm = _DATE_TAIL_RE.search(text)
    if not dm:
        ym = re.search(r"(\d{4}[\w\s\.\-–—]+(?:\d{4}|Current|Present)?)\s*$", text, re.I)
        if not ym:
            return None
        dates = _normalize_dates_fragment(ym.group(1))
        prefix = text[: ym.start()].strip().rstrip(".")
    else:
        dates = _normalize_dates_fragment(dm.group("dates"))
        prefix = text[: dm.start()].strip().rstrip(".")

    if not prefix:
        return None

    parts = [p.strip() for p in prefix.split(".") if p.strip()]
    if len(parts) >= 2:
        title = parts[0]
        company = ".".join(parts[1:])
    else:
        title, company = _split_merged_position_company(parts[0], "")

    title = _humanize_camel_case(title)
    company = _normalize_company_label(company)
    if not title or not company:
        return None

    return {"title": title, "company": company, "dates": dates, "summary": "", "highlights": []}


def _paren_content_looks_like_dates(content: str) -> bool:
    body = str(content or "").strip()
    return bool(re.search(r"\d{4}", body)) and bool(re.search(_MONTH_NAME, body, re.I))


def _parse_paren_company_job_line(line: str) -> dict | None:
    """«Senior Data Engineer (Valtech)» — должность и компания в скобках."""
    text = str(line or "").strip()
    if not text or "|" in text or _looks_like_contact_line(text):
        return None
    if not _ROLE_LINE_HINT.search(text):
        return None
    match = re.match(r"^(?P<title>.+?)\s*\((?P<company>[^()]+)\)\s*$", text)
    if not match:
        return None
    company_raw = match.group("company").strip()
    if _paren_content_looks_like_dates(company_raw) or _looks_like_invalid_job_company(company_raw):
        return None
    title = re.sub(r"\s+", " ", match.group("title").strip())
    company = _normalize_company_label(company_raw)
    if not title or not company:
        return None
    return {"title": title, "company": company, "dates": "", "summary": "", "highlights": []}


def _is_dates_only_line(line: str) -> bool:
    text = str(line or "").strip()
    if not text or len(text) > 48:
        return False
    if re.match(rf"^{_MONTH_NAME}\s+\d{{4}}\s*$", text, re.I):
        return True
    if _ROLE_LINE_HINT.search(text):
        return False
    if _looks_like_noise_line(text):
        return False
    if _DATE_TAIL_RE.fullmatch(text):
        return True
    return bool(
        re.match(rf"^{_MONTH_NAME}\s+\d{{4}}\s*$", text, re.I)
        or re.match(rf"^{_MONTH_NAME}\s+\d{{4}}\s*[—–-]\s*{_MONTH_NAME}\s+\d{{4}}\s*$", text, re.I)
    )


def _company_match_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(name or "").lower())


def _job_sort_key(job: dict) -> tuple[int, int]:
    dates = str(job.get("dates") or "")
    years = [int(y) for y in re.findall(r"\d{4}", dates)]
    if not years:
        return (0, 0)
    if re.search(r"current|present|настоящ", dates, re.I):
        return (years[0], 9999)
    return (years[0], years[-1] if len(years) > 1 else years[0])


def _sort_jobs_by_recency(jobs: list[dict]) -> list[dict]:
    return sorted(jobs, key=_job_sort_key, reverse=True)


def _looks_like_noise_line(line: str) -> bool:
    """Строки из SKILLS/CONTACT/курсов — не обязанности на работе."""
    low = str(line or "").strip().lower()
    if len(low) < 12:
        return True
    noise_prefixes = (
        "hands-on experience",
        "tools:",
        "domain expertise",
        "experience with jira",
        "experience with asana",
        "python,",
        "sql (",
        "sql,",
        "git (",
        "git ",
        "phone",
        "e-mail",
        "email:",
        "github:",
        "linkedin:",
        "xing:",
        "udemy",
        "it education",
        "donetsk national",
        "master's degree",
        "objective",
        "skills",
        "languages",
        "courses",
        "y u l i i a",
        "a n t o n o v a",
    )
    if any(low.startswith(p) for p in noise_prefixes):
        return True
    if re.match(r"^[a-z+/\s]+(?:github|gitlab|linkedin)", low):
        return True
    return False


def _is_standalone_bullet_marker(line: str) -> bool:
    text = re.sub(r"[\u200b\u200c\u200d\ufeff\s]+", "", str(line or "").strip())
    return text in {"●", "•", "-", "▪", "◦", "·"}


def _looks_like_duty_line(line: str) -> bool:
    text = str(line or "").strip()
    if not text:
        return False
    if _parse_paren_company_job_line(text) or _parse_dot_format_job_line(text):
        return False
    if "|" in text and not _looks_like_contact_line(text):
        return False
    low = text.lower()
    if _looks_like_noise_line(text):
        return False
    if len(low) < 18:
        return False
    duty_markers = (
        "developed",
        "built",
        "managed",
        "implemented",
        "automated",
        "worked",
        "created",
        "wrote",
        "maintained",
        "collected",
        "monitoring",
        "design",
        "deliver",
        "optimiz",
        "integrat",
        "pipeline",
        "process",
        "system",
        "spearhead",
        "strateg",
        "recommend",
        "analyzed",
        "engineered",
        "architected",
        "led ",
        "drove",
        "collaborat",
        "established",
        "launched",
        "extracted",
    )
    if any(m in low for m in duty_markers):
        return True
    if " data " in f" {low} " and not _ROLE_LINE_HINT.search(text):
        return True
    return False


def _is_bullet_continuation_line(line: str, previous: str) -> bool:
    """PDF переносит длинные буллеты на следующую строку — склеиваем."""
    text = str(line or "").strip()
    prev = str(previous or "").strip()
    if not text or not prev:
        return False
    if _match_section_header(text):
        return False
    if _parse_job_header_line(text) or _parse_paren_company_job_line(text):
        return False
    if _is_dates_only_line(text):
        return False
    if text.startswith(("-", "•", "●", "▪", "◦")):
        return False
    if _ROLE_LINE_HINT.search(text) and "(" in text and ")" in text:
        return False
    if _looks_like_duty_line(text) and _looks_like_duty_line(prev):
        if text[:1].islower():
            return True
        return False
    if prev.rstrip().endswith((".", "!", "?", ";")):
        return False
    if text[0].islower():
        return True
    incomplete_endings = (
        ",", " and", " or", " enabling", " including", " with", " for", " to",
        " the", " a", " an", " of", " in", " on", " into", " via", " through",
        " covering", " regarding", " using", " that", " which", " into",
    )
    if any(prev.rstrip().endswith(ending) for ending in incomplete_endings):
        return True
    if len(prev) > 55 and not prev.rstrip().endswith((".", "!", "?")):
        return True
    return False


def _merge_wrapped_highlights(highlights: list[str]) -> list[str]:
    merged: list[str] = []
    for raw in highlights:
        text = str(raw or "").strip()
        if not text:
            continue
        if merged and _is_bullet_continuation_line(text, merged[-1]):
            merged[-1] = f"{merged[-1]} {text}".strip()
        else:
            merged.append(text)
    return merged


def _append_experience_bullet(current: dict, line: str, *, force: bool = False) -> None:
    highlights = current.setdefault("highlights", [])
    bullet = re.sub(r"^[\-•●▪◦\u200b\s]+", "", line).rstrip(";").strip()
    if not bullet:
        return
    if highlights and _is_bullet_continuation_line(bullet, highlights[-1]):
        highlights[-1] = f"{highlights[-1]} {bullet}".strip()
        return
    if force or line.startswith(("-", "•", "●", "▪", "◦")) or _looks_like_duty_line(line):
        highlights.append(bullet)


def _parse_job_header_line(line: str) -> dict | None:
    return _parse_experience_header_line(line)


def _split_semicolon_duty_chunks(text: str) -> list[str]:
    """«Duty one; Duty two; Duty three» → отдельные буллеты (PDF Yuliia)."""
    chunk = str(text or "").strip()
    if not chunk or ";" not in chunk:
        return [chunk] if chunk else []
    parts = [p.strip() for p in chunk.split(";") if p.strip()]
    if len(parts) < 2:
        return [chunk]
    duty_like = sum(1 for p in parts if len(p) > 18 and not _looks_like_noise_line(p))
    if duty_like >= 2:
        return parts
    return [chunk]


def _parse_role_company_next_line(role_line: str, company_line: str) -> dict | None:
    """PDF: должность+даты на одной строке, компания на следующей (Energozbyt)."""
    role_text = str(role_line or "").strip()
    company_text = str(company_line or "").strip()
    if not role_text or not company_text:
        return None
    if not _ROLE_LINE_HINT.search(role_text):
        return None
    role_header = _parse_job_header_line(role_text)
    if role_header and _is_valid_job_header(role_header):
        return None
    company_header = _parse_job_header_line(company_text)
    if company_header and _is_valid_job_header(company_header):
        return None
    if _looks_like_noise_line(company_text):
        return None

    dates = ""
    dm = _DATE_TAIL_RE.search(role_text)
    paren_matches = list(
        re.finditer(
            rf"\((?:{_MONTH_NAME}[\w\s\-–—/]*\d{{4}}[\w\s\-–—/]*(?:{_MONTH_NAME}[\w\s\-–—/]*\d{{4}}|Present|Current)?)\)",
            role_text,
            re.I,
        )
    )
    if paren_matches:
        date_parts = [_normalize_dates_fragment(m.group(0).strip("()")) for m in paren_matches]
        dates = "; ".join(x for x in date_parts if x)
        title = role_text
        for match in reversed(paren_matches):
            title = f"{title[: match.start()]} {title[match.end() :]}".strip()
        title = re.sub(r"\s+and\s+", " and ", title, flags=re.I)
        title = re.sub(r"\s+", " ", title).strip(" .;")
    elif dm:
        dates = _normalize_dates_fragment(dm.group("dates"))
        title = role_text[: dm.start()].strip().rstrip(".")
    else:
        return None
    company = _normalize_company_label(company_text)
    if not title or not company:
        return None
    return {"title": title, "company": company, "dates": dates, "summary": "", "highlights": []}


def _parse_experience_sections(text: str) -> list[dict]:
    """Последовательный формат: заголовок → буллеты (resume.txt, нормальный PDF)."""
    jobs: list[dict] = []
    current: dict | None = None
    awaiting_bullet = False
    lines = _split_lines(text)
    idx = 0
    while idx < len(lines):
        line = lines[idx].strip()
        idx += 1
        if not line:
            continue

        if _is_standalone_bullet_marker(line):
            awaiting_bullet = True
            continue

        header = _parse_job_header_line(line)
        if header and idx < len(lines):
            next_line = lines[idx].strip()
            if not str(header.get("dates") or "").strip() and _is_dates_only_line(next_line):
                header["dates"] = _normalize_dates_fragment(next_line)
                idx += 1
        if header is None and idx < len(lines):
            header = _parse_role_company_next_line(line, lines[idx].strip())
            if header:
                idx += 1

        if header and _is_plausible_experience_job(_normalize_llm_job_entry(header)):
            current = {**header, "highlights": []}
            jobs.append(current)
            awaiting_bullet = False
            continue

        if current is None:
            continue

        if awaiting_bullet:
            _append_experience_bullet(current, line, force=True)
            awaiting_bullet = False
            continue

        if _looks_like_noise_line(line):
            continue

        _append_experience_bullet(current, line)

    return _dedupe_experience_jobs([_normalize_llm_job_entry(raw) for raw in jobs])


def _job_has_description(job: dict) -> bool:
    return bool(
        str(job.get("raw_description") or job.get("responsibilities_narrative") or "").strip()
        or job.get("highlights")
        or job.get("responsibilities")
    )


def _collect_job_headers_from_text(text: str) -> list[dict]:
    jobs: list[dict] = []
    seen: set[tuple[str, str]] = set()
    lines = _split_lines(text)
    idx = 0
    while idx < len(lines):
        line = lines[idx].strip()
        idx += 1
        if not line:
            continue
        parsed = _parse_job_header_line(line)
        if parsed and idx < len(lines):
            next_line = lines[idx].strip()
            if not str(parsed.get("dates") or "").strip() and _is_dates_only_line(next_line):
                parsed["dates"] = _normalize_dates_fragment(next_line)
                idx += 1
        if parsed is None and idx < len(lines):
            parsed = _parse_role_company_next_line(line, lines[idx].strip())
            if parsed:
                idx += 1
        if not parsed:
            continue
        job = _normalize_llm_job_entry(parsed)
        if not _is_plausible_experience_job(job):
            continue
        company = str(job.get("company") or "").strip()
        dates = str(job.get("dates") or "").strip()
        sig = (_company_match_key(company), dates)
        if sig in seen:
            continue
        seen.add(sig)
        jobs.append(job)
    return jobs


_BULLET_SIGNATURES: list[tuple[tuple[str, ...], str]] = [
    (("step functions", "glue jobs", "aurora", "opensearch", "ingestion → raw", "ingestion -> raw"), "trinetix"),
    (("etl processes", "data models and schemas", "troubleshooted system performance"), "selfemployed"),
    ((" ray", "pytest", "pipeline execution", "parsed data"), "hrforecast"),
    (("logistics platform", "python scripts", "business systems"), "auchanretail"),
    (("data processing systems", "operational data", "analytical reports", "storage solutions"), "energozbyt"),
    (("coal", "krasnolimanskaya"), "krasnolimanskaya"),
]


def _attach_bullets_from_resume_text(jobs: list[dict], text: str) -> None:
    """Привязывает обязанности к компаниям (PDF с перемешанным текстом)."""
    if not jobs or not text:
        return

    by_key = {_company_match_key(j.get("company")): j for j in jobs}
    raw_fragments: list[str] = []
    awaiting_bullet = False

    for raw in _split_lines(text):
        line = raw.strip()
        if not line or _looks_like_noise_line(line):
            continue
        if _parse_job_header_line(line):
            awaiting_bullet = False
            continue
        if line.upper() in {"SKILLS", "OBJECTIVE", "EDUCATION", "EXPERIENCE", "LANGUAGES", "COURSES", "CONTACT"}:
            awaiting_bullet = False
            continue
        if _ROLE_LINE_HINT.search(line) and _DATE_TAIL_RE.search(line):
            awaiting_bullet = False
            continue
        if _is_standalone_bullet_marker(line):
            awaiting_bullet = True
            continue
        if awaiting_bullet:
            raw_fragments.append(line)
            awaiting_bullet = False
            continue
        if line.startswith(("-", "•", "●", "▪", "◦")) or _looks_like_duty_line(line):
            chunk = re.sub(r"^[\-•●▪◦\u200b\s]+", "", line).rstrip(";").strip()
            if chunk:
                raw_fragments.append(chunk)
            continue
        if raw_fragments and _is_bullet_continuation_line(line, raw_fragments[-1]):
            raw_fragments[-1] = f"{raw_fragments[-1]} {line}".strip()

    expanded: list[str] = []
    for chunk in _merge_wrapped_highlights(raw_fragments):
        expanded.extend(_split_semicolon_duty_chunks(chunk))
    duty_lines = [c for c in expanded if _looks_like_duty_line(c)]

    for chunk in duty_lines:
        low = f" {chunk.lower()} "
        matched = False
        for signatures, company_key in _BULLET_SIGNATURES:
            if not any(f" {sig} " in low or low.strip().startswith(sig) for sig in signatures):
                if not any(sig in chunk.lower() for sig in signatures):
                    continue
            job = by_key.get(company_key)
            if not job:
                for key, candidate in by_key.items():
                    if company_key in key or key in company_key:
                        job = candidate
                        break
            if not job:
                continue
            highlights = job.setdefault("highlights", [])
            if chunk not in highlights:
                highlights.append(chunk)
            matched = True
            break
        if not matched and len(jobs) == 1:
            jobs[0].setdefault("highlights", []).append(chunk)

    for job in jobs:
        narrative = _job_narrative_from_parts(job.get("highlights"))
        if narrative:
            job["responsibilities_narrative"] = narrative
            job["raw_description"] = narrative


def _experience_section_is_usable(exp_lines: list[str]) -> bool:
    if len(exp_lines) < 4:
        return False
    valid = 0
    for raw in exp_lines:
        line = str(raw or "").strip()
        if not line:
            continue
        header = _parse_job_header_line(line)
        if header and _is_valid_job_header(header):
            valid += 1
            continue
        if _parse_paren_company_job_line(line):
            valid += 1
    return valid >= 2


def _pdf_has_dot_format_jobs(text: str) -> bool:
    for raw in _split_lines(text):
        if _parse_dot_format_job_line(raw.strip()):
            return True
    return False


def _extract_jobs_from_resume_plain_text(text: str) -> list[dict]:
    """Извлекает места работы и описания из plain text PDF/TXT."""
    if not str(text or "").strip():
        return []

    if _pdf_has_dot_format_jobs(text):
        jobs = _collect_job_headers_from_text(text)
        if jobs:
            _attach_bullets_from_resume_text(jobs, text)
            return _sort_jobs_by_recency(jobs)

    sections = _extract_named_sections(text)
    exp_lines = sections.get("EXPERIENCE") or []
    candidates: list[str] = []
    if _experience_section_is_usable(exp_lines):
        candidates.append("\n".join(exp_lines))
    candidates.append(text)

    for source in candidates:
        if not str(source or "").strip():
            continue
        section_jobs = _parse_experience_sections(source)
        described = sum(1 for j in section_jobs if _job_has_description(j))
        if section_jobs and described >= max(1, len(section_jobs) // 2):
            return _sort_jobs_by_recency(section_jobs)

    jobs = _collect_job_headers_from_text(text)
    if not jobs:
        return _parse_experience_sections(text)

    _attach_bullets_from_resume_text(jobs, text)
    return _sort_jobs_by_recency(jobs)


_SECTION_HEADERS = frozenset(
    {"CONTACT", "OBJECTIVE", "SKILLS", "EXPERIENCE", "COURSES", "EDUCATION", "LANGUAGES", "PROJECTS", "INTERESTS"}
)


_SECTION_ALIASES = {
    "PROFESSIONALEXPERIENCE": "EXPERIENCE",
    "WORKEXPERIENCE": "EXPERIENCE",
    "EMPLOYMENTHISTORY": "EXPERIENCE",
    "CAREERHISTORY": "EXPERIENCE",
    "SKILLSACCOMPLISHMENT": "SKILLS",
    "SKILLSANDACCOMPLISHMENT": "SKILLS",
    "SKILLSACCOMPLISHMENTS": "SKILLS",
    "SKILLS&ACCOMPLISHMENT": "SKILLS",
    "SKILLS&ACCOMPLISHMENTS": "SKILLS",
    "CERTIFICATIONS": "COURSES",
    "CERTIFICATES": "COURSES",
}


def _normalize_section_header(line: str) -> str:
    return re.sub(r"\s+", "", str(line or "").strip().upper())


def _match_section_header(line: str) -> str | None:
    token = _normalize_section_header(line)
    if token in _SECTION_ALIASES:
        return _SECTION_ALIASES[token]
    for header in _SECTION_HEADERS:
        if token == header:
            return header
    if token in {"EXPERIENCE", "PROFESSIONALEXPERIENCE", "WORKEXPERIENCE", "EMPLOYMENTHISTORY", "CAREERHISTORY"}:
        return "EXPERIENCE"
    if token in {
        "SKILLS",
        "SKILLS&ACCOMPLISHMENT",
        "SKILLS&ACCOMPLISHMENTS",
        "SKILLSACCOMPLISHMENT",
        "SKILLSACCOMPLISHMENTS",
    }:
        return "SKILLS"
    return None


def _extract_named_sections(text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {h: [] for h in _SECTION_HEADERS}
    current: str | None = None
    for raw in _split_lines(text):
        line = raw.strip()
        if not line:
            continue
        header = _match_section_header(line)
        if header:
            current = header
            continue
        if current:
            sections[current].append(line)
    return sections


def _looks_like_certificate_line(line: str) -> bool:
    low = str(line or "").strip().lower()
    return low.startswith("certificates:") or low.startswith("certificate:")


def _looks_like_course_line(line: str) -> bool:
    low = str(line or "").strip().lower()
    if len(low) < 8:
        return False
    if "energozbyt" in low or "ukrainian railways" in low:
        return False
    if low.startswith("certificates:") or low.startswith("certificate:"):
        return False
    markers = (
        "udemy",
        "coursera",
        "bootcamp",
        "certification",
        "certificate",
        "itea",
        "education academy",
        "course -",
        "course –",
    )
    if any(m in low for m in markers):
        return True
    if _ROLE_LINE_HINT.search(line) and _DATE_TAIL_RE.search(line) and "course" not in low:
        return False
    return False


def _looks_like_language_line(line: str) -> bool:
    s = str(line or "").strip()
    if not s or len(s) > 70:
        return False
    if re.match(
        r"^(Ukrainian|Russian|English|German|French|Spanish|Chinese|Polish|Czech)"
        r"(\s*/\s*[A-Za-z]+)?(\s*[—–-]\s*.+)?$",
        s,
        re.I,
    ):
        return True
    if re.match(r"^[A-Za-z]+/[A-Za-z]+(\s*[—–-]\s*.+)?$", s):
        return True
    if _looks_like_noise_line(s) or _looks_like_duty_line(s):
        return False
    if _looks_like_course_line(s):
        return False
    return False


def _looks_like_education_line(line: str) -> bool:
    low = str(line or "").strip().lower()
    if not low or len(low) > 160:
        return False
    if _looks_like_duty_line(line) or _looks_like_course_line(line) or _looks_like_language_line(line):
        return False
    if _parse_job_header_line(line) or _parse_dot_format_job_line(line):
        return False
    markers = ("university", "college", "institute", "academy", "degree", "bachelor", "master", "phd", "diploma")
    return any(m in low for m in markers)


def _dedupe_lines(lines: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in lines:
        line = str(raw or "").strip()
        if not line:
            continue
        key = line.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(line)
    return out


def _lines_to_bullet_block(lines: list[str]) -> str:
    return "\n".join(f"- {line.lstrip('-• ').strip()}" for line in _dedupe_lines(lines) if line.strip())


def _join_phone_parts(phones: list[str]) -> str:
    cleaned = [p.strip() for p in phones if p.strip()]
    if not cleaned:
        return ""
    return " | ".join(cleaned) if len(cleaned) > 1 else cleaned[0]


def _looks_like_location_line(line: str) -> bool:
    """Город/страна в шапке резюме — не буллет опыта и не длинное предложение."""
    text = str(line or "").strip()
    if not text or len(text) > 72:
        return False
    low = text.lower()
    if "@" in text or _looks_like_contact_line(text) or _match_section_header(text):
        return False
    if low.startswith(("email", "e-mail", "phone", "whatsapp", "linkedin", "github", "portfolio")):
        return False
    if _ROLE_LINE_HINT.search(text) and "|" in text:
        return False
    if re.search(r"\+?\d[\d\s().-]{7,}", text):
        return False
    if text.endswith("."):
        return False
    if text.count(",") > 2:
        return False
    if len(text.split()) > 9:
        return False
    if _looks_like_duty_line(text):
        return False
    duty_words = (
        "validate",
        "testing",
        "test ",
        "applications",
        "backend",
        "database",
        "automation",
        "quality assurance",
        "requirements",
        "defect",
        "regression",
        "integration",
    )
    if any(w in low for w in duty_words):
        return False
    if "," in text:
        left, right = [p.strip() for p in text.split(",", 1)]
        if left and right and len(right.split()) <= 5 and not right.endswith("."):
            return True
    if re.search(r"\b(poland|ukraine|germany|usa|uk|remote|lengerich|berlin)\b", low):
        return True
    return False


def _sanitize_contact_location(text: str) -> str:
    cleaned = str(text or "").strip()
    return cleaned if _looks_like_location_line(cleaned) else ""


def _resume_header_lines(text: str, *, limit: int = 15) -> list[str]:
    """Строки шапки до первой секции (SUMMARY/EXPERIENCE/...)."""
    lines: list[str] = []
    stop_sections = {
        "PROFESSIONAL SUMMARY",
        "SUMMARY",
        "PROFESSIONAL EXPERIENCE",
        "EXPERIENCE",
        "WORK EXPERIENCE",
        "SKILLS",
        "EDUCATION",
        "CERTIFICATES",
        "CERTIFICATIONS",
        "COURSES",
    }
    for raw in _split_lines(text):
        line = raw.strip()
        if not line:
            continue
        header = _match_section_header(line)
        if header and header in stop_sections:
            break
        lines.append(line)
        if len(lines) >= limit:
            break
    return lines


def _extract_contact_from_plain_text(text: str) -> dict[str, str]:
    out: dict[str, str] = {"phone": "", "email": "", "linkedin": "", "github": "", "portfolio": "", "location": ""}
    phones: list[str] = []
    header_lines = _resume_header_lines(text)

    for raw in _split_lines(text):
        line = raw.strip()
        low = line.lower()
        for chunk in re.split(r"[|\s]+", line) if ("linkedin.com" in low or "github.com" in low) else [line]:
            chunk = chunk.strip()
            if not chunk:
                continue
            parsed_chunk = _parse_social_links(chunk)
            if parsed_chunk["linkedin"] and not out["linkedin"]:
                out["linkedin"] = parsed_chunk["linkedin"]
            if parsed_chunk["github"] and not out["github"]:
                out["github"] = parsed_chunk["github"]
        if "|" in line and ("@" in line or re.search(r"\+?\d", line)):
            for part in (p.strip() for p in line.split("|")):
                chunk = part.split(":", 1)[-1].strip() if ":" in part else part.strip()
                if "@" in chunk and not out["email"]:
                    out["email"] = chunk
                elif re.search(r"\+?\d[\d\s().-]{7,}", chunk):
                    phones.append(chunk)
            continue
        if low.startswith("phone") or low.startswith("whatsapp"):
            phone_val = line.split(":", 1)[-1].strip() if ":" in line else line
            if "|" in phone_val:
                for part in (p.strip() for p in phone_val.split("|")):
                    if re.search(r"\+?\d[\d\s().-]{7,}", part):
                        phones.append(part)
            elif phone_val:
                phones.append(phone_val)
        elif low.startswith("e-mail") or low.startswith("email"):
            out["email"] = line.split(":", 1)[-1].strip() if ":" in line else line
        else:
            parsed_line = _parse_social_links(line)
            if parsed_line["linkedin"] and not out["linkedin"]:
                out["linkedin"] = parsed_line["linkedin"]
            if parsed_line["github"] and not out["github"]:
                out["github"] = parsed_line["github"]

    for line in header_lines[1:]:
        if _looks_like_location_line(line):
            out["location"] = line
            break

    for line in header_lines:
        if not out["email"]:
            email_match = re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", line)
            if email_match:
                out["email"] = email_match.group(0)
        if not phones:
            phone_match = re.search(r"(?<!\w)(\+\d[\d\s().-]{6,}\d|\d[\d\s().-]{7,}\d)(?!\d)", line)
            if phone_match:
                phones.append(phone_match.group(1).strip())

    out["phone"] = _join_phone_parts(phones)
    portfolio = _extract_portfolio_from_plain_text(text)
    if portfolio:
        out["portfolio"] = portfolio
    return out


def enrich_structured_personal_from_plain(structured: dict) -> dict:
    """Дополняет personal из _resume_plain_text (city, оба телефона, email)."""
    data = _seed_personal_links_from_plain(structured)
    plain = str(data.get("_resume_plain_text") or "").strip()
    if not plain:
        return data
    contact = _extract_contact_from_plain_text(plain)
    pers = dict(data.get("personal") or {}) if isinstance(data.get("personal"), dict) else {}
    existing_loc = _sanitize_contact_location(str(pers.get("location") or pers.get("city") or ""))
    plain_loc = _sanitize_contact_location(contact.get("location", ""))
    if plain_loc:
        pers["location"] = plain_loc
    elif existing_loc:
        pers["location"] = existing_loc
    elif pers.get("location") or pers.get("city"):
        pers.pop("location", None)
    if contact.get("email") and not str(pers.get("email") or "").strip():
        pers["email"] = contact["email"]
    if contact.get("phone"):
        existing = str(pers.get("phone") or "").strip()
        if not existing or existing.count("|") < contact["phone"].count("|"):
            pers["phone"] = contact["phone"]
    portfolio = str(pers.get("portfolio") or "").strip()
    if portfolio:
        links, parsed = _merge_social_links(portfolio, pers.get("linkedin"), pers.get("github"))
    else:
        links, parsed = _merge_social_links(
            pers.get("linkedin"),
            pers.get("github"),
            contact.get("linkedin"),
            contact.get("github"),
        )
    if links:
        pers["portfolio"] = links
    for key in ("linkedin", "github"):
        if parsed[key]:
            pers[key] = parsed[key]
    data["personal"] = pers
    return data


def build_contact_line(personal: dict | None) -> str:
    """Одна строка под именем: город | телефоны | email (без изменения HTML-шаблона)."""
    pers = personal if isinstance(personal, dict) else {}
    parts: list[str] = []
    location = _sanitize_contact_location(str(pers.get("location") or pers.get("city") or ""))
    phone = str(pers.get("phone") or "").strip()
    email = str(pers.get("email") or "").strip()
    if location:
        parts.append(location)
    if phone:
        parts.append(phone)
    if email and email.lower() not in phone.lower():
        parts.append(email)
    return " | ".join(parts)


def _education_line_is_relevant(line: str) -> bool:
    text = str(line or "").strip()
    if not text or len(text) > 220:
        return False
    if _parse_job_header_line(text) or _parse_dot_format_job_line(text) or _parse_paren_company_job_line(text):
        return False
    if _looks_like_course_line(text) or _looks_like_language_line(text):
        return False
    if _ROLE_LINE_HINT.search(text) and not _looks_like_education_line(text):
        return False
    if re.match(r"^[A-Za-z0-9 .'-]+\s+(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+\d{4}\b", text, re.I):
        return False
    low = text.lower()
    if "coursework" in low or "study abroad" in low or low.startswith(("honors", "gpa")):
        return True
    if text.startswith(("●", "•", "-", "▪", "◦")):
        return True
    if _looks_like_education_line(text):
        return True
    if re.match(rf"^{_MONTH_NAME}\s+\d{{4}}\s*$", text, re.I):
        return True
    if re.match(r"^[A-Z][a-zA-Z .'-]+,\s*[A-Z]{2}\s*$", text):
        return True
    return False


def _is_academic_education_item(item: dict) -> bool:
    inst = str(item.get("institution") or "").strip()
    degree = str(item.get("degree") or "").strip()
    details = str(item.get("details") or "").strip()
    blob = f"{inst} {degree} {details}".lower()
    if not inst and not degree:
        return False
    if _looks_like_course_line(inst) or _looks_like_course_line(degree) or _looks_like_course_line(details):
        return False
    if any(tok in blob for tok in ("udemy", "bootcamp", "coursera", "itea", "certification")):
        return False
    if any(
        tok in blob
        for tok in (
            "university",
            "college",
            "institute",
            "school of",
            "academy",
            "bachelor",
            "master",
            "phd",
            "diploma",
        )
    ):
        return True
    if inst and _looks_like_education_line(inst):
        return True
    return False


def _split_education_blob(text: str) -> tuple[str, str, str, str, list[str]]:
    """Разбирает многострочный education_text / institution blob на поля Hursh."""
    institution = ""
    degree = ""
    location = ""
    grad = ""
    bullets: list[str] = []
    for raw in _split_lines(text):
        line = str(raw or "").strip().lstrip("-•●▪◦ ")
        if not line:
            continue
        if _parse_job_header_line(line) or _parse_dot_format_job_line(line) or _parse_paren_company_job_line(line):
            continue
        if _ROLE_LINE_HINT.search(line) and not _looks_like_education_line(line):
            continue
        if _looks_like_course_line(line):
            continue
        low = line.lower()
        if "coursework" in low or "study abroad" in low or low.startswith(("honors", "gpa")):
            bullets.append(line)
            continue
        if re.match(r"^[A-Z][a-zA-Z .'-]+,\s*[A-Z]{2}\s*$", line):
            location = line
            continue
        if re.match(rf"^{_MONTH_NAME}\s+\d{{4}}\s*$", line, re.I):
            grad = line
            continue
        if any(tok in low for tok in ("bachelor", "master", "phd", "diploma", "degree in", "degree of")):
            if not degree:
                degree = line
            continue
        if _looks_like_education_line(line) or "university" in low or "college" in low:
            if not institution:
                institution = line
            elif not degree and any(tok in low for tok in ("bachelor", "master", "degree")):
                degree = line
            continue
    return institution, degree, location, grad, bullets


def _parse_education_chat_text(text: str) -> list[dict]:
    institution, degree, location, grad, bullets = _split_education_blob(text)
    if not (institution or degree):
        return []
    return [
        {
            "institution": institution,
            "degree": degree,
            "location": location,
            "graduation_date": grad,
            "details": "\n".join(bullets),
            "bullets": bullets,
        }
    ]


def _education_entries_from_chat_or_structured(education_text: str, education: object) -> list[dict]:
    if education_text.strip():
        parsed = _parse_education_chat_text(education_text)
        if parsed:
            return parsed
    if isinstance(education, list):
        out: list[dict] = []
        for item in education:
            if isinstance(item, dict) and _is_academic_education_item(item):
                inst = str(item.get("institution") or "").strip()
                degree = str(item.get("degree") or "").strip()
                if inst and "\n" in inst:
                    split_inst, split_deg, split_loc, split_grad, split_bullets = _split_education_blob(inst)
                    inst = split_inst or inst.splitlines()[0].strip()
                    degree = degree or split_deg
                    location = str(item.get("location") or "").strip() or split_loc
                    grad = str(item.get("graduation_date") or item.get("dates") or "").strip() or split_grad
                    bullets = split_bullets
                else:
                    location = str(item.get("location") or "").strip()
                    grad = str(item.get("graduation_date") or item.get("dates") or "").strip()
                    bullets = []
                    details = str(item.get("details") or "").strip()
                    if details:
                        bullets = [ln.lstrip("-•● ") for ln in details.splitlines() if ln.strip()]
                out.append(
                    {
                        "institution": inst,
                        "degree": degree,
                        "location": location,
                        "graduation_date": grad,
                        "details": "\n".join(bullets),
                        "bullets": bullets,
                    }
                )
        return out
    return []


def _extract_education_block(sections: dict[str, list[str]], full_text: str) -> str:
    lines: list[str] = []
    for raw in sections.get("EDUCATION") or []:
        line = raw.strip()
        if line and _education_line_is_relevant(line):
            lines.append(re.sub(r"^[\-•●▪◦\u200b\s]+", "", line).strip())

    if not lines:
        for raw in _split_lines(full_text):
            line = raw.strip()
            if line and _education_line_is_relevant(line):
                lines.append(re.sub(r"^[\-•●▪◦\u200b\s]+", "", line).strip())
    return "\n".join(_dedupe_lines(lines))


def _extract_interests_block(sections: dict[str, list[str]]) -> str:
    lines = [l.strip() for l in sections.get("INTERESTS") or [] if l.strip()]
    if not lines:
        return ""
    if len(lines) == 1 and ("·" in lines[0] or "•" in lines[0]):
        parts = [p.strip() for p in re.split(r"[·•]", lines[0]) if p.strip()]
        return _lines_to_bullet_block(parts)
    return _lines_to_bullet_block(lines)


def _looks_like_project_context(content: str) -> bool:
    text = str(content or "").strip()
    if not text or len(text) > 48:
        return False
    if _paren_content_looks_like_dates(text):
        return False
    low = text.lower()
    if low.startswith(("both ", "either ", "e.g.", "i.e.")):
        return False
    if "." in text or "hackathon" in low:
        return True
    return len(text.split()) <= 4


def _parse_project_header_line(line: str) -> dict | None:
    """«Mobile Utility App (eventually.im)» или «Web App (Bet.Net) May 2020 – October 2020»."""
    text = str(line or "").strip()
    if not text or _looks_like_contact_line(text):
        return None
    if _parse_paren_company_job_line(text):
        return None

    match = re.match(r"^(?P<title>.+?)\s*\((?P<context>[^()]+)\)\s*(?P<tail>.*)$", text)
    if match:
        context = match.group("context").strip()
        if _paren_content_looks_like_dates(context) or not _looks_like_project_context(context):
            return None
        title = re.sub(r"\s+", " ", match.group("title").strip())
        tail = match.group("tail").strip()
        dates = ""
        if tail and (_is_dates_only_line(tail) or _DATE_TAIL_RE.search(tail)):
            dates = _normalize_dates_fragment(tail)
        return {"title": title, "context": context, "dates": dates, "highlights": []}

    if _DATE_TAIL_RE.search(text):
        dm = _DATE_TAIL_RE.search(text)
        if dm:
            title = text[: dm.start()].strip().rstrip(".")
            if title and len(title) > 3:
                return {
                    "title": title,
                    "context": "",
                    "dates": _normalize_dates_fragment(dm.group("dates")),
                    "highlights": [],
                }
    return None


def _is_project_title_candidate(line: str) -> bool:
    if _parse_project_header_line(line):
        return True
    text = str(line or "").strip()
    if not text or len(text) > 140:
        return False
    if _is_dates_only_line(text) or _is_standalone_bullet_marker(text):
        return False
    if _looks_like_duty_line(text) or _parse_job_header_line(text):
        return False
    low = text.lower()
    markers = (" app", "hackathon", "project", "platform", "modeling", "utility", "web app", "pwa")
    return any(m in low for m in markers) or ("(" in text and ")" in text)


def _append_project_bullet(current: dict, line: str, *, force: bool = False) -> None:
    highlights = current.setdefault("highlights", [])
    bullet = re.sub(r"^[\-•●▪◦\u200b\s]+", "", line).rstrip(";").strip()
    if not bullet:
        return
    if highlights and _is_bullet_continuation_line(bullet, highlights[-1]):
        highlights[-1] = f"{highlights[-1]} {bullet}".strip()
        return
    if force or line.startswith(("-", "•", "●", "▪", "◦")) or _looks_like_duty_line(line):
        highlights.append(bullet)


def _parse_projects_from_lines(lines: list[str]) -> list[dict]:
    projects: list[dict] = []
    current: dict | None = None
    awaiting_bullet = False
    idx = 0
    while idx < len(lines):
        line = str(lines[idx] or "").strip()
        idx += 1
        if not line:
            continue

        if _is_standalone_bullet_marker(line):
            awaiting_bullet = True
            continue

        header = _parse_project_header_line(line)
        if header and not str(header.get("dates") or "").strip() and idx < len(lines):
            next_line = str(lines[idx] or "").strip()
            if _is_dates_only_line(next_line):
                header["dates"] = _normalize_dates_fragment(next_line)
                idx += 1

        if header and str(header.get("title") or "").strip():
            current = {**header, "highlights": []}
            projects.append(current)
            awaiting_bullet = False
            continue

        if _is_dates_only_line(line):
            if current is not None and not str(current.get("dates") or "").strip():
                current["dates"] = _normalize_dates_fragment(line)
            continue

        if current is None and _is_project_title_candidate(line):
            current = {"title": line, "context": "", "dates": "", "highlights": []}
            projects.append(current)
            awaiting_bullet = False
            continue

        if _is_project_title_candidate(line) and current is not None and (current.get("highlights") or awaiting_bullet):
            _append_project_bullet(current, line, force=awaiting_bullet or bool(current.get("highlights")))
            awaiting_bullet = False
            continue

        if current is None:
            continue

        if awaiting_bullet:
            _append_project_bullet(current, line, force=True)
            awaiting_bullet = False
            continue

        if line.startswith(("-", "•", "●", "▪", "◦")) or _looks_like_duty_line(line):
            _append_project_bullet(current, line)
            continue

        highlights = current.get("highlights") or []
        if highlights and _is_bullet_continuation_line(line, highlights[-1]):
            _append_project_bullet(current, line, force=True)

    for project in projects:
        merged = _merge_wrapped_highlights([str(x).strip() for x in project.get("highlights") or [] if str(x).strip()])
        project["highlights"] = merged
        project["description"] = "\n".join(merged)
    return projects


def _format_project_heading(project: dict) -> str:
    title = str(project.get("title") or "").strip()
    context = str(project.get("context") or "").strip()
    dates = str(project.get("dates") or "").strip()
    head = f"{title} ({context})" if context else title
    if dates:
        head = f"{head}, {dates}"
    return head


def _projects_to_chat_text(projects: list[dict]) -> str:
    blocks: list[str] = []
    for project in projects:
        heading = _format_project_heading(project)
        desc = str(project.get("description") or "").strip()
        if desc:
            blocks.append(f"- {heading}\n  {desc}")
        else:
            blocks.append(f"- {heading}")
    return "\n\n".join(blocks)


def _extract_projects_from_plain_text(text: str) -> str:
    sections = _extract_named_sections(text)
    lines = list(sections.get("PROJECTS") or [])
    if not lines:
        in_projects = False
        for raw in _split_lines(text):
            line = raw.strip()
            header = _match_section_header(line)
            if header == "PROJECTS":
                in_projects = True
                continue
            if header and in_projects:
                break
            if in_projects and line:
                lines.append(line)
    projects = _parse_projects_from_lines(lines)
    return _projects_to_chat_text(projects)


def _parse_projects_chat_text(text: str) -> list[dict]:
    items: list[dict] = []
    for block in re.split(r"\n\s*\n", str(text or "").strip()):
        block = block.strip()
        if not block.startswith("-"):
            continue
        lines = [ln.rstrip() for ln in block.splitlines() if ln.strip()]
        heading = lines[0].lstrip("- ").strip()
        desc = " ".join(ln.strip() for ln in lines[1:] if ln.strip()).strip()
        items.append({"title": heading, "context": "", "dates": "", "description": desc, "highlights": [desc] if desc else []})
    return items


def _prefer_plain_supplementary(current: str, plain: str) -> str:
    cur = str(current or "").strip()
    pln = str(plain or "").strip()
    if not pln:
        return cur
    if not cur:
        return pln
    if len(pln) > len(cur) + 8:
        return pln
    return cur


def _parse_experience_block(text: str) -> list[dict]:
    entries: list[dict] = []
    current: dict | None = None
    for raw in _split_lines(text):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("-") or line.startswith("•"):
            bullet = line.lstrip("-• ").strip()
            if current is not None and bullet:
                hl = current.setdefault("highlights", [])
                if isinstance(hl, list):
                    hl.append(bullet)
            continue

        header = _parse_experience_header_line(line)
        if header is not None:
            current = header
            entries.append(current)
            continue

        if current is not None:
            current["summary"] = (current.get("summary") or "") + ("\n" if current.get("summary") else "") + line
        else:
            current = {"title": line, "company": "", "dates": "", "summary": "", "highlights": []}
            entries.append(current)
    return entries


def _first_nonempty_str(*values: object) -> str:
    for value in values:
        text = str(value or "").strip()
        if text and text.lower() not in {"null", "none", "n/a", "-"}:
            return text
    return ""


def _split_title_and_company(text: str) -> tuple[str, str]:
    """Из одной строки «Data Engineer at HRForecast» выделяет должность и компанию."""
    raw = str(text or "").strip()
    if not raw:
        return "", ""

    match = re.search(r"\s+at\s+", raw, flags=re.I)
    if match:
        return raw[: match.start()].strip(), raw[match.end() :].strip()

    for sep in (" @ ", " / "):
        if sep in raw:
            left, right = raw.split(sep, 1)
            if left.strip() and right.strip():
                return left.strip(), right.strip()

    return raw, ""


def _job_narrative_from_parts(*parts: object) -> str:
    lines: list[str] = []
    seen: set[str] = set()
    for part in parts:
        if isinstance(part, list):
            for item in part:
                text = str(item).strip().lstrip("-• ")
                if text and text not in seen:
                    seen.add(text)
                    lines.append(text)
        else:
            text = str(part or "").strip()
            if not text:
                continue
            for chunk in re.split(r"\n+", text):
                line = chunk.strip().lstrip("-• ")
                if line and line not in seen:
                    seen.add(line)
                    lines.append(line)
    return "\n".join(lines)


def _normalize_llm_job_entry(item: object) -> dict:
    """Приводит запись опыта из LLM/PDF к единому виду (company, position, dates, narrative)."""
    if isinstance(item, str):
        line = item.strip()
        header = _parse_experience_header_line(line)
        if header:
            return _normalize_llm_job_entry(header)
        return {"company": "", "position": line, "title": line, "dates": "", "highlights": [], "technologies": []}

    if not isinstance(item, dict):
        return {}

    company = _first_nonempty_str(
        item.get("company"),
        item.get("employer"),
        item.get("organization"),
        item.get("company_name"),
        item.get("companyName"),
        item.get("employer_name"),
        item.get("workplace"),
        item.get("firm"),
        item.get("org"),
        item.get("name"),
    )
    position = _first_nonempty_str(
        item.get("position"),
        item.get("title"),
        item.get("role"),
        item.get("job_title"),
        item.get("jobTitle"),
        item.get("designation"),
        item.get("position_title"),
    )

    dates = _first_nonempty_str(
        item.get("dates"),
        item.get("duration"),
        item.get("period"),
        item.get("tenure"),
        item.get("date_range"),
        item.get("dateRange"),
        item.get("timeframe"),
    )
    start = _first_nonempty_str(item.get("start_date"), item.get("startDate"), item.get("start"), item.get("from"))
    end = _first_nonempty_str(item.get("end_date"), item.get("endDate"), item.get("end"), item.get("to"), item.get("until"))
    if str(item.get("current") or "").strip().lower() in {"true", "yes", "1", "present", "current"}:
        end = end or "Present"
    if not dates:
        dates = " — ".join(x for x in (start, end) if x)

    header = _first_nonempty_str(item.get("header"), item.get("line"), item.get("heading"))
    if header:
        parsed_header = _parse_experience_header_line(header)
        if parsed_header:
            if not position:
                position = str(parsed_header.get("title") or "").strip()
            if not company:
                company = str(parsed_header.get("company") or "").strip()
            if not dates:
                dates = str(parsed_header.get("dates") or "").strip()

    if not company and position:
        split_title, split_company = _split_title_and_company(position)
        if split_company:
            position = split_title
            company = split_company

    position, company = _split_merged_position_company(position, company)
    company = _normalize_company_label(company)
    position = _humanize_camel_case(position)

    highlights = item.get("highlights") or item.get("bullets") or item.get("achievements") or []
    if not isinstance(highlights, list):
        highlights = [highlights] if highlights else []
    highlights = _merge_wrapped_highlights([str(x).strip() for x in highlights if str(x).strip()])

    responsibilities = (
        item.get("responsibilities")
        or item.get("responsibility")
        or item.get("duties")
        or item.get("tasks")
        or item.get("description")
        or item.get("job_description")
        or item.get("summary_text")
        or ""
    )

    summary = _first_nonempty_str(item.get("summary"), item.get("overview"), item.get("details"))
    narrative = _job_narrative_from_parts(
        item.get("raw_description"),
        responsibilities,
        summary,
        highlights if not responsibilities and not summary else None,
    )

    technologies = item.get("technologies") or item.get("tech_stack") or item.get("tools") or item.get("skills") or []
    if isinstance(technologies, str):
        technologies = _parse_chips(technologies)

    resp_list: list[str] = []
    if isinstance(responsibilities, list):
        resp_list = [str(x).strip() for x in responsibilities if str(x).strip()]
    elif str(responsibilities).strip():
        resp_list = _parse_bullet_lines(str(responsibilities)) or [str(responsibilities).strip()]

    return {
        "company": company,
        "position": position,
        "title": position,
        "dates": dates,
        "start_date": start,
        "end_date": end,
        "highlights": highlights,
        "technologies": technologies if isinstance(technologies, list) else [],
        "responsibilities": resp_list or responsibilities,
        "responsibilities_narrative": narrative,
        "raw_description": narrative,
        "summary": summary or narrative,
        "project": item.get("project") if isinstance(item.get("project"), dict) else {},
        "improvements": item.get("improvements") or item.get("achievements"),
    }


def _humanize_camel_case(text: str) -> str:
    """DataEngineer → Data Engineer."""
    return re.sub(r"([a-z])([A-Z])", r"\1 \2", str(text or "").strip()).strip()


def _normalize_company_label(text: str) -> str:
    raw = _humanize_camel_case(text).replace('"', "").strip()
    key = raw.lower().replace("-", "").replace(" ", "")
    if key == "selfemployed":
        return "Self-employed"
    if key in {"hrforecast", "hrforcast"}:
        return "HR Forecast"
    if key == "auchanretail":
        return "Auchan Retail"
    if key == "trinetix":
        return "Trinetix"
    if "energozbyt" in key or "ukrainianrailways" in key.replace(" ", ""):
        return "Energozbyt JSC Ukrainian railways"
    if "krasnolimanskaya" in key or key.startswith("coalcompany"):
        return 'Coal company "Krasnolimanskaya"'
    return raw


def _split_merged_position_company(position: str, company: str) -> tuple[str, str]:
    """Разбирает склеенные LLM/PDF значения вроде «DataEngineer.Selfemployed»."""
    pos = str(position or "").strip()
    comp = str(company or "").strip()

    if "|" in pos:
        parts = [p.strip() for p in pos.split("|") if p.strip()]
        if len(parts) >= 2:
            pos = parts[0]
            if not comp:
                comp = parts[1]

    if "." in pos:
        left, right = pos.split(".", 1)
        if left.strip() and right.strip() and not re.search(r"\d{4}", right):
            pos = _humanize_camel_case(left.strip())
            right_company = _normalize_company_label(right.strip())
            if not comp:
                comp = right_company
            elif comp.lower().replace("-", "").replace(" ", "") != right_company.lower().replace("-", "").replace(" ", ""):
                # LLM иногда кладёт чужую company (HRForecast) при склеенном title (DataEngineer.Selfemployed)
                comp = right_company

    pos = _humanize_camel_case(pos)
    comp = _normalize_company_label(comp)
    return pos, comp


def _looks_like_broken_experience_entry(item: object) -> bool:
    if not isinstance(item, dict):
        return True
    position = str(item.get("position") or item.get("title") or "").strip()
    company = str(item.get("company") or "").strip()
    dates = str(item.get("dates") or "").strip()
    body = json.dumps(item.get("highlights") or item.get("description") or "", ensure_ascii=False).lower()

    if not company and not position:
        return True
    if "." in position and not dates and "|" not in position:
        return True
    if company.lower().replace(" ", "") in {"hrforecast", "hrforcast"} and "step functions" in body:
        return True
    if company.lower().replace(" ", "") in {"hrforecast", "hrforcast"} and "glue jobs" in body:
        return True
    return False


def _collect_experience_array_items(structured: dict) -> list[object]:
    items: list[object] = []
    seen_signatures: set[str] = set()

    def _add(raw_items: list[object]) -> None:
        for raw in raw_items:
            if isinstance(raw, dict):
                sig = json.dumps(raw, sort_keys=True, ensure_ascii=False)[:240]
            else:
                sig = str(raw).strip()[:240]
            if not sig or sig in seen_signatures:
                continue
            seen_signatures.add(sig)
            items.append(raw)

    for key in (
        "experience",
        "experiences",
        "work_experience",
        "workExperience",
        "employment",
        "employment_history",
        "professional_experience",
        "career_history",
        "work_history",
        "jobs",
        "positions",
    ):
        raw = structured.get(key)
        if isinstance(raw, list) and raw:
            _add(raw)
        elif isinstance(raw, dict):
            for subkey in ("items", "positions", "entries", "jobs", "history", "experiences"):
                sub = raw.get(subkey)
                if isinstance(sub, list) and sub:
                    _add(sub)
        elif isinstance(raw, str) and raw.strip():
            _add(_parse_experience_block(raw))
    return items


def _experience_text_block(structured: dict) -> str:
    return str(structured.get("experience_text") or structured.get("work_experience_text") or "").strip()


def _is_experience_array_reliable(items: list[object]) -> bool:
    if not items:
        return False
    broken = sum(1 for item in items if _looks_like_broken_experience_entry(item))
    return broken == 0


def _job_has_chat_enrichments(job: dict) -> bool:
    for field in ("improvements", "achievements"):
        val = job.get(field)
        if isinstance(val, list) and any(str(x).strip() for x in val):
            return True
        if isinstance(val, str) and str(val).strip():
            return True
    return False


def _merge_chat_enrichments_from_array(target_jobs: list[object], array_items: list[object]) -> list[dict]:
    """Сохраняет impact/achievements из structured experience при сборке из PDF plain text."""
    if not target_jobs or not array_items:
        return [_normalize_llm_job_entry(item) for item in target_jobs if isinstance(item, dict)]

    donors = [_normalize_llm_job_entry(item) for item in array_items if isinstance(item, dict)]
    if not any(_job_has_chat_enrichments(d) for d in donors):
        return [_normalize_llm_job_entry(item) for item in target_jobs if isinstance(item, dict)]

    out: list[dict] = []
    used_donors: set[int] = set()

    for idx, raw in enumerate(target_jobs):
        job = _normalize_llm_job_entry(raw) if isinstance(raw, dict) else {}
        donor: dict | None = None

        company = str(job.get("company") or "").strip()
        for d_idx, candidate in enumerate(donors):
            if d_idx in used_donors:
                continue
            if _companies_loosely_match(company, str(candidate.get("company") or "")):
                donor = candidate
                used_donors.add(d_idx)
                break

        if donor is None and idx < len(donors) and idx not in used_donors:
            donor = donors[idx]
            used_donors.add(idx)

        if donor and _job_has_chat_enrichments(donor):
            for field in ("improvements", "achievements"):
                if donor.get(field):
                    job[field] = donor[field]
            donor_highlights = donor.get("highlights")
            if isinstance(donor_highlights, list) and any(str(x).strip() for x in donor_highlights):
                job["highlights"] = [str(x).strip() for x in donor_highlights if str(x).strip()]
                if donor.get("responsibilities"):
                    job["responsibilities"] = donor["responsibilities"]
                elif job.get("highlights"):
                    job["responsibilities"] = list(job["highlights"])
            elif not job.get("responsibilities") and donor.get("responsibilities"):
                job["responsibilities"] = donor["responsibilities"]
                job["highlights"] = _job_highlights(job)
            elif not job.get("highlights"):
                job["highlights"] = _job_highlights(job)

        out.append(job)

    return out


def _collect_raw_experience_items(structured: dict) -> list[object]:
    """Собирает записи опыта из structured JSON и plain text PDF."""
    array_items = _collect_experience_array_items(structured)
    # Only tailored ATS saves opt in — chat/PDF import must still merge plain text + LLM array.
    if structured.get("_keep_stored_experience_bullets") and array_items:
        return array_items

    full_text = str(structured.get("_resume_plain_text") or "").strip()
    exp_text = _experience_text_block(structured)

    plain_jobs: list[dict] = []
    if full_text:
        plain_jobs = _extract_jobs_from_resume_plain_text(full_text)
    if not plain_jobs and exp_text:
        plain_jobs = _extract_jobs_from_resume_plain_text(exp_text)

    if plain_jobs:
        if array_items:
            return _merge_chat_enrichments_from_array(plain_jobs, array_items)
        return plain_jobs

    if array_items:
        return array_items

    source_text = exp_text or full_text
    if source_text:
        plain_jobs = _extract_jobs_from_resume_plain_text(source_text)
        if plain_jobs:
            if array_items:
                return _merge_chat_enrichments_from_array(plain_jobs, array_items)
            return plain_jobs
        return _parse_experience_block(source_text)

    return array_items


def _normalize_company_token(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _companies_loosely_match(left: str, right: str) -> bool:
    a = _normalize_company_token(left)
    b = _normalize_company_token(right)
    if not a or not b:
        return False
    return a in b or b in a


def _fill_missing_descriptions_from_plain(full_text: str, jobs: list[dict]) -> list[dict]:
    """Дополняет пустые description из plain text PDF (если LLM их пропустил)."""
    plain_jobs = [_normalize_llm_job_entry(item) for item in _extract_jobs_from_resume_plain_text(full_text)]
    if not plain_jobs:
        return jobs

    filled: list[dict] = []
    for idx, job in enumerate(jobs):
        row = dict(job)
        if _job_description_for_chat(row):
            filled.append(row)
            continue

        donor: dict | None = None
        if idx < len(plain_jobs) and _job_description_for_chat(plain_jobs[idx]):
            donor = plain_jobs[idx]
        else:
            company = str(row.get("company") or "").strip()
            for plain in plain_jobs:
                if _companies_loosely_match(company, str(plain.get("company") or "")):
                    if _job_description_for_chat(plain):
                        donor = plain
                        break

        if donor:
            for field in ("raw_description", "responsibilities_narrative", "summary", "description"):
                if not str(row.get(field) or "").strip() and str(donor.get(field) or "").strip():
                    row[field] = donor[field]
            if not row.get("highlights") and donor.get("highlights"):
                row["highlights"] = donor["highlights"]
            if not row.get("responsibilities") and donor.get("responsibilities"):
                row["responsibilities"] = donor["responsibilities"]

        filled.append(row)
    return filled


def _experience_entries_from_structured(structured: dict) -> list[dict]:
    """Извлекает список мест работы из structured JSON (разные ключи и форматы LLM)."""
    jobs: list[dict] = []
    for item in _collect_raw_experience_items(structured):
        job = _normalize_llm_job_entry(item)
        has_header = any(
            str(job.get(field) or "").strip()
            for field in ("company", "position", "title", "dates", "start_date", "end_date")
        )
        has_body = bool(str(job.get("raw_description") or job.get("responsibilities_narrative") or "").strip())
        has_body = has_body or bool(job.get("highlights")) or bool(job.get("responsibilities"))
        if has_header or has_body:
            jobs.append(job)

    full_text = str(structured.get("_resume_plain_text") or "").strip()
    if full_text and jobs:
        jobs = _fill_missing_descriptions_from_plain(full_text, jobs)
    return _dedupe_experience_jobs(jobs)


def _job_description_for_chat(job: dict) -> str:
    """Текст «чем занимались» для поля description в чате."""
    for field in ("raw_description", "responsibilities_narrative", "summary"):
        text = str(job.get(field) or "").strip()
        if text:
            return text

    project = job.get("project") if isinstance(job.get("project"), dict) else {}
    project_text = str(project.get("description") or "").strip()
    if project_text:
        return project_text

    responsibilities = job.get("responsibilities")
    if isinstance(responsibilities, list) and responsibilities:
        return "\n".join(str(x).strip() for x in responsibilities if str(x).strip())
    if isinstance(responsibilities, str) and responsibilities.strip():
        return responsibilities.strip()

    highlights = job.get("highlights")
    if isinstance(highlights, list) and highlights:
        return "\n".join(str(x).strip() for x in highlights if str(x).strip())

    return ""


def _parse_courses(text: str) -> list[str]:
    items: list[str] = []
    for raw in _split_lines(text):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("-") or line.startswith("•"):
            items.append(line.lstrip("-• ").strip())
        else:
            items.append(line)
    return items


def _normalize_languages_block(text: str) -> str:
    lines: list[str] = []
    for raw in _split_lines(text):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("-") or line.startswith("•"):
            lines.append(line if line.startswith("-") else f"- {line.lstrip('• ')}")
        else:
            lines.append(f"- {line}")
    return "\n".join(lines)


def _parse_bullet_lines(text: str) -> list[str]:
    items: list[str] = []
    for raw in _split_lines(text):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("-") or line.startswith("•"):
            line = line.lstrip("-• ").strip()
        if line:
            items.append(line)
    return items


def _collect_job_indices(answers: dict[str, str]) -> list[int]:
    indices: set[int] = set()
    for key in answers:
        match = re.match(r"job_(\d+)_", key)
        if match:
            indices.add(int(match.group(1)))
    return sorted(idx for idx in indices if str(answers.get(f"job_{idx}_company") or "").strip())


def _job_from_answers(answers: dict[str, str], index: int) -> dict:
    prefix = f"job_{index}_"

    def _field(name: str) -> str:
        return str(answers.get(f"{prefix}{name}") or "").strip()

    technologies = _parse_chips(_field("technologies"))
    role_and_dates = _field("roleAndDates")
    position = _field("position")
    dates_raw = _field("dates")

    if role_and_dates:
        if "," in role_and_dates:
            pos_part, dates_part = role_and_dates.split(",", 1)
            if not position:
                position = pos_part.strip()
            if not dates_raw:
                dates_raw = dates_part.strip()
        else:
            if not position:
                position = role_and_dates
            if not dates_raw:
                dates_raw = role_and_dates

    start_date, end_date = _split_dates(dates_raw)
    if not dates_raw:
        start_date = _field("startDate")
        end_date = _field("endDate")
        dates_raw = " — ".join(x for x in (start_date, end_date) if x)

    description = _field("description") or _field("raw_description")
    responsibilities_json: list[str] = []
    raw_json = answers.get(f"{prefix}responsibilities_json")
    if raw_json:
        try:
            parsed = json.loads(raw_json)
            if isinstance(parsed, list):
                responsibilities_json = [str(x).strip() for x in parsed if str(x).strip()]
        except (json.JSONDecodeError, TypeError):
            pass

    responsibilities_raw = _field("responsibilities")
    if not responsibilities_raw and responsibilities_json:
        responsibilities_raw = "\n".join(responsibilities_json)
    if not responsibilities_raw and description:
        responsibilities_raw = description

    result_raw = _field("result")
    improvements_raw = result_raw or _field("improvements")
    no_measurable_result = improvements_raw in {
        IMPROVEMENTS_NO_MEASURABLE_ANSWER,
        RESULT_NO_MEASURABLE_ANSWER_LEGACY,
    }
    if no_measurable_result:
        improvements_raw = ""
    if not improvements_raw:
        improvements_raw = _field("achievements") or _field("personalAchievement")

    if not responsibilities_raw:
        responsibilities_raw = _field("projectDescription")

    return {
        "company": _field("company"),
        "position": position,
        "title": position,
        "dates": dates_raw,
        "start_date": start_date,
        "end_date": end_date,
        "technologies": technologies,
        "raw_description": description or responsibilities_raw,
        "responsibilities": responsibilities_json or _parse_bullet_lines(responsibilities_raw) or ([responsibilities_raw] if responsibilities_raw else []),
        "responsibilities_narrative": description or responsibilities_raw,
        "improvements": _parse_bullet_lines(improvements_raw) or ([improvements_raw] if improvements_raw else []),
        "achievements": _parse_bullet_lines(improvements_raw),
        "no_measurable_result": no_measurable_result,
        "summary": description or responsibilities_raw,
        "project": {"name": "", "description": description or responsibilities_raw},
        "highlights": [],
        # legacy-поля для обратной совместимости
        "industry": _field("industry"),
        "team": _field("teamSize"),
        "role": _field("candidateRole") or position,
        "developed_features": _parse_bullet_lines(_field("developedFeatures")),
        "challenges": _parse_bullet_lines(_field("challenges")),
        "metrics": _parse_bullet_lines(_field("metrics")),
        "business_impact": _parse_bullet_lines(_field("businessImpact")),
        "personal_achievement": _field("personalAchievement"),
    }


def _job_highlights(job: dict) -> list[str]:
    highlights: list[str] = []
    for field in ("improvements", "achievements", "responsibilities"):
        for item in job.get(field) or []:
            text = str(item).strip()
            if text and text not in highlights:
                highlights.append(text)
    if highlights:
        return highlights[:8]
    for field in ("highlights", "bullets"):
        for item in job.get(field) or []:
            text = str(item).strip()
            if text and text not in highlights:
                highlights.append(text)
    if highlights:
        return highlights[:8]
    narrative = str(job.get("responsibilities_narrative") or job.get("summary") or "").strip()
    if narrative and narrative not in highlights and len(narrative) < 500:
        if "\n" not in narrative:
            highlights.insert(0, narrative)
    personal = str(job.get("personal_achievement") or "").strip()
    if personal and personal not in highlights:
        highlights.insert(0, personal)
    return highlights[:8]


def _experience_text_from_jobs(jobs: list[dict]) -> str:
    blocks: list[str] = []
    for job in jobs:
        header = " | ".join(
            x
            for x in (
                str(job.get("position") or job.get("title") or "").strip(),
                str(job.get("company") or "").strip(),
                str(job.get("dates") or "").strip(),
            )
            if x
        )
        if header:
            blocks.append(header)
        summary_parts = [
            str(job.get("project", {}).get("description") or "").strip(),
            str(job.get("industry") or "").strip(),
        ]
        summary = " — ".join(x for x in summary_parts if x)
        if summary:
            blocks.append(summary)
        for bullet in _job_highlights(job):
            blocks.append(f"- {bullet}")
        blocks.append("")
    return "\n".join(blocks).strip()


def _build_summary(answers: dict[str, str], skills: list[str]) -> str:
    position = str(answers.get("desiredPosition") or answers.get("desiredPositions") or "").strip()
    tech_chunk = ", ".join(skills[:8])
    parts: list[str] = []
    if position:
        lead = position[0].upper() + position[1:] if len(position) > 1 else position
        parts.append(lead)
    if tech_chunk:
        parts.append(f"Tech stack: {tech_chunk}")
    job_count = len(_collect_job_indices(answers))
    if job_count:
        parts.append(f"{job_count}+ relevant role(s) in recent experience")
    return ". ".join(p.rstrip(".") for p in parts if p).strip() + ("." if parts else "")


def _is_career_interview_answers(answers: dict[str, str]) -> bool:
    return bool(
        answers.get("name")
        or answers.get("headline")
        or answers.get("desiredPosition")
        or answers.get("desiredPositions")
        or answers.get("links")
        or answers.get("mainTechStack")
        or answers.get("strongTechnologies")
        or answers.get("experienceJobCount")
        or any(k.startswith("exp_") for k in answers)
        or any(k.startswith("job_") for k in answers)
    )


def _legacy_answers(answers: dict[str, str]) -> dict[str, str]:
    """Поддержка старых ключей чата."""
    out = dict(answers)
    if not out.get("desiredPosition"):
        out["desiredPosition"] = str(
            out.get("desiredPositions") or out.get("position") or out.get("objective") or out.get("about") or ""
        ).strip()
    if not out.get("mainTechStack"):
        out["mainTechStack"] = str(out.get("strongTechnologies") or out.get("skills") or "").strip()
    if not out.get("courses") and out.get("certificates"):
        out["courses"] = str(out.get("certificates") or "").strip()
    if not out.get("objective"):
        out["objective"] = str(out.get("desiredPosition") or "").strip()
    return out


def _split_dates(dates: str) -> tuple[str, str]:
    text = str(dates or "").strip()
    if not text:
        return "", ""
    for sep in (" — ", " – ", " - ", " to ", "–", "—"):
        if sep in text:
            start, end = text.split(sep, 1)
            return start.strip(), end.strip()
    return text, ""


def _language_lines(languages: object) -> str:
    if isinstance(languages, str):
        return _normalize_languages_block(languages)
    if not isinstance(languages, list):
        return ""
    lines: list[str] = []
    for item in languages:
        if isinstance(item, str):
            text = item.strip()
        elif isinstance(item, dict):
            text = str(item.get("language") or item.get("name") or "").strip()
            level = str(item.get("level") or "").strip()
            if level:
                text = f"{text} — {level}".strip(" —")
        else:
            text = str(item).strip()
        if text:
            lines.append(f"- {text.lstrip('-• ')}")
    return "\n".join(lines)


def _education_text_from_structured(education: object) -> str:
    if isinstance(education, str):
        return education.strip()
    if not isinstance(education, list):
        return ""
    for item in education:
        if not isinstance(item, dict) or not _is_academic_education_item(item):
            continue
        lines: list[str] = []
        inst = str(item.get("institution") or "").strip()
        degree = str(item.get("degree") or "").strip()
        date = str(item.get("graduation_date") or "").strip()
        details = str(item.get("details") or "").strip()
        if inst:
            lines.append(inst)
        if degree:
            lines.append(degree)
        if date:
            lines.append(date)
        if details:
            lines.append(details)
        return "\n".join(lines).strip()
    return ""


def _certificates_text_from_structured(certifications: object) -> str:
    if isinstance(certifications, str):
        return certifications.strip()
    if not isinstance(certifications, list):
        return ""
    lines: list[str] = []
    for item in certifications:
        if isinstance(item, str):
            text = item.strip()
        elif isinstance(item, dict):
            text = str(item.get("name") or item.get("title") or item.get("certification") or "").strip()
        else:
            text = str(item).strip()
        if text:
            lines.append(text if text.startswith("-") else f"- {text}")
    return "\n".join(lines)


def _split_location(location: str) -> tuple[str, str]:
    text = str(location or "").strip()
    if not text:
        return "", ""
    if "," in text:
        parts = [p.strip() for p in text.split(",") if p.strip()]
        if len(parts) >= 2:
            return parts[0], parts[-1]
    return text, ""


def _bullet_lines(items: object) -> str:
    if isinstance(items, str):
        return items.strip()
    if not isinstance(items, list):
        return ""
    lines: list[str] = []
    for item in items:
        text = str(item).strip()
        if text:
            lines.append(text if text.startswith("-") else f"- {text}")
    return "\n".join(lines)


def _tech_stack_from_structured(structured: dict) -> str:
    """Собирает основной стек из structured JSON (PDF/LLM) — несколько возможных форматов."""
    seen: set[str] = set()
    items: list[str] = []

    def _add(raw: object) -> None:
        if isinstance(raw, str):
            candidates = _parse_chips(raw)
        elif isinstance(raw, list):
            candidates = [_normalize_skill_item(x) for x in raw]
        elif isinstance(raw, dict):
            candidates = []
            for v in raw.values():
                if isinstance(v, list):
                    candidates.extend(_normalize_skill_item(x) for x in v)
                elif isinstance(v, str) and v.strip():
                    candidates.append(v.strip())
        else:
            candidates = []
        for name in candidates:
            text = str(name).strip()
            if not text or len(text) > 80:
                continue
            low = text.lower()
            if low in seen:
                continue
            seen.add(low)
            items.append(text)

    for key in (
        "main_tech_stack",
        "skills",
        "technical_skills",
        "tech_stack",
        "core_skills",
        "technologies",
    ):
        _add(structured.get(key))

    for text_key in ("skills_text", "skills_summary"):
        _add(str(structured.get(text_key) or "").strip())

    jobs = _experience_entries_from_structured(structured)
    if jobs:
        for job in jobs:
            _add(job.get("technologies"))
            for hl in job.get("highlights") or []:
                text = str(hl).strip()
                if not text:
                    continue
                for token in re.findall(
                    r"\b(?:Python|PySpark|SQL|AWS|Glue|Snowflake|Kafka|Spark|Java|Scala|"
                    r"Terraform|Docker|Kubernetes|Airflow|dbt|PostgreSQL|Redis|Athena)\b",
                    text,
                    flags=re.I,
                ):
                    _add(token)

    return ", ".join(items[:32])

