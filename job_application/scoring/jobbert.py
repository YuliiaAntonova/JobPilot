"""
JobBERT knowledge extraction + semantic skill matching (Untitled1_skillmatch_fixed.ipynb).

Scores resume vs JD by extracting knowledge entities from the JD requirements section
and matching them against resume entities (exact → lexical → MiniLM semantic).
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Any

from sklearn.metrics.pairwise import cosine_similarity

from job_application.config import (
    JOBBERT_KNOWLEDGE_MODEL,
    JOBBERT_MIN_ENTITY_SCORE,
    JOBBERT_SEMANTIC_THRESHOLD,
    MATCH_SCORE_MODEL,
)
SHORT_TECH_TERMS = {
    "sql",
    "aws",
    "gcp",
    "etl",
    "elt",
    "ml",
    "ai",
    "bi",
    "git",
    "api",
    "data",
}
# Missing-comma splits (Flask SQL) vs cloud prefixes (AWS Glue). Avoid «Power BI» → Power + BI.
SPLIT_LEADING_SKILL_TERMS = {"aws", "gcp", "azure"}
SPLIT_TRAILING_SKILL_TERMS = {"sql", "git", "api", "etl", "elt"}

# Slash compounds kept as one JD requirement (do not split into ETL + ELT).
PRESERVED_SLASH_SKILL_RE = re.compile(
    r"^(etl|ci)\s*/\s*(elt|cd)$",
    flags=re.IGNORECASE,
)

# NER noise — excluded from JobBERT score denominator (see also ATS suggestions).
SCORING_VAGUE_ENTITIES = frozenset(
    {
        "programming",
        "language",
        "modern",
        "data",
        "degree",
        "computer",
        "science",
        "engineering",
        "quality",
        "platforms",
        "processes",
        "management",
        "analytics",
        "integration",
        "performance",
        "storage",
        "processing",
        "continuous",
        "automated",
        "economics",
        "english",
        "german",
        "master",
        "technical",
        "university",
        "finance",
        "logistics",
        "manufacturing",
        "power",
        "too",
        "step",
        "fun",
        "reddit",
        # JD requirement-section fragments
        "models",
        "modeling",
        "analytical",
        "tables",
        "structures",
        "production",
        "monitoring",
        "testing",
        "databases",
        "warehouse",
        "pipeline",
    }
)


def extract_requirements_section(text: str) -> str:
    """Use explicit Skills & Requirements; cut Benefits / recruiter boilerplate."""
    match = re.search(
        r"skills\s*&\s*requirements(.*?)(?:benefits\s*/\s*other compensation|why hays\?|$)",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if match:
        return match.group(1).strip()

    parts = re.split(
        r"benefits\s*/\s*other compensation",
        text,
        maxsplit=1,
        flags=re.IGNORECASE,
    )
    return parts[0].strip()


def extract_from_long_text(text: str, model, *, chunk_size: int = 350, overlap: int = 40) -> list[dict]:
    """Run token-classification pipeline on text longer than 512 tokens."""
    tokenizer = model.tokenizer
    token_ids = tokenizer.encode(text, add_special_tokens=False)
    results: list[dict] = []
    step = chunk_size - overlap

    for start in range(0, len(token_ids), step):
        chunk_ids = token_ids[start : start + chunk_size]
        chunk_text = tokenizer.decode(chunk_ids, skip_special_tokens=True)
        results.extend(model(chunk_text))
        if start + chunk_size >= len(token_ids):
            break

    return results


def clean_technical_entities(items: list[dict], *, min_score: float | None = None) -> list[str]:
    """Clean JobBERT NER output: drop fragments, dedupe, remove nested noise."""
    threshold = JOBBERT_MIN_ENTITY_SCORE if min_score is None else min_score
    candidates: list[tuple[str, float]] = []

    for item in items:
        score = float(item.get("score", 0))
        text = str(item.get("word", "")).strip()

        if score < threshold:
            continue
        if text.startswith("##") or " ##" in text:
            continue
        if not re.search(r"[A-Za-z0-9]", text):
            continue

        text = re.sub(r"^[\s,;:()/\\|]+|[\s,;:()/\\|]+$", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) < 2:
            continue
        if (
            len(text.split()) == 1
            and text.islower()
            and len(text) <= 4
            and text.casefold() not in SHORT_TECH_TERMS
        ):
            continue

        candidates.append((text, score))

    unique: dict[str, tuple[str, float]] = {}
    for text, score in candidates:
        key = text.casefold()
        if key not in unique or score > unique[key][1]:
            unique[key] = (text, score)

    values = list(unique.values())
    cleaned: list[str] = []
    for text, score in values:
        norm = text.casefold()
        contained = False
        for other, other_score in values:
            if other == text:
                continue
            other_norm = other.casefold()
            if (
                len(other_norm) > len(norm)
                and norm in other_norm
                and len(norm) >= 5
                and other_score >= score - 0.05
            ):
                contained = True
                break
        if not contained:
            cleaned.append(text)

    return cleaned


def _strip_entity_punctuation(text: str) -> str:
    return re.sub(r"^[\s,;:()/\\|.]+|[\s,;:()/\\|.]+$", "", str(text or "").strip())


def is_scoring_vague_entity(name: str) -> bool:
    """Drop generic NER fragments from the score denominator."""
    norm = str(name or "").casefold().strip()
    if not norm:
        return True
    if norm in SCORING_VAGUE_ENTITIES:
        return True
    if re.search(r"\band$", norm):
        return True
    if " and " in norm and len(norm.split()) <= 4:
        return True
    if " " in norm:
        return False
    if norm in SHORT_TECH_TERMS:
        return False
    return len(norm) <= 4


def filter_scoring_job_entities(skills: list[str]) -> list[str]:
    return [skill for skill in skills if not is_scoring_vague_entity(skill)]


def _is_preserved_slash_compound(raw: str) -> bool:
    compact = re.sub(r"\s+", " ", str(raw or "").strip())
    return bool(PRESERVED_SLASH_SKILL_RE.match(compact))


def expand_compound_job_entities(skills: list[str]) -> list[str]:
    """
    Split merged JobBERT JD entities where safe: «AWS, Azure», «Git. Airflow».
    Keeps slash compounds «ETL / ELT», «CI / CD» as single requirements.
    """
    out: list[str] = []
    seen: set[str] = set()

    def add(raw: str) -> None:
        text = _strip_entity_punctuation(raw)
        if not text or len(text) < 2:
            return
        low = text.casefold()
        if low in {"and", "or", "with", "ie"}:
            return
        if re.search(r"\band$", low):
            return
        if low in seen:
            return
        seen.add(low)
        out.append(text)

    for skill in skills:
        raw = re.sub(r"^\s*or\s+", "", str(skill or "").strip(), flags=re.I)
        if not raw:
            continue

        if _is_preserved_slash_compound(raw):
            add(raw)
            continue

        if re.search(r"\.\s+[A-Za-z]", raw):
            parts = [_strip_entity_punctuation(p) for p in re.split(r"\.\s+", raw)]
            parts = [p for p in parts if p and len(p) >= 2]
            if len(parts) >= 2:
                for part in parts:
                    add(part)
                continue

        if "," in raw:
            parts = [_strip_entity_punctuation(p) for p in raw.split(",")]
            parts = [p for p in parts if p and len(p) >= 2]
            if len(parts) >= 2:
                for part in parts:
                    add(part)
                continue

        add(raw)

    return out


def refine_job_skills_for_scoring(skills: list[str]) -> list[str]:
    """Expand safe JD glue artifacts, then drop vague NER noise from scoring."""
    return filter_scoring_job_entities(expand_compound_job_entities(skills))


def normalize_skill(text: str) -> str:
    text = text.casefold().strip()
    text = text.replace("&", " and ")
    text = re.sub(r"[\s/_\-]+", " ", text)
    text = re.sub(r"[^a-z0-9+#. ]+", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def compact_skill(text: str) -> str:
    return re.sub(r"[^a-z0-9+#]", "", normalize_skill(text))


def expand_resume_skill_entities(resume_skills: list[str]) -> list[str]:
    """
    Split JobBERT artifacts from missing commas (e.g. «Flask SQL» → Flask + SQL).
    """
    expanded: list[str] = []
    seen: set[str] = set()

    def add(skill: str) -> None:
        text = skill.strip()
        if not text:
            return
        key = text.casefold()
        if key in seen:
            return
        seen.add(key)
        expanded.append(text)

    for skill in resume_skills:
        tokens = skill.split()
        if len(tokens) == 2:
            first = tokens[0].casefold()
            second = tokens[1].casefold()
            if first in SPLIT_LEADING_SKILL_TERMS:
                add(tokens[0])
                add(tokens[1])
                continue
            if second in SPLIT_TRAILING_SKILL_TERMS and first not in SPLIT_LEADING_SKILL_TERMS:
                add(tokens[0])
                add(tokens[1])
                continue
        add(skill)

    return expanded


def match_skills(
    job_skills: list[str],
    resume_skills: list[str],
    *,
    semantic_threshold: float | None = None,
) -> tuple[float, list[dict[str, Any]], list[dict[str, Any]]]:
    """Conservative exact → lexical → semantic skill matching."""
    threshold = JOBBERT_SEMANTIC_THRESHOLD if semantic_threshold is None else semantic_threshold

    if not job_skills:
        return 0.0, [], []

    if not resume_skills:
        return 0.0, [], [
            {
                "required_skill": skill,
                "best_candidate": None,
                "similarity": 0.0,
                "match_type": "missing",
            }
            for skill in job_skills
        ]

    resume_norm = [normalize_skill(x) for x in resume_skills]
    resume_compact = [compact_skill(x) for x in resume_skills]
    matched: list[dict[str, Any]] = []
    unresolved: list[str] = []

    for job_skill in job_skills:
        j_norm = normalize_skill(job_skill)
        j_compact = compact_skill(job_skill)

        exact_idx = next((i for i, r in enumerate(resume_norm) if r == j_norm), None)
        if exact_idx is not None:
            matched.append(
                {
                    "required_skill": job_skill,
                    "resume_skill": resume_skills[exact_idx],
                    "similarity": 1.0,
                    "match_type": "exact",
                }
            )
            continue

        compact_idx = next(
            (i for i, r in enumerate(resume_compact) if j_compact and r == j_compact),
            None,
        )
        if compact_idx is not None:
            matched.append(
                {
                    "required_skill": job_skill,
                    "resume_skill": resume_skills[compact_idx],
                    "similarity": 0.98,
                    "match_type": "normalized",
                }
            )
            continue

        token_idx = None
        if len(j_norm.split()) == 1:
            for i, r_norm in enumerate(resume_norm):
                r_tokens = r_norm.split()
                if len(r_tokens) == 1 and j_norm == r_tokens[0]:
                    token_idx = i
                    break
                if j_norm in SHORT_TECH_TERMS and j_norm in r_tokens:
                    token_idx = i
                    break

        if token_idx is not None:
            matched.append(
                {
                    "required_skill": job_skill,
                    "resume_skill": resume_skills[token_idx],
                    "similarity": 0.95,
                    "match_type": "token",
                }
            )
            continue

        containment_idx = None
        containment_score = 0.0
        if len(j_compact) >= 4:
            for i, r_compact in enumerate(resume_compact):
                if len(r_compact) < 4:
                    continue
                shorter = min(len(j_compact), len(r_compact))
                longer = max(len(j_compact), len(r_compact))
                ratio = shorter / longer
                if ratio >= 0.60 and (j_compact in r_compact or r_compact in j_compact):
                    if ratio > containment_score:
                        containment_idx = i
                        containment_score = ratio

        if containment_idx is not None:
            matched.append(
                {
                    "required_skill": job_skill,
                    "resume_skill": resume_skills[containment_idx],
                    "similarity": containment_score,
                    "match_type": "lexical",
                }
            )
            continue

        unresolved.append(job_skill)

    missing: list[dict[str, Any]] = []
    if unresolved:
        embedder = _embedding_model()
        job_embeddings = embedder.encode(unresolved, normalize_embeddings=True)
        resume_embeddings = embedder.encode(resume_skills, normalize_embeddings=True)
        similarity_matrix = cosine_similarity(job_embeddings, resume_embeddings)

        for i, job_skill in enumerate(unresolved):
            best_idx = int(similarity_matrix[i].argmax())
            best_score = float(similarity_matrix[i][best_idx])
            best_resume_skill = resume_skills[best_idx]
            if best_score >= threshold:
                matched.append(
                    {
                        "required_skill": job_skill,
                        "resume_skill": best_resume_skill,
                        "similarity": best_score,
                        "match_type": "semantic",
                    }
                )
            else:
                missing.append(
                    {
                        "required_skill": job_skill,
                        "best_candidate": best_resume_skill,
                        "similarity": best_score,
                        "match_type": "missing",
                    }
                )

    match_percent = len(matched) / len(job_skills) * 100
    return match_percent, matched, missing


@lru_cache(maxsize=1)
def _knowledge_model():
    from transformers import pipeline

    return pipeline(
        "token-classification",
        model=JOBBERT_KNOWLEDGE_MODEL,
        aggregation_strategy="simple",
    )


@lru_cache(maxsize=1)
def _embedding_model():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(MATCH_SCORE_MODEL)


def warmup_jobbert_models() -> None:
    """Preload JobBERT + embedding model on app startup."""
    import logging

    log = logging.getLogger(__name__)
    try:
        _knowledge_model()
        _embedding_model()
        log.info("JobBERT models warmed up")
    except Exception:
        log.exception("JobBERT warmup failed (scoring will retry on first use)")


def _merge_resume_skills_for_scoring(
    resume_text: str,
    resume_skills: list[str],
    job_skills: list[str],
) -> list[str]:
    """Merge structured skills with chips from full plain resume (after AI tailoring)."""
    from job_application.resume.profile_text import skills_from_plain_resume_text

    seen = {s.casefold() for s in resume_skills}
    merged = list(resume_skills)
    for skill in expand_resume_skill_entities(skills_from_plain_resume_text(resume_text)):
        key = skill.casefold()
        if key not in seen:
            seen.add(key)
            merged.append(skill)
    return supplement_resume_entities_with_literal_phrases(resume_text, job_skills, merged)


def supplement_resume_entities_with_literal_phrases(
    resume_text: str,
    job_skills: list[str],
    resume_skills: list[str],
) -> list[str]:
    """
    JobBERT иногда не выделяет фразу целиком (напр. «data pipelines»),
    хотя она дословно есть в тексте резюме. Добавляем такие multi-word entities.
    """
    augmented = list(resume_skills)
    seen = {s.casefold() for s in resume_skills}
    resume_low = (resume_text or "").casefold()

    for skill in job_skills:
        phrase = str(skill or "").strip()
        if len(phrase.split()) < 2:
            continue
        key = phrase.casefold()
        if key in seen:
            continue
        if key in resume_low:
            augmented.append(phrase)
            seen.add(key)

    return augmented


def extract_job_skills_from_jd(jd_text: str) -> tuple[list[str], str]:
    """Extract required skills/knowledge from JD (requirements section only)."""
    jd = (jd_text or "").strip()
    if not jd:
        return [], ""

    requirements_text = extract_requirements_section(jd)
    if not requirements_text.strip():
        requirements_text = jd

    raw = extract_from_long_text(requirements_text, _knowledge_model())
    skills = refine_job_skills_for_scoring(clean_technical_entities(raw))
    return skills, requirements_text


def compute_jobbert_skill_match(
    resume_text: str,
    jd_text: str,
    *,
    structured: dict | None = None,
    semantic_threshold: float | None = None,
) -> dict[str, Any]:
    resume = (resume_text or "").strip()
    jd = (jd_text or "").strip()
    if not resume or not jd:
        raise ValueError("resume_text and jd_text are required for JobBERT scoring")

    from job_application.resume.profile_text import (
        extract_skills_text_for_jobbert,
        structured_skills_list,
    )

    job_skills, requirements_text = extract_job_skills_from_jd(jd)
    resume_entities_text, resume_entities_source = extract_skills_text_for_jobbert(
        resume,
        structured,
    )
    structured_skills = structured_skills_list(structured)
    if structured_skills:
        resume_skills = expand_resume_skill_entities(structured_skills)
    else:
        resume_raw = extract_from_long_text(resume_entities_text, _knowledge_model())
        resume_skills = clean_technical_entities(resume_raw)
        resume_skills = expand_resume_skill_entities(resume_skills)
    # Literal JD phrases (e.g. «data pipelines») may live in experience bullets, not SKILLS JSON.
    resume_skills = _merge_resume_skills_for_scoring(resume, resume_skills, job_skills)

    skill_match_percent, matched, missing = match_skills(
        job_skills,
        resume_skills,
        semantic_threshold=semantic_threshold,
    )

    score_int = max(0, min(100, int(round(skill_match_percent))))
    matched_names = [item["required_skill"] for item in matched]
    unmatched_names = [item["required_skill"] for item in missing]

    if job_skills:
        summary = (
            f"JobBERT skill match {score_int}% "
            f"({len(matched)}/{len(job_skills)} required knowledge entities). "
            f"Matched: {', '.join(matched_names) or '—'}. "
            f"Missing: {', '.join(unmatched_names) or '—'}."
        )
    else:
        summary = (
            "JobBERT: no knowledge entities extracted from the JD requirements section. "
            "Score is 0%."
        )

    return {
        "match_score": score_int,
        "skill_match_percent": round(skill_match_percent, 2),
        "comparison_summary": summary,
        "scoring_method": "jobbert_knowledge",
        "skills_source": "jobbert_requirements_section",
        "skills_available": bool(job_skills),
        "requirements_text": requirements_text,
        "resume_entities_text": resume_entities_text,
        "resume_entities_source": resume_entities_source,
        "required_skills": job_skills,
        "resume_skills": resume_skills,
        "matched_skills": matched_names,
        "unmatched_skills": unmatched_names,
        "matched_details": matched,
        "missing_details": missing,
        "skill_score": round(skill_match_percent / 100.0, 4),
    }
