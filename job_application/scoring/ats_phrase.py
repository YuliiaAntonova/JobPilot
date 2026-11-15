"""Phrase-level ATS via SentenceTransformer semantic_search (L4 notebook logic)."""

from __future__ import annotations

import re
from typing import Any

from job_application.config import PHRASE_DISCOVERY_THRESHOLD, RESUME_PLAIN_TEXT_KEY
from job_application.scoring.ats import _is_vague_entity
from job_application.scoring.jobbert import _embedding_model

_BULLET_PREFIX = re.compile(r"^[\*•●\-–—\d\.\)]\s*")
_PHRASE_EDGE_STOP = frozenset({"and", "or", "for", "with", "the", "a", "an", "on", "in", "to", "of", "at", "by", "as"})
def resume_text_for_phrase_ats(resume_text: str, structured: dict | None = None) -> str:
    """
    Phrase bank needs experience bullets, not only the SKILLS block.
    Merge explicit resume_text with stored PDF plain text and structured highlights.
    """
    parts: list[str] = []
    seen_lines: set[str] = set()

    def add_block(block: str) -> None:
        for raw in (block or "").splitlines():
            line = re.sub(r"\s+", " ", str(raw or "").strip())
            if not line:
                continue
            key = line.casefold()
            if key in seen_lines:
                continue
            seen_lines.add(key)
            parts.append(line)

    add_block(resume_text)
    data = structured if isinstance(structured, dict) else {}
    add_block(str(data.get(RESUME_PLAIN_TEXT_KEY) or ""))
    for job in data.get("experience") or []:
        if not isinstance(job, dict):
            continue
        for field in ("highlights", "bullets", "responsibilities", "summary"):
            raw = job.get(field)
            if isinstance(raw, list):
                for item in raw:
                    add_block(str(item))
            elif isinstance(raw, str):
                add_block(raw)
    return "\n".join(parts)


def _pick_phrase_semantic_hit(
    jd_phrase: str,
    hit_list: list[dict[str, Any]],
    resume_phrases: list[str],
    *,
    phrase_threshold: float,
) -> tuple[dict[str, Any] | None, float, str]:
    valid = [h for h in hit_list if float(h["score"]) >= phrase_threshold]
    if not valid:
        return None, 0.0, ""

    def choose(pool: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, float, str]:
        ordered = sorted(
            pool,
            key=lambda h: (
                -float(h["score"]),
                len(resume_phrases[int(h["corpus_id"])].split()),
            ),
        )
        for hit in ordered:
            resume_phrase = resume_phrases[int(hit["corpus_id"])]
            if resume_phrase.casefold() == jd_phrase.casefold():
                continue
            if jd_phrase.casefold() in resume_phrase.casefold():
                continue
            return hit, float(hit["score"]), resume_phrase
        return None, 0.0, ""

    best_score = float(valid[0]["score"])
    near = [h for h in valid if float(h["score"]) >= best_score - 0.02]
    hit, score, resume_phrase = choose(near)
    if hit is None:
        hit, score, resume_phrase = choose(valid)
    return hit, score, resume_phrase


def extract_resume_phrases(text: str, structured: dict | None = None) -> list[str]:
    """Bullets / skill lines from full resume — candidates for phrase-level substitution."""
    seen: set[str] = set()
    out: list[str] = []

    def add(raw: str) -> None:
        phrase = re.sub(r"\s+", " ", str(raw or "").strip())
        if len(phrase) < 20 or len(phrase) > 240:
            return
        key = phrase.casefold()
        if key in seen:
            return
        seen.add(key)
        out.append(phrase)

    skip_headers = {"languages", "skills", "experience", "education", "contact", "objective"}
    for raw in (text or "").splitlines():
        line = _BULLET_PREFIX.sub("", raw.strip())
        if not line:
            continue
        low = line.casefold()
        if low in skip_headers:
            continue
        if " - " in line and len(line) < 55 and any(x in low for x in ("english", "german", "ukrainian", "russian")):
            continue
        if line.endswith((".", ";")) or "→" in line:
            add(line)
        elif line.startswith(
            (
                "Hands-on",
                "Tools:",
                "Experience with",
                "Implemented",
                "Developed",
                "Built ",
                "Manage ",
                "Work with",
                "Monitoring",
                "Wrote ",
            )
        ):
            add(line)
        elif "," in line and len(line) > 28:
            add(line)

    data = structured if isinstance(structured, dict) else {}
    for job in data.get("experience") or []:
        if not isinstance(job, dict):
            continue
        for field in ("highlights", "bullets", "responsibilities"):
            values = job.get(field)
            if isinstance(values, list):
                for item in values:
                    add(str(item))
    return out


def _is_valid_multiword_phrase(phrase: str, *, min_words: int = 2, max_words: int = 6) -> bool:
    text = re.sub(r"\s+", " ", str(phrase or "").strip())
    words = text.split()
    if len(words) < min_words or len(words) > max_words:
        return False
    if words[0].casefold() in _PHRASE_EDGE_STOP or words[-1].casefold() in _PHRASE_EDGE_STOP:
        return False
    content = [w for w in words if w.casefold() not in _PHRASE_EDGE_STOP]
    return len(content) >= 2


