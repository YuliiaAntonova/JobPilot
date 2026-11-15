"""ATS suggestions from JobBERT entity match (Untitled_skillmatch.ipynb)."""

from __future__ import annotations

import re
from typing import Any

from job_application.config import JOBBERT_SEMANTIC_THRESHOLD, PHRASE_DISCOVERY_THRESHOLD
from job_application.scoring.jobbert import is_scoring_vague_entity

_PLATFORM_JD_HINTS = ("platform",)
_STORAGE_RESUME_HINTS = (
    "storage",
    "querying",
    "query",
    "opensearch",
    "aurora",
    "warehouse",
    "lakehouse",
    "datalake",
    "database",
)

def _count_substantive_lines(text: str) -> int:
    count = 0
    for line in (text or "").splitlines():
        cleaned = re.sub(r"^[\*•●\-–—\d\.\)]\s*", "", line.strip())
        if len(cleaned) >= 12:
            count += 1
    return count


def _is_vague_entity(name: str) -> bool:
    return is_scoring_vague_entity(name)


def build_ats_suggestions(
    resume_text: str,
    requirements_text: str,
    matched_details: list[dict[str, Any]],
    missing_details: list[dict[str, Any]],
    *,
    max_items: int = 10,
    near_miss_threshold: float | None = None,
) -> dict[str, Any]:
    """
    Пары строго из вывода match_skills(job_all_skills, resume_all_skills):

    - matched (не exact): resume entity → required entity
    - missing: resume best_candidate entity → required entity (similarity >= threshold)

    Без поиска строк резюме / абзацев JD — только списки entities из JobBERT.
    """
    threshold = JOBBERT_SEMANTIC_THRESHOLD if near_miss_threshold is None else near_miss_threshold
    # Near-miss для UI чуть ниже порога semantic match (0.73 для data pipelines).
    suggest_threshold = min(threshold, 0.72)

    suggestions: list[dict[str, Any]] = []
    seen_pairs: set[tuple[str, str]] = set()
    req_text = (requirements_text or "").strip()
    resume = (resume_text or "").strip()

    def add(
        resume_entity: str,
        required_entity: str,
        *,
        match_type: str,
        similarity: float,
    ) -> None:
        rp = str(resume_entity or "").strip()
        jp = str(required_entity or "").strip()
        if not rp or not jp:
            return
        if rp.casefold() == jp.casefold():
            return
        pair_key = (rp.casefold(), jp.casefold())
        if pair_key in seen_pairs:
            return
        seen_pairs.add(pair_key)
        suggestions.append(
            {
                "resume_phrase": rp,
                "jd_phrase": jp,
                "match_type": match_type,
                "similarity": round(similarity, 4),
            }
        )

    for item in matched_details:
        match_type = str(item.get("match_type") or "")
        if match_type == "exact":
            continue
        required = str(item.get("required_skill") or "").strip()
        resume_skill = str(item.get("resume_skill") or "").strip()
        similarity = float(item.get("similarity") or 0.0)
        if not required or not resume_skill:
            continue
        if required.casefold() == resume_skill.casefold():
            continue
        if _is_vague_entity(required) and match_type not in {"token", "normalized", "lexical"}:
            continue
        add(resume_skill, required, match_type=match_type, similarity=similarity)

    for item in missing_details:
        required = str(item.get("required_skill") or "").strip()
        best = str(item.get("best_candidate") or "").strip()
        similarity = float(item.get("similarity") or 0.0)
        if not required or not best:
            continue
        if similarity < suggest_threshold:
            continue
        if _is_vague_entity(required) or _is_vague_entity(best):
            continue
        add(best, required, match_type="near_miss", similarity=similarity)

    suggestions.sort(key=lambda row: (-float(row.get("similarity") or 0), row["resume_phrase"]))

    return {
        "jd_phrase_count": _count_substantive_lines(req_text),
        "resume_phrase_count": _count_substantive_lines(resume),
        "threshold": suggest_threshold,
        "suggestions": suggestions[:max_items],
    }


def _normalize_phrase_token(token: str) -> str:
    return re.sub(r"[.,;!?]+$", "", str(token or "").strip())


