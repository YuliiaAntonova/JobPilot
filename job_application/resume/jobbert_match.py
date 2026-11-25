"""JobBERT match helpers for tailor analyze/generate (extracted from safe_tailoring._core)."""

from __future__ import annotations

import logging
import re
from typing import Any

import yaml

logger = logging.getLogger("job_application.jobbert_match")

try:
    from job_application.scoring.jobbert import compute_jobbert_skill_match
except Exception:  # pragma: no cover - optional heavy deps
    compute_jobbert_skill_match = None  # type: ignore[assignment]

_SKILL_CONTAINER_KEYS = (
    "items",
    "skills",
    "stack",
    "technologies",
    "tech_stack",
    "core_skills",
    "technical_skills",
    "main_tech_stack",
)
_SKILL_DICT_NAME_KEYS = ("name", "label", "text", "value")
_SKILL_TOP_LEVEL_KEYS = (
    "skills",
    "main_tech_stack",
    "technical_skills",
    "technologies",
    "tech_stack",
    "core_skills",
    "skills_text",
    "skills_summary",
)

_SEMANTIC_STOPWORDS = frozenset(
    {
        "with",
        "from",
        "that",
        "this",
        "have",
        "has",
        "had",
        "been",
        "were",
        "was",
        "are",
        "and",
        "for",
        "the",
        "into",
        "onto",
        "over",
        "under",
        "using",
        "used",
        "able",
        "also",
        "such",
        "than",
        "then",
        "when",
        "where",
        "which",
        "while",
        "about",
        "across",
        "after",
        "before",
        "between",
        "during",
        "through",
        "within",
        "without",
        "candidate",
        "resume",
        "role",
        "team",
        "work",
        "working",
        "strong",
        "good",
        "deep",
        "solid",
        "hands",
        "on",
    }
)


def parse_original_resume_yaml(resume_text: str) -> dict | None:
    """Parse resume text as YAML mapping; None for plain PDF/DOCX/TXT."""
    try:
        data = yaml.safe_load(resume_text)
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _is_skill_chip(text: str) -> bool:
    text = str(text or "").strip()
    if not text or len(text) > 80:
        return False
    if text.startswith("{") or text.startswith("["):
        return False
    if text.endswith(":"):
        return False
    return True


def _flatten_skill_entries(raw: Any) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()

    def add(raw_value: Any) -> None:
        text = str(raw_value or "").strip()
        if not _is_skill_chip(text):
            return
        key = text.casefold()
        if key in seen:
            return
        seen.add(key)
        out.append(text)

    def walk(node: Any) -> None:
        if node is None:
            return
        if isinstance(node, str):
            if any(sep in node for sep in (",", ";", "|")):
                for part in re.split(r"[,;|]", node):
                    add(part.strip())
            add(node)
            return
        if isinstance(node, (int, float, bool)):
            return
        if isinstance(node, list):
            for item in node:
                walk(item)
            return
        if isinstance(node, dict):
            for key in _SKILL_CONTAINER_KEYS:
                if key in node:
                    walk(node[key])
                    return
            for key in _SKILL_DICT_NAME_KEYS:
                if key in node:
                    add(node.get(key))
                    return

    walk(raw)
    return out


def flatten_cv_skills_for_jobbert(structured: dict | None) -> list[str]:
    if not isinstance(structured, dict):
        return []

    chips: list[str] = []
    seen: set[str] = set()

    def extend(raw: Any) -> None:
        for chip in _flatten_skill_entries(raw):
            key = chip.casefold()
            if key in seen:
                continue
            seen.add(key)
            chips.append(chip)

    for key in _SKILL_TOP_LEVEL_KEYS:
        if key in structured:
            extend(structured.get(key))

    return chips


