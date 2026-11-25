"""Skills extraction, categorization, and chat field helpers."""

from __future__ import annotations

import json
import re

from job_application.resume.cv_constants import (
    IMPROVEMENTS_NO_MEASURABLE_ANSWER,
    RESULT_NO_MEASURABLE_ANSWER_LEGACY,
)
from job_application.config import DESIRED_ROLE_MAX_LEN

from job_application.resume.profile_text import experience as _experience_mod


def _bind_module_names(mod) -> None:
    """Copy public and private helpers into this module namespace."""
    g = globals()
    for name, value in vars(mod).items():
        if name.startswith("__"):
            continue
        g[name] = value

_bind_module_names(_experience_mod)

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


def _parse_chips(text: str) -> list[str]:
    items: list[str] = []
    for part in re.split(r"[,;\n]", text or ""):
        s = part.strip()
        if s:
            items.append(s)
    return items


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


def _normalize_skill_item(item: object) -> str:
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        return str(
            item.get("name") or item.get("skill") or item.get("title") or item.get("technology") or ""
        ).strip()
    return str(item).strip()

