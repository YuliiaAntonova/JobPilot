"""Plain-text и structured JSON профиля резюме (формат resume.txt)."""

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


def structured_skills_list(data: dict | None) -> list[str]:
    """Skills from structured profile / LLM JSON (как в PostgreSQL), без education/experience."""
    if not isinstance(data, dict):
        return []

    seen: set[str] = set()
    out: list[str] = []

    def add(raw: object) -> None:
        if raw is None:
            return
        if isinstance(raw, list):
            for item in raw:
                add(item)
            return
        text = str(raw).strip()
        if not text or len(text) > 80:
            return
        key = text.casefold()
        if key in seen:
            return
        seen.add(key)
        out.append(text)

    skills_text = str(data.get("skills_text") or data.get("skills_summary") or "").strip()
    if skills_text:
        for chip in _split_skill_chips(skills_text):
            add(chip)

    for key in (
        "skills",
        "main_tech_stack",
        "technical_skills",
        "technicalSkills",
        "technologies",
        "tech_stack",
        "core_skills",
    ):
        raw = data.get(key)
        if isinstance(raw, list):
            for item in raw:
                add(item)
        elif isinstance(raw, str) and raw.strip():
            for chip in _split_skill_chips(raw):
                add(chip)

    return out


def skills_from_plain_resume_text(plain: str) -> list[str]:
    """Skill chips from plain resume lines (SKILLS section, Hands-on / Tools: rows)."""
    seen: set[str] = set()
    out: list[str] = []

    def add(raw: object) -> None:
        text = str(raw or "").strip()
        if not text or len(text) > 80:
            return
        key = text.casefold()
        if key in seen:
            return
        seen.add(key)
        out.append(text)

    text = (plain or "").strip()
    if not text:
        return out

    sections = _extract_named_sections(text)
    for line in sections.get("SKILLS") or []:
        labeled = _parse_labeled_skills_line(line)
        body = labeled[1] if labeled else line
        for chip in _split_skill_chips(body):
            add(chip)

    for raw in _split_lines(text):
        line = raw.strip()
        if not line or not _looks_like_skill_content_line(line):
            continue
        labeled = _parse_labeled_skills_line(line)
        body = labeled[1] if labeled else line
        for chip in _split_skill_chips(body):
            add(chip)

    return out


def _skills_only_from_parsed_plain(plain: str) -> str:
    """Fallback для PDF без заголовков: только skill-строки, без education/languages."""
    parts: list[str] = []
    plain_skills = _extract_skills_from_plain_text(plain)
    skills_body = str(plain_skills.get("skills") or plain_skills.get("mainTechStack") or "").strip()
    skill_lines: list[str] = []
    for raw in _split_lines(plain):
        line = raw.strip()
        if not line or _match_section_header(line):
            continue
        if _looks_like_skill_content_line(line):
            skill_lines.append(line)
    if skill_lines:
        scanned = "\n".join(_dedupe_lines(skill_lines))
        skills_body = "\n\n".join(x for x in (skills_body, scanned) if x).strip()
    if skills_body:
        parts.extend(["SKILLS", "", skills_body])
    return "\n".join(parts).strip()


def extract_skills_text_for_jobbert(
    resume_text: str,
    structured: dict | None = None,
) -> tuple[str, str]:
    """
    Text for JobBERT entity extraction: SKILLS only.

    Priority: structured JSON (DB / extract_resume_json) → SKILLS section → parsed plain skills.
    """
    structured_skills = structured_skills_list(structured)
    if structured_skills:
        body = ", ".join(structured_skills)
        return f"SKILLS\n\n{body}", "structured_profile"

    plain = (resume_text or "").strip()
    if plain:
        sections = _extract_named_sections(plain)
        skill_lines = list(sections.get("SKILLS") or [])
        if skill_lines:
            combined = "\n".join(["SKILLS", *skill_lines]).strip()
            if len(combined) >= 20:
                return combined, "skills_section"

        parsed = _skills_only_from_parsed_plain(plain)
        if len(parsed) >= 20:
            return parsed, "parsed_plain_skills"

    return plain, "full_resume"


def extract_skills_education_text(
    resume_text: str,
    structured: dict | None = None,
) -> tuple[str, str]:
    """Backward-compatible alias — JobBERT scoring uses structured skills only."""
    return extract_skills_text_for_jobbert(resume_text, structured)


def extract_skills_experience_text(
    resume_text: str,
    structured: dict | None = None,
) -> tuple[str, str]:
    """Backward-compatible alias."""
    return extract_skills_text_for_jobbert(resume_text, structured)


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


_SKILL_LABEL_PREFIXES = (
    "technical skills",
    "technologies",
    "tools",
    "domain expertise",
    "hands-on experience",
    "knowledge of",
    "experience with",
    "cloud & data",
    "databases & sql",
    "programming languages",
    "frameworks",
    "platforms",
)

_CATEGORIZED_SKILL_LINE_RE = re.compile(
    r"^(Hands-on experience|Knowledge of|Experience with|Tools:|Domain expertise:|Cloud & Data:|Databases & SQL:|SQL\s*\(|Git\s*\()",
    re.I,
)

_SKILL_ROW_BOUNDARY_RE = re.compile(
    r"(?="
    r"Hands-on experience\s|"
    r"Knowledge of\s|"
    r"Cloud\s*&\s*Data\s*:|"
    r"Databases\s*&\s*SQL\s*:|"
    r"Experience with\s|"
    r"Tools\s*:|"
    r"Domain expertise\s*:|"
    r"Git\s*\("
    r")",
    re.I,
)

_PERIOD_BEFORE_SKILL_LABEL_RE = re.compile(
    r"\.\s+(?="
    r"Knowledge of\s|"
    r"Experience with\s|"
    r"Tools\s*:|"
    r"Domain expertise\s*:|"
    r"Cloud\s*&\s*Data\s*:|"
    r"Databases\s*&\s*SQL\s*:|"
    r"SQL\s*\("
    r")",
    re.I,
)


def _split_skills_into_labeled_rows(text: str) -> list[str]:
    """One PDF paragraph or glued labels → separate skill rows for parsing."""
    raw = str(text or "").strip()
    if not raw:
        return []
    rows: list[str] = []
    for ln in _split_lines(raw):
        line = ln.strip()
        if not line:
            continue
        parts = [p.strip() for p in _SKILL_ROW_BOUNDARY_RE.split(line) if p.strip()]
        if len(parts) == 1:
            subparts = [p.strip() for p in _PERIOD_BEFORE_SKILL_LABEL_RE.split(line) if p.strip()]
            if len(subparts) > 1:
                parts = subparts
        for part in parts:
            db_parts = [p.strip() for p in _PERIOD_BEFORE_SKILL_LABEL_RE.split(part) if p.strip()]
            rows.extend(db_parts if len(db_parts) > 1 else [part])
    return rows