def _flexible_entity_pattern(resume_entity: str) -> re.Pattern[str]:
    """
    JobBERT entity «Flask SQL» в PDF часто разбита: «Flask\\nSQL (DML)».
    Собираем токены entity через гибкий разделитель (пробел, перенос, запятая).
    """
    tokens = [_normalize_phrase_token(t) for t in re.split(r"[\s/]+", resume_entity.strip()) if t]
    if not tokens:
        return re.compile(re.escape(resume_entity.strip()), flags=re.IGNORECASE)
    if len(tokens) <= 1:
        return re.compile(rf"\b{re.escape(tokens[0])}\b[.,;!?]*", flags=re.IGNORECASE)
    inner = r"[\s,;·\-\n]+".join(re.escape(token) for token in tokens)
    return re.compile(rf"\b{inner}(\s*\([^)]*\))?[.,;!?]*", flags=re.IGNORECASE)


def _line_span(text: str, start: int, end: int) -> tuple[int, int]:
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", end)
    if line_end == -1:
        line_end = len(text)
    return line_start, line_end


def _should_apply_substitution(
    text: str,
    start: int,
    end: int,
    src: str,
    dst: str,
) -> bool:
    """Avoid prefix overlap (modern + data pipelines → modern modern…)."""
    dst_cf = dst.casefold()
    src_cf = src.casefold()
    if src_cf in dst_cf:
        prefix = dst_cf[: dst_cf.index(src_cf)].strip()
        if prefix:
            before = text[max(0, start - len(prefix) - 3) : start].casefold()
            if before.endswith(prefix):
                return False
    return True


def _remove_token_span(text: str, start: int, end: int) -> str:
    """Remove matched token and one adjacent chip separator (avoid merging neighbors)."""
    left, right = start, end
    probe = left
    while probe > 0 and text[probe - 1] in " \t":
        probe -= 1
    if probe > 0 and text[probe - 1] in "·,;|":
        left = probe - 1
        while left > 0 and text[left - 1] == " ":
            left -= 1
    else:
        while right < len(text) and text[right] in " \t":
            right += 1
        if right < len(text) and text[right] in "·,;|":
            right += 1
            while right < len(text) and text[right] == " ":
                right += 1
    return text[:left] + text[right:]


def _is_composite_token_replacement(src: str, dst: str, match_type: str) -> bool:
    """Flask SQL → SQL: dst is one token inside multi-word src."""
    if match_type != "token" or " " not in src.strip():
        return False
    dst_cf = dst.casefold()
    return any(t.casefold() == dst_cf for t in re.split(r"[\s/]+", src) if t)


def _should_remove_duplicate_token(line: str, src: str, dst: str, match_type: str) -> bool:
    """Drop src chip when JD term already on the line (Postgres + PostgreSQL)."""
    if " " in src.strip() or match_type.startswith("phrase_"):
        return False
    line_cf = line.casefold()
    dst_cf = dst.casefold()
    src_cf = src.casefold()
    return dst_cf in line_cf and src_cf != dst_cf


def _apply_substitution_on_match(
    text: str,
    match: re.Match[str],
    src: str,
    dst: str,
    *,
    match_type: str = "",
) -> str:
    line_start, line_end = _line_span(text, match.start(), match.end())
    line = text[line_start:line_end]
    composite = _is_composite_token_replacement(src, dst, match_type)
    if not composite and _should_remove_duplicate_token(line, src, dst, match_type):
        return _remove_token_span(text, match.start(), match.end())
    line_cf = line.casefold()
    dst_cf = dst.casefold()
    src_cf = src.casefold()
    if not composite and dst_cf in line_cf and src_cf != dst_cf:
        return text
    if not _should_apply_substitution(text, match.start(), match.end(), src, dst):
        return text
    return _apply_match(text, match, dst)


def _apply_all_for_pattern(
    text: str,
    pattern: re.Pattern[str],
    src: str,
    dst: str,
    *,
    match_type: str = "",
) -> str:
    out = text
    while True:
        changed = False
        for match in pattern.finditer(out):
            new_out = _apply_substitution_on_match(out, match, src, dst, match_type=match_type)
            if new_out != out:
                out = new_out
                changed = True
                break
        if not changed:
            break
    return out