def extract_jd_phrase_targets(
    requirements_text: str,
    missing_details: list[dict[str, Any]],
    matched_details: list[dict[str, Any]],
    required_skills: list[str] | None = None,
) -> list[str]:
    """Whole JD phrases (≥2 words): JobBERT entities + patterns from requirements text."""
    seen: set[str] = set()
    out: list[str] = []

    def add(raw: str) -> None:
        text = re.sub(r"\s+", " ", str(raw or "").strip())
        if not _is_valid_multiword_phrase(text):
            return
        key = text.casefold()
        if key in seen:
            return
        seen.add(key)
        out.append(text)

    pool = list(required_skills or [])
    for item in list(missing_details) + list(matched_details):
        ent = str(item.get("required_skill") or "").strip()
        if ent:
            pool.append(ent)

    req_cf = (requirements_text or "").casefold()
    for ent in sorted(set(pool), key=len, reverse=True):
        if _is_vague_entity(ent) and " " not in ent:
            continue
        if ent.casefold() in req_cf:
            add(ent)

    for pattern in (
        r"modern data pipelines",
        r"data pipelines",
        r"data modeling",
        r"best practices",
        r"programming language",
        r"sql skills",
        r"data platforms",
    ):
        match = re.search(pattern, req_cf, flags=re.IGNORECASE)
        if match:
            add(requirements_text[match.start() : match.end()])

    return out


def extract_resume_phrase_targets(
    resume_text: str,
    resume_skills: list[str] | None = None,
    structured: dict | None = None,
) -> list[str]:
    """Whole resume phrases literally present in text (no noisy n-grams)."""
    text = resume_text or ""
    text_cf = text.casefold()
    seen: set[str] = set()
    out: list[str] = []

    def add(raw: str) -> None:
        phrase = re.sub(r"\s+", " ", str(raw or "").strip())
        if not _is_valid_multiword_phrase(phrase):
            return
        if phrase.casefold() not in text_cf:
            return
        key = phrase.casefold()
        if key in seen:
            return
        seen.add(key)
        out.append(phrase)

    for skill in resume_skills or []:
        add(str(skill))

    token_re = re.compile(r"[A-Za-z0-9+#\.]+")
    tokens = token_re.findall(text)
    for n in range(2, 6):
        for i in range(len(tokens) - n + 1):
            add(" ".join(tokens[i : i + n]))

    for bullet in extract_resume_phrases(text, structured):
        add(bullet)

    out.sort(key=len, reverse=True)
    pruned: list[str] = []
    for phrase in out:
        if any(phrase.casefold() != kept.casefold() and phrase.casefold() in kept.casefold() for kept in pruned):
            continue
        pruned.append(phrase)
    return pruned


def build_phrase_ats_suggestions(
    resume_text: str,
    requirements_text: str,
    missing_details: list[dict[str, Any]],
    matched_details: list[dict[str, Any]] | None = None,
    structured: dict | None = None,
    resume_skills: list[str] | None = None,
    required_skills: list[str] | None = None,
    *,
    phrase_threshold: float | None = None,
    max_items: int = 12,
) -> list[dict[str, Any]]:
    """
    SentenceTransformer util.semantic_search between whole phrase lists.
    Substitution is phrase→phrase (not bullet→sentence).
    """
    from sentence_transformers import util

    discovery_th = PHRASE_DISCOVERY_THRESHOLD if phrase_threshold is None else phrase_threshold
    matched_details = matched_details or []
    phrase_resume_text = resume_text_for_phrase_ats(resume_text, structured)
    jd_phrases = extract_jd_phrase_targets(
        requirements_text, missing_details, matched_details, required_skills
    )
    resume_phrases = extract_resume_phrase_targets(phrase_resume_text, resume_skills, structured)
    if not jd_phrases or not resume_phrases:
        return []

    embedder = _embedding_model()
    jd_emb = embedder.encode(jd_phrases, convert_to_tensor=True, normalize_embeddings=True)
    res_emb = embedder.encode(resume_phrases, convert_to_tensor=True, normalize_embeddings=True)
    hits = util.semantic_search(jd_emb, res_emb, top_k=8, score_function=util.cos_sim)

    bullets = extract_resume_phrases(phrase_resume_text, structured)
    suggestions: list[dict[str, Any]] = []
    used_pairs: set[tuple[str, str]] = set()

    for i, hit_list in enumerate(hits):
        if not hit_list:
            continue
        jd_phrase = jd_phrases[i]
        hit, score, resume_phrase = _pick_phrase_semantic_hit(
            jd_phrase,
            hit_list,
            resume_phrases,
            phrase_threshold=discovery_th,
        )
        if hit is None or not resume_phrase:
            continue
        pair_key = (resume_phrase.casefold(), jd_phrase.casefold())
        if pair_key in used_pairs:
            continue
        used_pairs.add(pair_key)

        context = next(
            (b for b in bullets if resume_phrase.casefold() in b.casefold()),
            resume_phrase,
        )
        suggestions.append(
            {
                "resume_phrase": resume_phrase,
                "jd_phrase": jd_phrase,
                "jd_entity": jd_phrase,
                "context_resume": context,
                "match_type": "phrase_semantic",
                "similarity": round(score, 4),
            }
        )

    suggestions.sort(key=lambda row: (-float(row.get("similarity") or 0), -len(row.get("resume_phrase") or "")))
    return suggestions[:max_items]