def _strip_skill_field_value(value: str) -> str:
    return str(value or "").strip().rstrip(".")

_HANDS_ON_SKILLS = frozenset(
    {
        "python",
        "java",
        "javascript",
        "typescript",
        "go",
        "golang",
        "rust",
        "c++",
        "c#",
        "scala",
        "kotlin",
        "ruby",
        "php",
        "swift",
        "r",
        "flask",
        "django",
        "fastapi",
        "spring",
        "spring boot",
        "react",
        "vue",
        "angular",
        "node.js",
        "nodejs",
        ".net",
    }
)

_KNOWLEDGE_SKILLS = frozenset(
    {
        "pandas",
        "numpy",
        "pyspark",
        "spark",
        "ray",
        "scikit-learn",
        "scikit learn",
        "sklearn",
        "pytorch",
        "tensorflow",
        "matplotlib",
        "plotly",
        "seaborn",
        "polars",
        "dask",
        "scipy",
        "aws redshift",
        "redshift",
        "agentic ai",
    }
)

_DATABASE_SKILLS = frozenset(
    {
        "sql",
        "oracle",
        "postgres",
        "postgresql",
        "redis",
        "mysql",
        "mongodb",
        "aurora",
        "opensearch",
        "snowflake",
        "dynamodb",
        "cassandra",
        "mariadb",
        "sqlite",
        "delta table",
        "delta lake",
    }
)

_GIT_HOST_SKILLS = frozenset({"github", "gitlab", "bitbucket"})
_COLLAB_SKILLS = frozenset({"jira", "asana", "confluence", "trello", "slack", "azure devops"})
_DOMAIN_SKILLS = frozenset({"finance", "logistics", "manufacturing", "healthcare", "retail"})
_TOOLS_SKILLS = frozenset(
    {
        "databricks",
        "airflow",
        "apache airflow",
        "aws glue",
        "step functions",
        "athena",
        "lambda",
        "power bi",
        "pytest",
        "pycharm",
        "jupyter notebook",
        "docker",
        "etl",
        "kubernetes",
        "terraform",
    }
)