def cv_yaml_to_jobbert_plain(structured: dict | None, fallback_text: str = "") -> str:
    if not isinstance(structured, dict):
        return str(fallback_text or "").strip()

    parts: list[str] = []

    basics = structured.get("basics") or {}
    if isinstance(basics, dict):
        for key in ("summary", "headline"):
            value = str(basics.get(key) or "").strip()
            if value:
                parts.append(value)

    flat_skills = flatten_cv_skills_for_jobbert(structured)
    if flat_skills:
        parts.append("SKILLS\n" + ", ".join(flat_skills))

    for section_key, title in (
        ("experience", "EXPERIENCE"),
        ("experience_earlier", "EARLIER EXPERIENCE"),
    ):
        entries = structured.get(section_key) or []
        if not isinstance(entries, list):
            continue

        section_lines: list[str] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue

            header = " ".join(
                str(entry.get(field) or "").strip()
                for field in ("company", "title", "role", "period")
                if str(entry.get(field) or "").strip()
            )
            if header:
                section_lines.append(header)

            bullets = entry.get("bullets")
            if bullets is None:
                bullets = entry.get("stack")
            if isinstance(bullets, list):
                for bullet in bullets:
                    bullet_text = str(bullet or "").strip()
                    if bullet_text:
                        section_lines.append(f"- {bullet_text}")
            elif isinstance(bullets, str) and bullets.strip():
                section_lines.append(f"- {bullets.strip()}")

        if section_lines:
            parts.append(title + "\n" + "\n".join(section_lines))

    text = "\n\n".join(parts).strip()
    return text or str(fallback_text or "").strip()


def _expand_skill_aliases(skills: list[str]) -> list[str]:
    expanded = list(skills)
    seen = {skill.casefold() for skill in expanded}
    for skill in skills:
        parts = str(skill).strip().split()
        if len(parts) < 2:
            continue
        alias = parts[-1]
        if not _is_skill_chip(alias):
            continue
        key = alias.casefold()
        if key in seen:
            continue
        seen.add(key)
        expanded.append(alias)
    return expanded


def jobbert_structured_for_scoring(structured: dict | None) -> dict | None:
    if not isinstance(structured, dict):
        return None

    flat_skills = _expand_skill_aliases(flatten_cv_skills_for_jobbert(structured))
    if not flat_skills:
        return structured

    view = dict(structured)
    view["skills"] = flat_skills
    view["skills_text"] = ", ".join(flat_skills)
    return view


def derive_semantic_groups(fact: str) -> list[list[str]]:
    """Build concise OR-groups from a confirmed fact for local semantic checks."""
    text = (fact or "").lower()
    words = re.findall(r"[a-z0-9]+", text)
    significant = [w for w in words if w not in _SEMANTIC_STOPWORDS and len(w) >= 4]

    groups: list[list[str]] = []
    i = 0
    while i < len(significant):
        if i + 1 < len(significant):
            w1, w2 = significant[i], significant[i + 1]
            bigram = f"{w1} {w2}"
            groups.append(list(dict.fromkeys([bigram, w1, w2])))
            i += 2
            continue
        groups.append([significant[i]])
        i += 1

    for anchor in ("experience", "experienced", "proficiency", "familiarity", "working"):
        if re.search(rf"\b{anchor}\b", text):
            groups.append([anchor, "experience"])

    deduped: list[list[str]] = []
    seen: set[tuple[str, ...]] = set()
    for group in groups:
        key = tuple(group)
        if key not in seen:
            seen.add(key)
            deduped.append(group)
    return deduped


def run_jobbert_match_score(
    resume_text: str,
    job_description: str,
    *,
    structured: dict | None = None,
    phase: str = "",
) -> dict | None:
    """JobBERT skill match (0–100). Used before/after tailor in the workflow."""
    resume_text = str(resume_text or "").strip()
    job_description = str(job_description or "").strip()
    label = phase or "result"

    if len(resume_text) < 40 or len(job_description) < 40:
        logger.info("JobBERT (%s) skipped: resume or JD too short", label)
        return None

    if compute_jobbert_skill_match is None:
        logger.warning("JobBERT (%s) unavailable: scoring module failed to import", label)
        return None

    parsed = structured if isinstance(structured, dict) else parse_original_resume_yaml(resume_text)
    plain_for_scoring = cv_yaml_to_jobbert_plain(parsed, resume_text)
    scoring_structured = jobbert_structured_for_scoring(parsed)

    try:
        result = compute_jobbert_skill_match(
            plain_for_scoring,
            job_description,
            structured=scoring_structured,
        )
    except Exception as exc:
        logger.warning("JobBERT (%s) failed: %s", label, exc)
        return None

    summary = {
        "match_score": result.get("match_score"),
        "skill_match_percent": result.get("skill_match_percent"),
        "matched_skills": result.get("matched_skills") or [],
        "unmatched_skills": result.get("unmatched_skills") or [],
        "comparison_summary": result.get("comparison_summary"),
        "scoring_method": result.get("scoring_method"),
        "resume_skills_used": result.get("resume_skills") or [],
    }
    logger.info(
        "JobBERT (%s):\n%s",
        label,
        yaml.safe_dump(summary, sort_keys=False, allow_unicode=True, width=120),
    )
    return result