_SKILL_LINE_RE = re.compile(
    r"^(\s*(?:technical skills|technologies|skills|tools)\s*:\s*)(.+)$",
    re.IGNORECASE | re.MULTILINE,
)
_CHIP_SPLIT_RE = re.compile(r"\s*[·,;|]\s*")
_SKILL_SYNONYM_DISPLAY: dict[str, str] = {
    "postgres": "PostgreSQL",
    "postgresql": "PostgreSQL",
    "psql": "PostgreSQL",
}


def _dedupe_skill_tokens(parts: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for part in parts:
        raw = part.strip()
        if not raw:
            continue
        norm = _normalize_phrase_token(raw).casefold()
        display = _SKILL_SYNONYM_DISPLAY.get(norm, raw)
        key = _SKILL_SYNONYM_DISPLAY.get(norm, norm).casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(display)
    return out


def _dedupe_skill_chip_lines(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        prefix, body = match.group(1), match.group(2)
        parts = [p.strip() for p in _CHIP_SPLIT_RE.split(body) if p.strip()]
        return prefix + " · ".join(_dedupe_skill_tokens(parts))

    return _SKILL_LINE_RE.sub(repl, text)


def _apply_match(text: str, match: re.Match[str], dst: str) -> str:
    suffix = (match.group(1) or "") if match.lastindex else ""
    return text[: match.start()] + dst + suffix + text[match.end() :]


_ORCHESTRATE_GLUE_RE = re.compile(r"orchestrat\w*\s+glue\s+jobs?", re.IGNORECASE)


def _is_destructive_substitution(src: str, dst: str) -> bool:
    """Block ATS pairs that truncate full duty lines into noisy JD fragments."""
    src_s = str(src or "").strip()
    dst_s = str(dst or "").strip()
    dst_cf = dst_s.casefold()
    if "orchestration tools" in dst_cf and "glue" not in dst_cf:
        if _ORCHESTRATE_GLUE_RE.search(src_s):
            return False
        return True
    # Only guard long duty-line replacements, not short phrase pairs (storage → platforms).
    if len(src_s) >= 48 and len(dst_s) < len(src_s) * 0.55:
        return True
    return False


def resolve_safe_ats_pair(src: str, dst: str) -> tuple[str, str] | None:
    """
    Expand ATS pairs that would drop Glue context into a readable JD rewrite.
    E.g. orchestrate Glue Jobs and automate → use orchestration tools for Glue Jobs and automate.
    """
    src_s = str(src or "").strip()
    dst_s = str(dst or "").strip()
    if not src_s or not dst_s or src_s.casefold() == dst_s.casefold():
        return None

    src_cf = src_s.casefold()
    dst_cf = dst_s.casefold()
    if "orchestration tools" in dst_cf and _ORCHESTRATE_GLUE_RE.search(src_s):
        safe_dst = _ORCHESTRATE_GLUE_RE.sub("use orchestration tools for Glue Jobs", src_s, count=1)
        if safe_dst.casefold() != src_cf:
            return src_s, safe_dst

    if _is_destructive_substitution(src_s, dst_s):
        return None
    return src_s, dst_s


def _apply_one_entity_substitution(text: str, item: dict[str, Any]) -> str:
    src = str(item.get("resume_phrase") or "").strip()
    dst = str(item.get("jd_phrase") or "").strip()
    match_type = str(item.get("match_type") or "")
    if not src or not dst or src.casefold() == dst.casefold():
        return text
    resolved = resolve_safe_ats_pair(src, dst)
    if resolved is None:
        return text
    src, dst = resolved

    out = _apply_all_for_pattern(text, _flexible_entity_pattern(src), src, dst, match_type=match_type)
    if out != text:
        return out

    if match_type == "token" and " " not in dst:
        src_tokens = [t for t in re.split(r"[\s/]+", src) if t]
        dst_cf = dst.casefold()
        if any(t.casefold() == dst_cf for t in src_tokens):
            prefix = [t for t in src_tokens if t.casefold() != dst_cf]
            if prefix:
                prefix_pat = r"[\s,;·\-\n]+".join(re.escape(token) for token in prefix)
                token_pat = re.compile(
                    rf"\b{prefix_pat}[\s,;·\-\n]+{re.escape(dst)}(\s*\([^)]*\))?",
                    flags=re.IGNORECASE,
                )
                out = _apply_all_for_pattern(text, token_pat, src, dst, match_type=match_type)
                if out != text:
                    return out

    exact = re.compile(re.escape(src), flags=re.IGNORECASE)
    out = _apply_all_for_pattern(text, exact, src, dst, match_type=match_type)
    if out != text:
        return out

    if match_type.startswith("phrase_"):
        core = re.sub(r"[.,;!?]+$", "", src).strip()
        if core:
            loose = re.compile(re.escape(core) + r"[.,;!?]*", flags=re.IGNORECASE)
            out = _apply_all_for_pattern(text, loose, src, dst, match_type=match_type)
            if out != text:
                return out
    return text


def is_boosted_phrase_substitution(
    resume_phrase: str,
    jd_phrase: str,
    similarity: float,
    *,
    discovery_threshold: float | None = None,
) -> bool:
    """
    Low embedding score but clear infra overlap (e.g. storage/querying → platforms).
    """
    th = PHRASE_DISCOVERY_THRESHOLD if discovery_threshold is None else discovery_threshold
    if float(similarity) < th:
        return False
    jp = str(jd_phrase or "").casefold()
    rp = str(resume_phrase or "").casefold()
    if not jp or not rp:
        return False
    if not any(h in jp for h in _PLATFORM_JD_HINTS):
        return False
    return any(h in rp for h in _STORAGE_RESUME_HINTS)


def filter_confident_ats_suggestions(
    suggestions: list[dict[str, Any]],
    *,
    min_phrase_sim: float = 0.65,
    phrase_discovery_threshold: float | None = None,
) -> list[dict[str, Any]]:
    """Diff/preview: phrase pairs when sim >= min_phrase_sim or boosted lexical match."""
    discovery_th = PHRASE_DISCOVERY_THRESHOLD if phrase_discovery_threshold is None else phrase_discovery_threshold
    out: list[dict[str, Any]] = []
    for item in suggestions:
        match_type = str(item.get("match_type") or "")
        sim = float(item.get("similarity") or 0.0)
        if match_type.startswith("phrase_") and sim < min_phrase_sim:
            rp = str(item.get("resume_phrase") or "")
            jp = str(item.get("jd_phrase") or "")
            if not is_boosted_phrase_substitution(rp, jp, sim, discovery_threshold=discovery_th):
                continue
            boosted = dict(item)
            boosted["phrase_confidence"] = "lexical_boost"
            out.append(boosted)
            continue
        out.append(item)
    return out


def merge_ats_suggestions(*groups: list[dict[str, Any]], max_items: int = 12) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for group in groups:
        for item in group:
            rp = str(item.get("resume_phrase") or "").strip()
            jp = str(item.get("jd_phrase") or "").strip()
            if not rp or not jp:
                continue
            key = (rp.casefold(), jp.casefold())
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
    merged.sort(
        key=lambda row: (
            0 if str(row.get("match_type") or "").startswith(("phrase_", "expression_")) else 1,
            -len(str(row.get("resume_phrase") or "")),
            -float(row.get("similarity") or 0),
        )
    )
    return merged[:max_items]


def apply_ats_entity_substitutions(text: str, suggestions: list[dict[str, Any]]) -> str:
    """Заменяет resume entity на JD entity в тексте (длинные сущности первыми)."""
    if not text or not suggestions:
        return text

    ordered = sorted(
        suggestions,
        key=lambda item: len(str(item.get("resume_phrase") or "")),
        reverse=True,
    )
    out = text
    for item in ordered:
        out = _apply_one_entity_substitution(out, item)
    return _dedupe_skill_chip_lines(out)


def apply_substitutions_to_structured(
    structured: dict[str, Any],
    suggestions: list[dict[str, Any]],
) -> dict[str, Any]:
    """Apply ATS substitutions to all string fields in structured JSON (PDF/DOCX render)."""

    def transform(value: Any, *, in_structured_root: bool = False) -> Any:
        if isinstance(value, str) and value.strip():
            return apply_ats_entity_substitutions(value, suggestions)
        if isinstance(value, list):
            return [transform(item) for item in value]
        if isinstance(value, dict):
            out: dict[str, Any] = {}
            for key, item in value.items():
                if in_structured_root and str(key).startswith("_"):
                    out[key] = item
                    continue
                out[key] = transform(item)
            return out
        return value

    if not isinstance(structured, dict) or not structured or not suggestions:
        return structured
    return transform(dict(structured), in_structured_root=True)