def _norm_skill_token(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def _looks_like_database_skills_line(line: str) -> bool:
    low = str(line or "").strip().lower()
    if not low or low.startswith(
        (
            "hands-on",
            "knowledge of",
            "experience with",
            "tools:",
            "domain expertise:",
            "git ",
            "technical skills:",
            "technologies:",
        )
    ):
        return False
    if re.match(r"^(cloud\s*&\s*data|databases\s*&\s*sql)\s*:", low):
        return True
    if _looks_like_git_hosts_line(line):
        return False
    if re.match(r"^sql\s*\(", low):
        return True
    markers = (
        "oracle",
        "postgres",
        "redis",
        "mysql",
        "mongodb",
        "aurora",
        "opensearch",
        "snowflake",
        "dynamodb",
        "cassandra",
        "delta table",
        "delta lake",
    )
    return any(m in low for m in markers)


def skills_text_is_categorized(text: str) -> bool:
    """True when skills already use Yuliia-style labeled rows."""
    for raw in _split_skills_into_labeled_rows(text):
        line = raw.strip()
        if not line:
            continue
        if _CATEGORIZED_SKILL_LINE_RE.match(line):
            return True
        if _looks_like_database_skills_line(line) or _looks_like_git_hosts_line(line):
            return True
        labeled = _parse_labeled_skills_line(line)
        if labeled and labeled[0].lower() in {"hands-on experience", "knowledge of", "experience with", "tools"}:
            return True
    return False


def chips_from_skills_text(text: str) -> list[str]:
    """Flat skill chips from any skills_text / chat skills field."""
    seen: set[str] = set()
    out: list[str] = []

    def add(raw: object) -> None:
        for chip in _split_skill_chips(str(raw or "")):
            key = _norm_skill_token(chip)
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(chip)

    for raw in _split_lines(text):
        line = raw.strip()
        if not line:
            continue
        labeled = _parse_labeled_skills_line(line)
        if labeled:
            add(labeled[1])
            continue
        low = line.lower()
        for prefix in ("technical skills:", "technologies:"):
            if low.startswith(prefix):
                add(line.split(":", 1)[-1])
                break
        else:
            if _CATEGORIZED_SKILL_LINE_RE.match(line) or _looks_like_skill_content_line(line):
                add(line)

    if not out and str(text or "").strip():
        add(text)
    return out


def _git_hosts_only_text(text: str) -> str:
    hosts = [_clean_chip(part) for part in re.split(r"[,·]", str(text or "")) if _clean_chip(part)]
    if not hosts:
        return ""
    if all(_norm_skill_token(host) in _GIT_HOST_SKILLS for host in hosts):
        return ", ".join(hosts)
    return ""


def _format_git_skill_line(git_chips: list[str]) -> str:
    hosts = [_clean_chip(c) for c in git_chips if _norm_skill_token(c) in _GIT_HOST_SKILLS]
    has_git = any(_norm_skill_token(c) == "git" for c in git_chips)
    if hosts and not has_git:
        return ", ".join(hosts)
    if has_git and hosts:
        return f"Git ({', '.join(hosts)})"
    if has_git:
        return "Git"
    if hosts:
        return ", ".join(hosts)
    return ""


def _looks_like_git_hosts_line(line: str) -> bool:
    return bool(_git_hosts_only_text(line))


def _is_knowledge_skill(key: str) -> bool:
    if key in _KNOWLEDGE_SKILLS:
        return True
    return any(token in key for token in ("agentic", "machine learning", " llm", "gen ai", "generative ai"))


def _format_database_skill_line(db_chips: list[str]) -> str:
    parts: list[str] = []
    rest: list[str] = []
    for chip in db_chips:
        low = _norm_skill_token(chip)
        if low.startswith("sql"):
            parts.append("SQL (DML)" if "dml" not in low else chip)
        else:
            rest.append(chip)
    parts.extend(rest)
    return ", ".join(parts)


def _strip_databases_label(text: str) -> str:
    cleaned = str(text or "").strip()
    for prefix in (r"^cloud\s*&\s*data\s*:", r"^databases\s*&\s*sql\s*:"):
        if re.match(prefix, cleaned, re.I):
            return cleaned.split(":", 1)[-1].strip()
    return cleaned


def _format_databases_skill_output(text: str) -> str:
    body = _strip_databases_label(text)
    if not body:
        return ""
    return f"Cloud & Data: {body}"


def _clean_chip(chip: str) -> str:
    text = re.sub(r"\s+", " ", str(chip or "")).strip()
    if not text:
        return ""
    mapping = {
        "postgresql": "PostgreSQL",
        "postgres": "Postgres",
        "nodejs": "Node.js",
        "pyspark": "PySpark",
        "git": "Git",
        "github": "GitHub",
        "gitlab": "GitLab",
        "pytest": "PyTest",
        "pycharm": "PyCharm",
    }
    key = text.lower()
    return mapping.get(key, text)


def _ordered_tools_chips(chips: list[str]) -> list[str]:
    git_order = {"git": 0, "github": 1, "gitlab": 2, "bitbucket": 3}
    collab_order = {"jira": 0, "asana": 1, "confluence": 2, "trello": 3, "slack": 4}
    seen: set[str] = set()
    unique: list[str] = []
    for chip in chips:
        clean = _clean_chip(chip)
        if not clean:
            continue
        key = _norm_skill_token(clean)
        if key in seen:
            continue
        seen.add(key)
        unique.append(clean)

    def sort_key(chip: str) -> tuple[int, int, str]:
        key = _norm_skill_token(chip)
        if key in git_order:
            return (0, git_order[key], key)
        if key in ("pytest", "power bi"):
            return (1, 0 if key == "pytest" else 1, key)
        if key in collab_order:
            return (2, collab_order[key], key)
        return (3, 0, key)

    return sorted(unique, key=sort_key)


def _ensure_git_in_tools(chips: list[str]) -> list[str]:
    ordered = _ordered_tools_chips(chips)
    keys = {_norm_skill_token(chip) for chip in ordered}
    if keys & _GIT_HOST_SKILLS and "git" not in keys:
        return ["Git", *ordered]
    return ordered


def _split_tools_body_to_fields(body: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    git_chips: list[str] = []
    collab_chips: list[str] = []
    other: list[str] = []
    for chip in _ordered_tools_chips(_split_skill_chips(body)):
        key = _norm_skill_token(chip)
        if key == "git" or key in _GIT_HOST_SKILLS:
            git_chips.append(chip)
        elif key in _COLLAB_SKILLS:
            collab_chips.append(chip)
        else:
            other.append(chip)
    if git_chips:
        fields["skill_git"] = ", ".join(_ordered_tools_chips(git_chips))
    if collab_chips:
        fields["skill_collab"] = ", ".join(collab_chips)
    if other:
        fields["skill_tools"] = ", ".join(other)
    return fields


def _merge_tools_line(git: str, collab: str, tools: str) -> str:
    combined: list[str] = []
    for raw in (git, collab, tools):
        text = str(raw or "").strip()
        if not text:
            continue
        if text.lower().startswith("tools:"):
            text = text.split(":", 1)[-1].strip()
        combined.extend(_split_skill_chips(text))
    ordered = _ensure_git_in_tools(combined)
    if not ordered:
        return ""
    return f"Tools: {', '.join(ordered)}"


def categorize_skill_chips(chips: list[str]) -> list[str]:
    """Group flat chips into Hands-on / Knowledge / SQL / Git / Experience / Tools rows."""
    hands_on: list[str] = []
    knowledge: list[str] = []
    databases: list[str] = []
    git_items: list[str] = []
    collab: list[str] = []
    domain: list[str] = []
    tools: list[str] = []
    seen: set[str] = set()

    def bucket(chip: str) -> None:
        clean = _clean_chip(chip)
        if not clean:
            return
        key = _norm_skill_token(clean)
        if key in seen:
            return
        seen.add(key)

        if key in _HANDS_ON_SKILLS:
            hands_on.append(clean)
        elif _is_knowledge_skill(key):
            knowledge.append(clean)
        elif key in _DATABASE_SKILLS or key.startswith("sql") or "delta table" in key or "delta lake" in key:
            databases.append(clean)
        elif key == "git" or key in _GIT_HOST_SKILLS:
            git_items.append(clean)
        elif key in _COLLAB_SKILLS:
            collab.append(clean)
        elif key in _DOMAIN_SKILLS:
            domain.append(clean)
        else:
            tools.append(clean)

    for chip in chips:
        bucket(chip)

    lines: list[str] = []
    if hands_on:
        lines.append(f"Hands-on experience {', '.join(hands_on)}")
    if knowledge:
        lines.append(f"Knowledge of {', '.join(knowledge)}")
    db_line = _format_database_skill_line(databases)
    if db_line:
        lines.append(_format_databases_skill_output(db_line))
    git_line = _format_git_skill_line(git_items)
    if git_line:
        lines.append(git_line)
    if collab:
        lines.append(f"Experience with {', '.join(collab)}")
    if tools:
        lines.append(f"Tools: {', '.join(_ensure_git_in_tools(tools))}")
    if domain:
        lines.append(f"Domain expertise: {', '.join(domain)}")
    return lines


def format_skills_text_for_chat(text: str) -> str:
    """Normalize chat/PDF skills into labeled multiline rows (Yuliia-style)."""
    raw = str(text or "").strip()
    if not raw:
        return ""
    if skills_text_is_categorized(raw):
        fields = parse_skills_text_to_fields(raw)
        if fields:
            return merge_skill_fields_from_answers({**fields, "skills": raw})
        return "\n".join(_dedupe_lines([ln.strip() for ln in _split_lines(raw) if ln.strip()]))
    return "\n".join(categorize_skill_chips(chips_from_skills_text(raw)))


SKILL_FIELD_KEYS: tuple[str, ...] = (
    "skill_handsOn",
    "skill_knowledge",
    "skill_databases",
    "skill_git",
    "skill_collab",
    "skill_tools",
    "skill_domain",
)


def parse_skills_text_to_fields(text: str) -> dict[str, str]:
    """Multiline skills block → editable chat keys (skill_handsOn, skill_tools, …)."""
    raw = str(text or "").strip()
    if not raw:
        return {}
    if not skills_text_is_categorized(raw):
        lines = categorize_skill_chips(chips_from_skills_text(raw))
    else:
        lines = _split_skills_into_labeled_rows(raw)
    fields: dict[str, str] = {}
    for line_raw in lines:
        line = str(line_raw).strip()
        if not line:
            continue
        parsed = _parse_skills_line_to_field(line)
        if parsed:
            key, value = parsed
            value = _strip_skill_field_value(value)
            if not value:
                continue
            if key == "__tools__":
                fields.update(_split_tools_body_to_fields(value))
            else:
                fields[key] = value
        elif _looks_like_git_hosts_line(line):
            fields["skill_git"] = _git_hosts_only_text(line)
        elif _looks_like_database_skills_line(line):
            fields["skill_databases"] = _strip_databases_label(line)
    return fields


def merge_skill_fields_from_answers(answers: dict[str, str]) -> str:
    """Editable skill_* keys → single skills_text for structured JSON / PDF."""
    if not isinstance(answers, dict):
        return ""

    lines: list[str] = []
    hands_on = str(answers.get("skill_handsOn") or "").strip()
    if hands_on:
        lines.append(f"Hands-on experience {hands_on}")
    knowledge = str(answers.get("skill_knowledge") or "").strip()
    if knowledge:
        lines.append(f"Knowledge of {knowledge}")
    databases = str(answers.get("skill_databases") or "").strip()
    if databases:
        lines.append(_format_databases_skill_output(databases))
    tools_line = _merge_tools_line(
        str(answers.get("skill_git") or "").strip(),
        str(answers.get("skill_collab") or "").strip().rstrip(","),
        str(answers.get("skill_tools") or "").strip(),
    )
    if tools_line:
        lines.append(tools_line)
    domain = str(answers.get("skill_domain") or "").strip()
    if domain:
        body = domain.split(":", 1)[-1].strip() if domain.lower().startswith("domain expertise:") else domain
        lines.append(f"Domain expertise: {body}")

    if lines:
        return "\n".join(lines)
    return str(answers.get("skills") or answers.get("mainTechStack") or "").strip()


def expand_skill_fields_in_answers(answers: dict[str, str]) -> dict[str, str]:
    """Ensure skill_* edit fields exist when only combined skills text is stored."""
    if not isinstance(answers, dict):
        return {}
    out = dict(answers)
    combined = str(out.get("skills") or out.get("mainTechStack") or "").strip()
    if combined:
        parsed = parse_skills_text_to_fields(combined)
        if parsed:
            if skills_text_is_categorized(combined):
                for key in SKILL_FIELD_KEYS:
                    if parsed.get(key):
                        out[key] = parsed[key]
            else:
                for key, value in parsed.items():
                    if value and not str(out.get(key) or "").strip():
                        out[key] = value
    merged = merge_skill_fields_from_answers(out)
    if merged:
        out["skills"] = format_skills_text_for_chat(merged)
    return out


def skills_lines_for_render(text: str, *, skills_list: list[str] | None = None) -> list[str]:
    """Skill rows for PDF renderers."""
    raw = str(text or "").strip()
    if raw and skills_text_is_categorized(raw):
        return _dedupe_lines([ln.strip() for ln in _split_skills_into_labeled_rows(raw) if ln.strip()])
    chips = chips_from_skills_text(raw)
    if not chips and skills_list:
        chips = [_clean_chip(x) for x in skills_list if _clean_chip(x)]
    return categorize_skill_chips(chips)


def _parse_skills_line_to_field(line: str) -> tuple[str, str] | None:
    text = str(line or "").strip()
    if not text:
        return None
    low = text.lower()
    if low.startswith("hands-on experience "):
        return "skill_handsOn", text[len("Hands-on experience ") :].strip()
    if low.startswith("knowledge of "):
        return "skill_knowledge", text[len("Knowledge of ") :].strip()
    if low.startswith("experience with "):
        return "skill_collab", text[len("Experience with ") :].strip()
    if low.startswith("tools:"):
        return "__tools__", text.split(":", 1)[-1].strip()
    if low.startswith("domain expertise:"):
        return "skill_domain", text.split(":", 1)[-1].strip()
    if re.match(r"^(cloud\s*&\s*data|databases\s*&\s*sql)\s*:", low):
        return "skill_databases", _strip_databases_label(text)
    git_match = re.match(r"^Git\s*\(([^)]+)\)\s*$", text, re.I)
    if git_match:
        return "skill_git", git_match.group(1).strip()
    git_hosts = _git_hosts_only_text(text)
    if git_hosts:
        return "skill_git", git_hosts
    if _looks_like_database_skills_line(text):
        return "skill_databases", text
    return None


def _split_comma_separated(text: str) -> list[str]:
    """Split on commas outside parentheses: «Git (GitHub, Gitlab)» stays one part."""
    parts: list[str] = []
    current: list[str] = []
    depth = 0
    for char in str(text or ""):
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        if char == "," and depth == 0:
            chunk = "".join(current).strip()
            if chunk:
                parts.append(chunk)
            current = []
            continue
        current.append(char)
    chunk = "".join(current).strip()
    if chunk:
        parts.append(chunk)
    return parts


def _extract_skill_segment_body(segment: str) -> str:
    """Strip inline labels: «Hands-on experience Python…» or «Tools: PyCharm…»."""
    seg = re.sub(r"\s+", " ", str(segment or "")).strip().rstrip(".")
    if not seg:
        return ""
    low = seg.casefold()
    for label in _SKILL_LABEL_PREFIXES:
        for prefix in (f"{label}:", f"{label} "):
            if low.startswith(prefix):
                return seg[len(prefix) :].strip()
    if low.startswith("experience with "):
        return seg[len("experience with ") :].strip()
    return seg


def _parse_skill_chip(raw: str) -> list[str]:
    """One chip; expand «Git (GitHub, Gitlab)», drop qualifier in «SQL (DML)»."""
    chip = re.sub(r"\s+", " ", str(raw or "")).strip().rstrip(".")
    if not chip or len(chip) >= 80:
        return []

    paren = re.match(r"^(.+?)\s*\(([^)]+)\)\s*$", chip)
    if not paren:
        return [chip]

    head = paren.group(1).strip()
    inner = paren.group(2).strip()
    if not head:
        return _split_skill_chips(inner)

    inner_parts = [p.strip() for p in re.split(r"[·•,;/|]", inner) if p.strip()]
    if len(inner_parts) == 1 and (
        re.fullmatch(r"[A-Z]{2,6}", inner_parts[0])
        or len(inner_parts[0]) <= 5
    ):
        return [head]
    out = [head]
    for part in inner_parts:
        out.extend(_parse_skill_chip(part))
    return out


def _split_skill_chips(text: str) -> list[str]:
    raw = str(text or "").strip()
    if not raw:
        return []

    segments = re.split(r"\.\s+", raw) if re.search(r"\.\s+[A-Za-z]", raw) else [raw]
    items: list[str] = []
    for segment in segments:
        body = _extract_skill_segment_body(segment)
        if not body:
            continue
        for part in _split_comma_separated(body):
            for sub in re.split(r"[·•;\n|]", part):
                items.extend(_parse_skill_chip(sub))
    return items


def _parse_labeled_skills_line(line: str) -> tuple[str, str] | None:
    raw = str(line or "").strip()
    if not raw:
        return None
    low = raw.lower()
    for label in _SKILL_LABEL_PREFIXES:
        prefix = f"{label}:"
        if low.startswith(prefix):
            body = raw[len(prefix) :].strip()
            return label.title(), body
    return None


def _looks_like_skill_content_line(line: str) -> bool:
    text = str(line or "").strip()
    if not text or len(text) > 220:
        return False
    if _parse_labeled_skills_line(text):
        return True
    low = text.lower()
    if low.startswith(("portfolio:", "github:", "linkedin:")):
        return False
    if _looks_like_certificate_line(text):
        return False
    if _looks_like_duty_line(text) or _parse_paren_company_job_line(text):
        return False
    if _looks_like_course_line(text) or _looks_like_education_line(text):
        return False
    if re.search(r"\d{4}", text) and _ROLE_LINE_HINT.search(text):
        return False
    if "|" in text:
        return False
    if any(k in low for k in ("python", "sql", "aws", "azure", "gcp", "spark", "pytorch", "docker", "kubernetes")):
        return True
    if "," in text and len(text) < 180 and not re.search(r"\d{4}", text):
        return True
    return False


def _extract_skills_from_plain_text(text: str) -> dict[str, str]:
    """Technical Skills / Technologies / SKILLS-секция → текст для чата и mainTechStack."""
    if not str(text or "").strip():
        return {}

    sections = _extract_named_sections(text)
    blocks: list[str] = []
    tech_chips: list[str] = []
    seen_blocks: set[str] = set()

    def _add_block(label: str, body: str) -> None:
        chips = _split_skill_chips(body)
        if not chips:
            return
        block = f"{label}: {', '.join(chips)}"
        key = block.lower()
        if key in seen_blocks:
            return
        seen_blocks.add(key)
        blocks.append(block)
        tech_chips.extend(chips)

    def _ingest_labeled_skill_line(line: str) -> None:
        """Hands-on experience … / Tools: … / Technical Skills: … rows."""
        line = str(line or "").strip()
        if not line or _looks_like_certificate_line(line):
            return
        if line.lower() in {"hands-on experience", "hands on experience"}:
            return
        if _CATEGORIZED_SKILL_LINE_RE.match(line):
            key = line.lower()
            if key not in seen_blocks:
                seen_blocks.add(key)
                blocks.append(line)
                tech_chips.extend(_split_skill_chips(line))
            return
        labeled = _parse_labeled_skills_line(line)
        if labeled and labeled[0].lower() in {"hands-on experience", "knowledge of", "experience with", "tools"}:
            key = line.lower()
            if key not in seen_blocks:
                seen_blocks.add(key)
                blocks.append(line)
                tech_chips.extend(_split_skill_chips(labeled[1]))
            return
        if labeled:
            _add_block(labeled[0], labeled[1])

    def _ingest_skill_section_line(line: str) -> None:
        _ingest_labeled_skill_line(line)
        line = str(line or "").strip()
        if not line:
            return
        if _looks_like_git_hosts_line(line):
            key = line.lower()
            if key not in seen_blocks:
                seen_blocks.add(key)
                blocks.append(line)
                tech_chips.extend(_split_skill_chips(line))
            return
        if _looks_like_database_skills_line(line):
            key = line.lower()
            if key not in seen_blocks:
                seen_blocks.add(key)
                blocks.append(_format_databases_skill_output(_strip_databases_label(line)))
                tech_chips.extend(_split_skill_chips(line))
            return
        if _looks_like_skill_content_line(line):
            chips = _split_skill_chips(line.split(":", 1)[-1] if ":" in line else line)
            if chips:
                block = ", ".join(chips)
                if block.lower() not in seen_blocks:
                    seen_blocks.add(block.lower())
                    blocks.append(block)
                    tech_chips.extend(chips)

    skill_section_lines = list(sections.get("SKILLS") or [])
    if not skill_section_lines:
        in_skills = False
        for raw in _split_lines(text):
            line = raw.strip()
            header = _match_section_header(line)
            if header == "SKILLS":
                in_skills = True
                continue
            if header and in_skills:
                break
            if in_skills and line:
                skill_section_lines.append(line)

    for line in skill_section_lines:
        _ingest_skill_section_line(line)

    # Yuliia-style PDFs often place labeled skill rows before the SKILLS header.
    for raw in _split_lines(text):
        line = raw.strip()
        if not line or _match_section_header(line):
            continue
        _ingest_labeled_skill_line(line)

    skills_text = "\n".join(blocks)
    main_stack = ", ".join(_dedupe_lines(tech_chips)[:40])
    out: dict[str, str] = {}
    if skills_text:
        out["skills"] = skills_text
    if main_stack:
        out["mainTechStack"] = main_stack
    return out


def _extract_supplementary_from_plain_text(text: str) -> dict[str, str]:
    """Курсы, образование, языки, objective из plain text (в т.ч. перемешанный PDF)."""
    if not str(text or "").strip():
        return {}

    sections = _extract_named_sections(text)
    course_lines: list[str] = []
    lang_lines: list[str] = []

    for line in sections.get("SKILLS") or []:
        if _looks_like_certificate_line(line):
            body = line.split(":", 1)[-1].strip()
            course_lines.extend(_split_skill_chips(body))
    for line in sections.get("COURSES") or []:
        chunk = line.strip()
        if not chunk:
            continue
        low = chunk.lower()
        if low.startswith(("http://", "https://", "www.")) or "://" in low:
            continue
        if low in {"certifications", "certificates", "courses"}:
            continue
        if "@" in chunk and "linkedin.com" not in low:
            continue
        # В named-секции CERTIFICATES/COURSES строки — названия курсов, не фильтруем по «bootcamp».
        course_lines.append(chunk.lstrip("-• ").strip())
    for line in sections.get("LANGUAGES") or []:
        if _looks_like_language_line(line):
            lang_lines.append(line)

    for raw in _split_lines(text):
        line = raw.strip()
        if not line or _match_section_header(line):
            continue
        if _looks_like_certificate_line(line):
            course_lines.extend(_split_skill_chips(line.split(":", 1)[-1]))
            continue
        low = line.lower()
        if low.startswith(("http://", "https://", "www.")) or "://" in low:
            continue
        if _looks_like_course_line(line):
            course_lines.append(line)
            continue
        if _looks_like_language_line(line):
            lang_lines.append(line)
            continue
        if _parse_job_header_line(line) or _parse_dot_format_job_line(line):
            continue

    objective = ""
    for line in sections.get("OBJECTIVE") or []:
        if line.strip():
            objective = line.strip()
            break
    if not objective:
        for raw in _split_lines(text):
            line = raw.strip()
            if line.lower().startswith("obtain "):
                objective = line
                break

    cleaned_courses = _dedupe_lines(
        [
            ln.lstrip("-• ").strip()
            for ln in course_lines
            if ln.strip()
            and not str(ln).lower().startswith(("http://", "https://", "www."))
            and "://" not in str(ln)
            and not ("@" in str(ln) and "linkedin.com" not in str(ln).lower())
        ]
    )

    return {
        "courses": _lines_to_bullet_block(cleaned_courses),
        "education": _extract_education_block(sections, text),
        "languages": _lines_to_bullet_block(lang_lines),
        "interests": _extract_interests_block(sections),
        "projects": _extract_projects_from_plain_text(text),
        "desiredPosition": objective,
    }


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


def _parse_chips(text: str) -> list[str]:
    items: list[str] = []
    for part in re.split(r"[,;\n]", text or ""):
        s = part.strip()
        if s:
            items.append(s)
    return items


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


def _skills_from_jobs_and_profile(answers: dict[str, str], jobs: list[dict]) -> list[str]:
    skills: list[str] = []
    seen: set[str] = set()
    stack = str(
        answers.get("mainTechStack") or answers.get("skills") or answers.get("strongTechnologies") or ""
    ).strip()
    for item in _parse_chips(stack):
        low = item.lower()
        if low not in seen:
            seen.add(low)
            skills.append(item)
    if not skills:
        for raw in _split_lines(stack):
            labeled = _parse_labeled_skills_line(raw)
            if labeled:
                for item in _split_skill_chips(labeled[1]):
                    low = item.lower()
                    if low not in seen:
                        seen.add(low)
                        skills.append(item)
            else:
                for item in _split_skill_chips(raw):
                    low = item.lower()
                    if low not in seen:
                        seen.add(low)
                        skills.append(item)
    for job in jobs:
        for tech in job.get("technologies") or []:
            low = str(tech).lower()
            if low not in seen:
                seen.add(low)
                skills.append(str(tech))
    return skills[:32]


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


def _normalize_skill_item(item: object) -> str:
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        return str(
            item.get("name") or item.get("skill") or item.get("title") or item.get("technology") or ""
        ).strip()
    return str(item).strip()


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


def clamp_desired_role(text: str, max_len: int | None = None) -> str:
    """Fit desired role into DB column (resume_profiles.desired_role VARCHAR)."""
    limit = DESIRED_ROLE_MAX_LEN if max_len is None else max_len
    cleaned = re.sub(r"\s+", " ", str(text or "").strip())
    if not cleaned or len(cleaned) <= limit:
        return cleaned
    cut = cleaned[:limit]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip(".,;:- ")


def _first_sentence(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(text or "").strip())
    if not cleaned:
        return ""
    match = re.match(r"^(.{1,500}?[.!?])(?:\s|$)", cleaned)
    if match:
        return match.group(1).strip()
    return cleaned


_SECTION_HEADER_RE = re.compile(
    r"^(professional summary|summary|experience|work experience|education|skills|certifications|languages|projects)\b",
    re.IGNORECASE,
)
_HEADLINE_ROLE_WORDS = (
    "engineer",
    "developer",
    "analyst",
    "manager",
    "architect",
    "qa",
    "tester",
    "consultant",
    "specialist",
    "lead",
    "director",
    "designer",
    "administrator",
)


def _looks_like_resume_headline(line: str) -> bool:
    text = str(line or "").strip()
    if not text or len(text) > 160:
        return False
    low = text.lower()
    if _SECTION_HEADER_RE.match(text):
        return False
    if _looks_like_contact_line(text):
        return False
    if low.startswith(("email", "phone", "linkedin", "github", "xing", "website", "portfolio")):
        return False
    if "|" in text:
        return True
    letters = [c for c in text if c.isalpha()]
    if letters:
        upper_ratio = sum(1 for c in letters if c.isupper()) / len(letters)
        if upper_ratio > 0.55 and len(text) <= 90:
            return True
    if any(word in low for word in _HEADLINE_ROLE_WORDS):
        return True
    return False


def _extract_headline_from_plain_text(text: str) -> str:
    lines = [ln for ln in _split_lines(text) if ln.strip()]
    if len(lines) < 2:
        return ""
    for line in lines[1:8]:
        if _looks_like_resume_headline(line):
            return line.strip()
    return ""


def resolve_desired_role(
    structured: dict,
    *,
    desired_role: str | None = None,
    plain_text: str = "",
) -> str:
    """Short job title for desired_role — never the full professional summary."""
    roles = structured.get("desired_roles")
    if isinstance(roles, list) and roles:
        candidate = str(roles[0]).strip()
        if candidate:
            return clamp_desired_role(candidate)

    for key in ("objective",):
        candidate = str(structured.get(key) or "").strip()
        if candidate:
            return clamp_desired_role(candidate)

    headline = _extract_headline_from_plain_text(plain_text)
    if headline:
        return clamp_desired_role(headline)

    plain_supp = _extract_supplementary_from_plain_text(plain_text) if plain_text else {}
    candidate = str(plain_supp.get("desiredPosition") or "").strip()
    if candidate:
        return clamp_desired_role(candidate)

    summary = str(structured.get("summary") or "").strip()
    if summary:
        return clamp_desired_role(_first_sentence(summary))

    return clamp_desired_role(str(desired_role or ""))


def structured_to_chat_answers(structured: dict, *, desired_role: str | None = None) -> dict[str, str]:
    """Structured JSON (cv.yml in DB) → flat chat answers for the editor."""
    from job_application.resume.cv_schema import cv_to_chat_answers, normalize_to_cv

    if not isinstance(structured, dict):
        return {}

    answers = cv_to_chat_answers(normalize_to_cv(structured))
    if desired_role and not answers.get("headline"):
        answers["headline"] = str(desired_role).strip()
    return answers


def _legacy_structured_to_chat_answers_unused(structured: dict, *, desired_role: str | None = None) -> dict[str, str]:
    p = structured.get("personal") if isinstance(structured.get("personal"), dict) else {}
    full_name = " ".join(
        x for x in [str(p.get("first_name") or "").strip(), str(p.get("last_name") or "").strip()] if x
    ).strip() or str(p.get("full_name") or "").strip()

    portfolio = str(p.get("portfolio") or "").strip()
    urls = p.get("portfolio_urls")
    if not portfolio and isinstance(urls, list):
        for url in urls:
            text = str(url).strip()
            if text:
                portfolio = text
                break

    plain_text = str(structured.get("_resume_plain_text") or "").strip()
    if not portfolio and plain_text:
        portfolio = _extract_portfolio_from_plain_text(plain_text)
    plain_supp = _extract_supplementary_from_plain_text(plain_text) if plain_text else {}
    plain_skills = _extract_skills_from_plain_text(plain_text) if plain_text else {}
    plain_contact = _extract_contact_from_plain_text(plain_text) if plain_text else {}

    if portfolio:
        links, parsed = _merge_social_links(portfolio, p.get("linkedin"), p.get("github"))
    else:
        links, parsed = _merge_social_links(
            p.get("linkedin"),
            p.get("github"),
            plain_contact.get("linkedin"),
            plain_contact.get("github"),
        )
    linkedin = parsed["linkedin"]
    github = parsed["github"]

    desired_positions = resolve_desired_role(
        structured,
        desired_role=desired_role,
        plain_text=plain_text,
    )

    languages_text = str(structured.get("languages_text") or "").strip() or _language_lines(structured.get("languages"))
    education_text = str(structured.get("education_text") or "").strip() or _education_text_from_structured(
        structured.get("education")
    )
    certificates_text = str(structured.get("courses_text") or "").strip() or _certificates_text_from_structured(
        structured.get("certifications") or structured.get("courses")
    )
    skills_text = str(structured.get("skills_text") or "").strip() or _tech_stack_from_structured(structured)
    main_tech_stack = ""
    raw_stack = structured.get("main_tech_stack") or structured.get("skills")
    if isinstance(raw_stack, list):
        main_tech_stack = ", ".join(str(x).strip() for x in raw_stack if str(x).strip())
    elif isinstance(raw_stack, str):
        main_tech_stack = raw_stack.strip()

    if not languages_text and plain_supp.get("languages"):
        languages_text = plain_supp["languages"]
    if plain_text:
        education_text = _prefer_plain_supplementary(education_text, plain_supp.get("education", ""))
        languages_text = _prefer_plain_supplementary(languages_text, plain_supp.get("languages", ""))
        certificates_text = _prefer_plain_supplementary(certificates_text, plain_supp.get("courses", ""))
        skills_text = _prefer_plain_supplementary(skills_text, plain_skills.get("skills", ""))
        main_tech_stack = _prefer_plain_supplementary(main_tech_stack, plain_skills.get("mainTechStack", ""))
    elif not education_text and plain_supp.get("education"):
        education_text = plain_supp["education"]
    if not certificates_text and plain_supp.get("courses"):
        certificates_text = plain_supp["courses"]
    if not skills_text and plain_skills.get("skills"):
        skills_text = plain_skills["skills"]
    if not main_tech_stack and plain_skills.get("mainTechStack"):
        main_tech_stack = plain_skills["mainTechStack"]
    if skills_text:
        skills_text = format_skills_text_for_chat(skills_text)

    interests_text = str(structured.get("interests_text") or "").strip()
    if plain_text:
        interests_text = _prefer_plain_supplementary(interests_text, plain_supp.get("interests", ""))
    elif not interests_text and plain_supp.get("interests"):
        interests_text = plain_supp["interests"]

    projects_text = str(structured.get("projects_text") or "").strip()
    if plain_text:
        projects_text = _prefer_plain_supplementary(projects_text, plain_supp.get("projects", ""))
    elif not projects_text and plain_supp.get("projects"):
        projects_text = plain_supp["projects"]

    location = _sanitize_contact_location(
        str(p.get("location") or p.get("city") or "").strip() or plain_contact.get("location", "")
    )

    answers: dict[str, str] = {
        "fullName": full_name,
        "city": location,
        "phone": str(p.get("phone") or "").strip() or plain_contact.get("phone", ""),
        "email": str(p.get("email") or "").strip() or plain_contact.get("email", ""),
        "links": links,
        "linkedin": linkedin or plain_contact.get("linkedin", ""),
        "github": github or plain_contact.get("github", ""),
        "desiredPosition": desired_positions,
        "skills": skills_text,
        "mainTechStack": main_tech_stack,
        "languages": languages_text,
        "education": education_text,
        "courses": certificates_text,
        "interests": interests_text,
        "projects": projects_text,
    }
    summary_text = str(structured.get("summary") or "").strip()
    if summary_text:
        answers["summary"] = summary_text

    jobs = _experience_entries_from_structured(structured)
    if isinstance(jobs, list) and jobs:
        for idx, job in enumerate(jobs):
            prefix = f"job_{idx}_"
            dates_raw = str(job.get("dates") or "").strip()
            if not dates_raw:
                dates_raw = " — ".join(
                    x for x in (str(job.get("start_date") or "").strip(), str(job.get("end_date") or "").strip()) if x
                )

            position = str(job.get("position") or job.get("title") or "").strip()
            company = _normalize_company_label(str(job.get("company") or "").strip())
            position, parsed_company = _split_merged_position_company(position, company)
            if not company and parsed_company:
                company = parsed_company
            role_and_dates = ", ".join(x for x in (position, dates_raw) if x)

            description = _job_description_for_chat(job)

            result = ""
            for field in ("improvements", "achievements"):
                val = job.get(field)
                if isinstance(val, list) and val:
                    result = "\n".join(str(x) for x in val if str(x).strip())
                    break
                if isinstance(val, str) and val.strip():
                    result = val.strip()
                    break

            technologies = job.get("technologies")
            if isinstance(technologies, list):
                tech_text = ", ".join(str(x).strip() for x in technologies if str(x).strip())
            else:
                tech_text = str(technologies or "").strip()

            answers.update(
                {
                    f"{prefix}company": company or str(job.get("company") or "").strip(),
                    f"{prefix}roleAndDates": role_and_dates,
                    f"{prefix}description": description,
                    f"{prefix}raw_description": description,
                    f"{prefix}result": result,
                }
            )
            if tech_text:
                answers[f"{prefix}technologies"] = tech_text
                answers[f"{prefix}needs_tech_fallback"] = "0"
            elif description:
                answers[f"{prefix}needs_tech_fallback"] = "1"

            responsibilities = job.get("responsibilities")
            if isinstance(responsibilities, list) and responsibilities:
                answers[f"{prefix}responsibilities_json"] = json.dumps(
                    [str(x).strip() for x in responsibilities if str(x).strip()],
                    ensure_ascii=False,
                )

    global_tech = str(answers.get("mainTechStack") or answers.get("skills") or "").strip()
    if global_tech:
        for key in list(answers.keys()):
            if key.endswith("_needs_tech_fallback") and not answers.get(key.replace("needs_tech_fallback", "technologies")):
                answers[key] = "0"

    return {k: v for k, v in expand_skill_fields_in_answers(answers).items() if str(v).strip()}


def chat_answers_to_structured(answers: dict[str, str]) -> dict:
    """Преобразует ответы чат-мастера в structured JSON (cv.yml schema in DB)."""
    from job_application.config import RESUME_PLAIN_TEXT_KEY
    from job_application.resume.cv_schema import chat_answers_to_cv

    a = expand_skill_fields_in_answers(_legacy_answers(answers))
    merged_skills = merge_skill_fields_from_answers(a)
    if merged_skills:
        a["skills"] = format_skills_text_for_chat(merged_skills)

    if _is_career_interview_answers(a):
        cv = chat_answers_to_cv(a)
        pdf_plain = str(a.get(RESUME_PLAIN_TEXT_KEY) or "").strip()
        if pdf_plain:
            cv[RESUME_PLAIN_TEXT_KEY] = pdf_plain
        return cv

    full_name = str(a.get("fullName") or a.get("name") or "").strip()
    parts = full_name.split()
    first_name = parts[0] if parts else ""
    last_name = " ".join(parts[1:]).strip() if len(parts) > 1 else ""

    contact_links = _parse_contact_links(str(a.get("contactLinks") or ""))
    objective = str(a.get("objective") or "").strip()
    skills_text = str(a.get("skills") or "").strip()
    experience_text = str(a.get("experience") or "").strip()
    courses_text = str(a.get("courses") or "").strip()
    education_text = str(a.get("education") or "").strip()
    interests_text = str(a.get("interests") or "").strip()
    projects_text = str(a.get("projects") or "").strip()
    languages_text = _normalize_languages_block(str(a.get("languages") or ""))

    experience = _parse_experience_block(experience_text) if experience_text else []
    courses = _parse_courses(courses_text)

    skills_list = [
        s.strip()
        for s in re.split(r"[,;\n]", skills_text)
        if s.strip() and len(s.strip()) < 80 and not s.strip().lower().startswith("tools")
    ][:24]

    return {
        "personal": {
            "full_name": full_name,
            "first_name": first_name,
            "last_name": last_name,
            "email": str(a.get("email") or "").strip(),
            "phone": str(a.get("phone") or "").strip(),
            "location": _sanitize_contact_location(str(a.get("city") or "")),
            "github": contact_links.get("github", ""),
            "linkedin": contact_links.get("linkedin", ""),
            "xing": contact_links.get("xing", ""),
        },
        "objective": objective,
        "summary": objective,
        "skills_text": skills_text,
        "skills": skills_list,
        "experience_text": experience_text,
        "experience": experience,
        "courses_text": courses_text,
        "courses": courses,
        "certifications": courses,
        "education_text": education_text,
        "education": _education_entries_from_chat_or_structured(education_text, []),
        "languages_text": languages_text,
        "languages": [ln.lstrip("- ").strip() for ln in languages_text.splitlines() if ln.strip()],
        "interests_text": interests_text,
        "interests": [ln.lstrip("- ").strip() for ln in interests_text.splitlines() if ln.strip()],
        "projects_text": projects_text,
        "projects": _parse_projects_chat_text(projects_text),
    }


def structured_profile_to_plain_text(data: dict) -> str:
    """Текст резюме в формате resume.txt."""
    from job_application.resume.cv_schema import cv_to_plain_text, is_cv_structured, normalize_to_cv

    if is_cv_structured(data):
        return cv_to_plain_text(data)
    if isinstance(data, dict) and data.get("chat_format") == "cv_yml":
        return cv_to_plain_text(normalize_to_cv(data))

    pers = data.get("personal") if isinstance(data.get("personal"), dict) else {}
    name = " ".join(
        x for x in [str(pers.get("first_name") or "").strip(), str(pers.get("last_name") or "").strip()] if x
    ).strip()
    if not name:
        name = str(pers.get("full_name") or "").strip()

    lines: list[str] = []
    if name:
        lines.append(name.upper())
    lines.append("")
    lines.append("CONTACT")

    phone = str(pers.get("phone") or "").strip()
    email = str(pers.get("email") or "").strip()
    if phone:
        lines.append(f"Phone/WhatsApp: {phone}")
    if email:
        lines.append(f"E-mail: {email}")

    for label, key in (("GitHub", "github"), ("LinkedIn", "linkedin"), ("Xing", "xing")):
        val = str(pers.get(key) or "").strip()
        if val:
            lines.append(f"{label}: {val}")

    objective = str(data.get("objective") or data.get("summary") or "").strip()
    if objective:
        lines.extend(["", "OBJECTIVE", objective])

    skills_text = str(data.get("skills_text") or "").strip()
    if not skills_text:
        skills = data.get("skills")
        if isinstance(skills, list) and skills:
            skills_text = ", ".join(str(x).strip() for x in skills if str(x).strip())
    if skills_text:
        lines.extend(["", "SKILLS", "", skills_text])

    experience_text = str(data.get("experience_text") or "").strip()
    if not experience_text or data.get("_keep_stored_experience_bullets"):
        exp = data.get("experience")
        if isinstance(exp, list) and exp:
            experience_text = _experience_text_from_jobs(exp)
    if experience_text:
        lines.extend(["", "EXPERIENCE", "", experience_text])

    courses_text = str(data.get("courses_text") or "").strip()
    if not courses_text:
        courses = data.get("courses") or data.get("certifications")
        if isinstance(courses, list) and courses:
            courses_text = "\n".join(
                f"- {c}" if not str(c).strip().startswith("-") else str(c).strip() for c in courses if str(c).strip()
            )
    if courses_text:
        lines.extend(["", "COURSES", courses_text if courses_text.lstrip().startswith("-") else f"- {courses_text}"])

    education_text = str(data.get("education_text") or "").strip()
    if not education_text:
        edu = data.get("education")
        if isinstance(edu, list) and edu:
            edu_lines: list[str] = []
            for e in edu:
                if not isinstance(e, dict):
                    continue
                inst = str(e.get("institution") or "").strip()
                degree = str(e.get("degree") or "").strip()
                if inst:
                    edu_lines.append(inst)
                if degree:
                    edu_lines.append(degree)
            education_text = "\n".join(edu_lines)
    if education_text:
        lines.extend(["", "EDUCATION", education_text])

    languages_text = str(data.get("languages_text") or "").strip()
    if not languages_text:
        langs = data.get("languages")
        if isinstance(langs, list) and langs:
            languages_text = _normalize_languages_block(
                "\n".join(str(x).strip() for x in langs if str(x).strip())
            )
    if languages_text:
        lines.extend(["", "LANGUAGES", languages_text])

    interests_text = str(data.get("interests_text") or "").strip()
    if not interests_text:
        interests = data.get("interests")
        if isinstance(interests, list) and interests:
            interests_text = _lines_to_bullet_block([str(x).strip() for x in interests if str(x).strip()])
    if interests_text:
        lines.extend(["", "INTERESTS", interests_text])

    projects_text = str(data.get("projects_text") or "").strip()
    if not projects_text:
        projects = data.get("projects")
        if isinstance(projects, list) and projects:
            blocks: list[str] = []
            for item in projects:
                if isinstance(item, dict):
                    blocks.append(f"- {_format_project_heading(item)}\n  {item.get('description', '')}".strip())
                elif str(item).strip():
                    blocks.append(str(item).strip())
            projects_text = "\n\n".join(blocks)
    if projects_text:
        lines.extend(["", "PROJECTS", projects_text])

    return "\n".join(lines).strip()
