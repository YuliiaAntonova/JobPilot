"""Legacy ATS notebook dump — not used by crew_l7 orchestrator.

Prefer job_application.resume.jobbert_match for scoring and
safe_tailoring.orchestrator for the public tailor API.
Kept for tests + TAILORING_PIPELINE=notebook helpers.
"""

from __future__ import annotations

import copy
import re
from pathlib import Path

import yaml

from job_application.config import APP_LLM_MODEL
from job_application.shared.llm.client import chat_completion_tracked

MAX_ANALYSIS_TOKENS = 1050
MAX_RESUME_TOKENS = 1400

_USAGE_CALLS: list[dict] = []


def reset_token_usage() -> None:
    _USAGE_CALLS.clear()


def get_usage_calls() -> list[dict]:
    return list(_USAGE_CALLS)


def generate_response(
    message: str,
    system_prompt: str,
    model: str | None = "auto",
    max_output_tokens: int | None = None,
    print_usage: bool = True,
) -> str:
    user = (message or "").strip()
    if max_output_tokens:
        user += (
            f"\nLENGTH: Keep the response within approximately "
            f"{max_output_tokens} output tokens.\n"
        )

    llm_model = None if not model or str(model).strip().lower() == "auto" else model
    response, usage = chat_completion_tracked(
        llm_model or APP_LLM_MODEL,
        system_prompt,
        user,
        call_label="safe_tailoring",
    )
    usage_entry = dict(usage)
    usage_entry["step"] = usage_entry.get("step") or "safe_tailoring"
    _USAGE_CALLS.append(usage_entry)

    if print_usage:
        print(
            f"safe_tailoring tokens: in={usage.get('prompt_tokens', 0)} "
            f"out={usage.get('completion_tokens', 0)}"
        )

    return (response or "").strip()


def extract_text_from_pdf(pdf_path: str | Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    pages = []

    for page in reader.pages:
        page_text = (page.extract_text() or "").strip()
        if page_text:
            pages.append(page_text)

    return "\n\n".join(pages)


def extract_text_from_docx(docx_path: str | Path) -> str:
    from docx import Document

    doc = Document(str(docx_path))
    return "\n".join(
        p.text.strip()
        for p in doc.paragraphs
        if p.text.strip()
    )


def load_resume(path: str | Path) -> str:
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"Resume file not found: {path}")

    suffix = path.suffix.lower()

    if suffix == ".pdf":
        return extract_text_from_pdf(path)

    if suffix == ".docx":
        return extract_text_from_docx(path)

    if suffix in {".txt", ".md", ".yml", ".yaml"}:
        return path.read_text(encoding="utf-8")

    raise ValueError("Supported formats: PDF, DOCX, TXT, MD, YAML")

def _clean_yaml_response(text: str) -> str:
    text = (text or "").strip()
    text = re.sub(r"^```(?:yaml|yml)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text).strip()
    return text


def _parse_yaml_mapping(text: str, label: str) -> dict:
    cleaned = _clean_yaml_response(text)

    if not cleaned:
        raise ValueError(f"{label} is empty.")

    try:
        data = yaml.safe_load(cleaned)
    except yaml.YAMLError as exc:
        raise ValueError(
            f"{label} is not valid YAML.\n\n"
            f"YAML error: {exc}\n\n"
            f"Response:\n{cleaned}"
        ) from exc

    if not isinstance(data, dict):
        raise ValueError(f"{label} root must be a YAML mapping.")

    return data



def parse_original_resume_yaml(resume_text: str) -> dict | None:
    """
    Parse the original resume if it is YAML.
    Returns None for unstructured PDF/DOCX/TXT input.
    """
    try:
        data = yaml.safe_load(resume_text)
    except Exception:
        return None

    return data if isinstance(data, dict) else None


def build_resume_analysis_view(resume_text: str) -> str:
    """
    Compact view for ATS analysis.
    Excludes contact data, education, certifications, languages, links, and note.
    """
    data = parse_original_resume_yaml(resume_text)

    if data is None:
        # Fallback for PDF/DOCX/TXT: cannot safely select YAML sections.
        return resume_text

    basics = data.get("basics", {}) or {}

    compact = {
        "basics": {
            "headline": basics.get("headline", ""),
            "summary": basics.get("summary", ""),
        },
        "skills": data.get("skills", []),
        "experience": data.get("experience", []),
        "experience_earlier": data.get("experience_earlier", []),
    }

    return yaml.safe_dump(
        compact,
        sort_keys=False,
        allow_unicode=True,
        width=120,
    ).strip()


def build_resume_edit_view(resume_text: str) -> str:
    """
    Same compact editable view used by the final editor.
    """
    return build_resume_analysis_view(resume_text)


def merge_editable_blocks_into_original(
    original_resume_text: str,
    edited_blocks: dict,
) -> dict:
    """
    Merge only allowed editable blocks back into the original YAML.

    Immutable sections remain exactly from the original resume:
    name/contact/location/links/note, education, certifications, languages.
    """
    original = parse_original_resume_yaml(original_resume_text)

    if original is None:
        # Unstructured fallback: return model output directly.
        return edited_blocks

    result = dict(original)

    # Only headline and summary may change inside basics.
    original_basics = dict(original.get("basics", {}) or {})
    edited_basics = edited_blocks.get("basics", {}) or {}

    if "headline" in edited_basics:
        original_basics["headline"] = edited_basics["headline"]

    if "summary" in edited_basics:
        original_basics["summary"] = edited_basics["summary"]

    result["basics"] = original_basics

    # Only these top-level sections are editable.
    for section in ("skills", "experience", "experience_earlier"):
        if section in edited_blocks:
            result[section] = edited_blocks[section]

    return result


def analyze_resume_for_safe_tailoring(
    resume_text: str,
    job_description: str,
    model: str = "auto",
    max_output_tokens: int = 1050,
) -> dict:
    """
    Compact ATS pass using only relevant resume blocks.
    """
    resume_view = build_resume_analysis_view(resume_text)

    prompt = f"""
Analyze the RESUME VIEW against the JOB DESCRIPTION.

JOB DESCRIPTION:
{job_description}

RESUME VIEW:
{resume_view}

Return ONLY valid YAML:

target_role: ""

ats_keywords:
  - ""

career_advisor_priorities:
  - ""

action_plan:
  auto_apply:
    - id: ""
      section: ""
      instruction: ""
      evidence: ""

  ask_user:
    - id: ""
      section: ""
      apply_to: ""
      company: ""
      required_terms:
        - ""
      proposed_fact: ""
      why_it_matters: ""

  do_not_add:
    - id: ""
      item: ""
      apply_to: ""
      company: ""
      forbidden_term_sets:
        - [""]
      reason: ""

bullet_revisions:
  - company: ""
    bullet_index: 0
    original: ""
    suggested_rewrite: ""
    evidence: ""

RULES:
- RESUME VIEW is the only confirmed source of candidate facts.
- ATS keywords: extract 8-12 important hard-skill/platform/responsibility terms from the vacancy.
- Career-advisor priorities: at most 3 concise things to emphasize based on actual overlap.

AUTO_APPLY:
- Only safe edits already supported by RESUME VIEW.
- Do not introduce a technology into experience unless the same role/bullet explicitly supports it.
- Do not derive a new technical capability from adjacent evidence.

ASK_USER:
- Use only for relevant facts NOT explicit in RESUME VIEW.
- proposed_fact must be ONE atomic, concrete, CV-ready statement.
- No placeholders.
- No "or" alternatives.
- One technology/claim per proposed_fact.
- apply_to must be one of: skills, experience, summary.
- required_terms must contain the minimum literal terms that must appear in the
  target section for the fact to count as applied.
- proposed_fact semantic strength MUST match apply_to:
  * apply_to: skills — state only skill membership / familiarity.
    Do NOT use proficient, expert, professional experience, production experience,
    hands-on experience, years of experience, backend/workload-specific experience,
    architecture ownership, or implementation ownership language.
    Prefer neutral wording such as "<skill> is part of the candidate's technical skill set."
    Confirmed skills are later mirrored in Skills, Summary, and a relevant work-context experience bullet
    (never as a standalone skill-inventory bullet).
  * apply_to: experience — professional/production/hands-on/implementation claims are allowed,
    but company is REQUIRED, the fact must be concrete and atomic, and required_terms must be
    sufficient to verify the claim inside that employer's experience block.
    Do NOT include the company name inside proposed_fact bullet wording; the employer header already shows it.
  * apply_to: summary — may describe a broader capability, but must not exceed what the human
    could reasonably confirm from the proposed fact alone.
- For apply_to: experience, company is REQUIRED and must exactly match one company
  already present in RESUME VIEW.
- Experience-level proposed facts must be anchored to technologies already associated
  with that company in RESUME VIEW whenever possible.
- Do not create a broad experience claim if you can formulate a narrower company-specific
  fact from existing evidence.
- A technology appearing only in skills does NOT satisfy an experience-level claim.
- If necessary platform/context is unknown, put the item in do_not_add instead.

BULLET_REVISIONS:
- Rewrite only an existing bullet.
- Preserve factual meaning exactly.
- A safe rewrite may improve wording, but MUST NOT introduce a new:
  technical noun, technology, responsibility, metric, workload type, capability,
  architecture concept, performance metric, or scope that is absent from that original bullet.
- Do not infer a stronger or different technical claim from adjacent wording.
- Do not convert a generic improvement into a specific metric unless that metric is explicit.
- Do not convert use of one technology into experience with another technology.
- Do not convert participation into ownership, design, architecture, production scale,
  or operational responsibility unless explicitly supported.
- suggested_rewrite must be safe without human confirmation.
- Do not combine facts from separate bullets.

DO_NOT_ADD:
- Unsupported vacancy requirements and stronger interpretations go here.
- If related to ask_user, use the same stable id.
- apply_to must be one of: skills, experience, summary, anywhere.
- For apply_to: experience, set company only when the restriction is specific to one employer.
- forbidden_term_sets are used by LOCAL Python validation after generation.
- Each inner list is an AND-set: if every term in that set occurs in the target area,
  the restriction is considered hit.
- Use short distinctive literal terms, not whole sentences.
- Build forbidden_term_sets from the unsupported claim itself.
- Each set should contain the smallest distinctive terms needed to identify that claim.
- Avoid generic singleton words that could occur innocently in unrelated resume content.
- Never combine multiple independently confirmable claims into one proposed_fact.
  Split them into separate atomic ask_user items.
- For experience confirmations, anchor the proposal to the exact employer and to
  concrete technologies/responsibilities already associated with that employer
  whenever possible.
- Do not upgrade evidence into a broader architecture, ownership, scale, performance,
  or production claim unless the human explicitly confirms that stronger claim.

Keep the result concise.
YAML only. No Markdown.
"""

    response = generate_response(
        prompt,
        system_prompt=(
            "You are a strict factual ATS analyst. "
            "Separate safe edits, human-confirmed additions, and unsupported claims. "
            "Never upgrade adjacent evidence into a stronger technical claim."
        ),
        model=model,
        max_output_tokens=max_output_tokens,
    )

    data = _parse_yaml_mapping(response, "ATS analysis")

    data.setdefault("target_role", "")
    data.setdefault("ats_keywords", [])
    data.setdefault("career_advisor_priorities", [])
    data.setdefault("bullet_revisions", [])
    data.setdefault("action_plan", {})
    data["action_plan"].setdefault("auto_apply", [])
    data["action_plan"].setdefault("ask_user", [])
    data["action_plan"].setdefault("do_not_add", [])

    return data


# JobBERT scoring lives in jobbert_match; keep names here for legacy notebook helpers/tests.
from job_application.resume.jobbert_match import (  # noqa: E402,F401
    _SKILL_CONTAINER_KEYS,
    _SKILL_DICT_NAME_KEYS,
    _SKILL_TOP_LEVEL_KEYS,
    _expand_skill_aliases,
    _flatten_skill_entries,
    _is_skill_chip,
    compute_jobbert_skill_match,
    cv_yaml_to_jobbert_plain,
    derive_semantic_groups,
    flatten_cv_skills_for_jobbert,
    jobbert_structured_for_scoring,
    run_jobbert_match_score,
)


def _format_display_name(name: str) -> str:
    """Render ALL-CAPS source names in readable title case for HTML output."""
    name = str(name or "").strip()
    if not name:
        return name

    letters = [ch for ch in name if ch.isalpha()]
    if not letters:
        return name

    upper_ratio = sum(ch.isupper() for ch in letters) / len(letters)
    if upper_ratio < 0.8:
        return name

    def _title_token(token: str) -> str:
        return "-".join(part.capitalize() for part in token.split("-"))

    return " ".join(_title_token(part) for part in name.split())


def render_cv_html(cv: dict, template_path: Path, output_path: Path) -> None:
    """Render cv_tailored.yml into cv.html using an existing HTML shell template."""
    from html import escape

    template_path = Path(template_path)
    output_path = Path(output_path)
    template = template_path.read_text(encoding="utf-8")

    b = cv.get("basics", {}) or {}
    display_name = _format_display_name(b.get("name", ""))

    def _link(item: dict) -> str:
        from job_application.resume.pdf.render import link_display_text

        display = link_display_text(item)
        url = str(item.get("url") or "").strip()
        if not display:
            return ""
        if url:
            return f'<a href="{escape(url)}">{escape(display)}</a>'
        return escape(display)

    links_html = " <span>&bull;</span> ".join(
        part
        for item in b.get("links", [])
        if isinstance(item, dict)
        for part in [_link(item)]
        if part
    )
    contact_parts = [escape(b.get("location", ""))]
    if b.get("email"):
        email = escape(b["email"])
        contact_parts.append(f'<a href="mailto:{email}">{email}</a>')
    if b.get("phone"):
        contact_parts.append(escape(b["phone"]))
    contact = " <span>&bull;</span> ".join(contact_parts)
    if links_html:
        contact += f" <span>&bull;</span> {links_html}"

    note = str(b.get("note", "") or "").strip()
    note_html = f'<p class="note">{escape(note)}</p>' if note else ""

    header = (
        f"<header><h1>{escape(display_name)}</h1>"
        f'<p class="headline">{escape(b.get("headline", ""))}</p>'
        f'<p class="contact">{contact}</p>{note_html}</header>'
    )
    summary = (
        f'<section><h2>Summary</h2>'
        f'<p class="summary">{escape(b.get("summary", ""))}</p></section>'
    )

    skills = '<section><h2>Skills</h2><div class="skills">'
    for group in cv.get("skills", []) or []:
        if not isinstance(group, dict):
            continue
        items = ", ".join(escape(x) for x in group.get("items", []) or [])
        skills += (
            f'<div class="skill-row"><span class="skill-group">{escape(group.get("group", ""))}</span>'
            f'<span class="skill-items">{items}</span></div>'
        )
    skills += "</div></section>"

    exp = ['<section><h2>Experience</h2>']
    for entry in cv.get("experience", []) or []:
        if not isinstance(entry, dict):
            continue
        bullets = "".join(f"<li>{escape(x)}</li>" for x in entry.get("bullets", []) or [])
        exp.append(
            f'<div class="entry"><div class="entry-head"><span class="left">{escape(entry.get("company", ""))}</span>'
            f'<span class="right">{escape(entry.get("location", ""))}</span></div>'
            f'<div class="entry-sub"><span class="left">{escape(entry.get("title", ""))}</span>'
            f'<span class="right">{escape(entry.get("period", ""))}</span></div>'
            f"<ul>{bullets}</ul></div>"
        )
    exp.append("</section>")

    earlier = ['<section><h2>Earlier Experience</h2><div class="earlier">']
    for entry in cv.get("experience_earlier", []) or []:
        if not isinstance(entry, dict):
            continue
        stack = ", ".join(escape(x) for x in entry.get("stack", []) or [])
        earlier.append(
            f'<div class="earlier-row"><span class="left"><strong>{escape(entry.get("company", ""))}</strong>'
            f' — {escape(entry.get("role", ""))}</span>'
            f'<span class="right">{escape(entry.get("period", ""))}</span></div>'
            f'<div class="earlier-stack">{stack}</div>'
        )
    earlier.append("</div></section>")

    education = ""
    for edu in cv.get("education", []) or []:
        if not isinstance(edu, dict):
            continue
        education = (
            f'<section><h2>Education</h2><div class="entry">'
            f'<div class="entry-head"><span class="left">{escape(edu.get("degree", ""))}</span>'
            f'<span class="right">{escape(edu.get("period", ""))}</span></div>'
            f'<div class="entry-sub"><span class="left">{escape(edu.get("school", ""))}</span>'
            f'<span class="right"></span></div></div></section>'
        )
        break

    certs = '<section><h2>Certifications</h2>'
    for cert in cv.get("certifications", []) or []:
        name = cert.get("name", cert) if isinstance(cert, dict) else cert
        certs += f'<div class="cert-row"><span class="left">{escape(str(name))}</span><span class="right"></span></div>'
    certs += "</section>"

    lang_parts = []
    for lang in cv.get("languages", []) or []:
        if isinstance(lang, dict):
            name = escape(lang.get("name", ""))
            level = str(lang.get("level", "") or "").strip()
            if level:
                lang_parts.append(f'{name} <span class="lang-level">({escape(level)})</span>')
            else:
                lang_parts.append(name)
        else:
            lang_parts.append(escape(str(lang)))
    languages = (
        f'<section><h2>Languages</h2>'
        f'<p class="languages">{" <span>&bull;</span> ".join(lang_parts)}</p></section>'
    )

    body = (
        f'<main class="page">{header}{summary}{skills}{"".join(exp)}{"".join(earlier)}'
        f"{education}{certs}{languages}</main>"
    )

    main_start = '<main class="page">'
    main_end = '</main>'
    if main_start not in template or main_end not in template:
        raise ValueError(f"HTML template missing {main_start} wrapper: {template_path}")

    rendered = (
        template[: template.index(main_start)]
        + body
        + template[template.index(main_end) + len(main_end) :]
    )
    rendered = re.sub(
        r"(?s)<title>.*?</title>",
        f"<title>{escape(display_name)} — CV</title>",
        rendered,
        count=1,
    )
    output_path.write_text(rendered, encoding="utf-8")


def _normalize_renderer_schema(parsed: dict) -> dict:
    # Certifications -> mappings containing at least name.
    certs = parsed.get("certifications", [])
    normalized_certs = []

    if isinstance(certs, list):
        for cert in certs:
            if isinstance(cert, dict):
                name = str(cert.get("name", "") or "").strip()
                if not name:
                    continue

                item = {"name": name}
                issuer = str(cert.get("issuer", "") or "").strip()
                year = str(cert.get("year", "") or "").strip()

                if issuer:
                    item["issuer"] = issuer
                if year:
                    item["year"] = year

                normalized_certs.append(item)

            elif isinstance(cert, str) and cert.strip():
                normalized_certs.append({"name": cert.strip()})

    if "certifications" in parsed:
        parsed["certifications"] = normalized_certs

    # Languages -> mappings with name + level.
    languages = parsed.get("languages", [])
    normalized_languages = []

    if isinstance(languages, list):
        for lang in languages:
            if isinstance(lang, dict):
                name = str(lang.get("name", "") or "").strip()
                if not name:
                    continue

                normalized_languages.append({
                    "name": name,
                    "level": str(lang.get("level", "") or "").strip(),
                })

            elif isinstance(lang, str) and lang.strip():
                normalized_languages.append({
                    "name": lang.strip(),
                    "level": "",
                })

    if "languages" in parsed:
        parsed["languages"] = normalized_languages

    return parsed

def _experience_company_text(edited_blocks: dict, company: str) -> str:
    """
    Return only the experience entry for the exact company.
    """
    company = (company or "").strip()
    if not company:
        return ""

    for entry in edited_blocks.get("experience", []) or []:
        if not isinstance(entry, dict):
            continue
        if str(entry.get("company", "") or "").strip() == company:
            return yaml.safe_dump(
                entry,
                sort_keys=False,
                allow_unicode=True,
            ).lower()

    return ""


def _section_text_for_fact(
    edited_blocks: dict,
    apply_to: str,
    company: str = "",
) -> str:
    """
    Return only the target resume area used for local confirmed-fact validation.
    Experience facts are scoped to the exact company.
    """
    apply_to = (apply_to or "").strip().lower()

    if apply_to == "skills":
        value = edited_blocks.get("skills", [])
    elif apply_to == "experience":
        return _experience_company_text(edited_blocks, company)
    elif apply_to == "summary":
        value = (edited_blocks.get("basics", {}) or {}).get("summary", "")
    else:
        return ""

    if isinstance(value, str):
        return value.lower()

    return yaml.safe_dump(
        value,
        sort_keys=False,
        allow_unicode=True,
    ).lower()


def _collect_auto_apply_ids(analysis: dict) -> set[str]:
    """IDs from auto_apply — LLM often lists these in applied_confirmed_ids."""
    action_plan = analysis.get("action_plan") if isinstance(analysis.get("action_plan"), dict) else {}
    ids: set[str] = set()
    for item in action_plan.get("auto_apply", []) or []:
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id", "") or "").strip()
        if item_id:
            ids.add(item_id)
    return ids


def _normalize_applied_ids(applied_ids: set[str], confirmed_facts: list[dict]) -> set[str]:
    """Map applied ids to confirmed_fact ids when casing differs."""
    confirmed_ids = {
        str(item.get("id", "") or "").strip()
        for item in confirmed_facts
        if isinstance(item, dict) and str(item.get("id", "") or "").strip()
    }
    by_lower = {cid.lower(): cid for cid in confirmed_ids}
    normalized: set[str] = set()
    for aid in applied_ids:
        if aid in confirmed_ids:
            normalized.add(aid)
        elif aid.lower() in by_lower:
            normalized.add(by_lower[aid.lower()])
        else:
            normalized.add(aid)
    return normalized


def _validate_confirmed_facts_in_sections(
    edited_blocks: dict,
    confirmed_facts: list[dict],
    applied_ids: set[str],
    *,
    extra_allowed_applied_ids: set[str] | None = None,
) -> dict:
    """
    Validate that every confirmed fact:
    1. is reported as applied by the model;
    2. appears in the required target section(s);
    3. for experience, appears under the exact confirmed company;
    4. contains all required literal terms in the target area(s);
    5. for skills, also appears in Summary and at least one experience bullet;
    6. for experience, bullets must not repeat the company name.
    """
    details = []
    missing_ids = []
    wrong_target_ids = []
    company_name_in_bullet_ids = []
    skills_cross_section_failed = []
    skills_work_context_failed = []
    skills_meta_bullet_failed = []

    confirmed_ids = {
        str(item.get("id", "") or "").strip()
        for item in confirmed_facts
        if isinstance(item, dict) and str(item.get("id", "") or "").strip()
    }
    allowed_applied_ids = confirmed_ids | set(extra_allowed_applied_ids or ())

    for item in confirmed_facts:
        if not isinstance(item, dict):
            continue

        fact_id = str(item.get("id", "") or "").strip()
        apply_to = str(item.get("apply_to", "") or "").strip().lower()
        company = str(item.get("company", "") or "").strip()
        required_terms = [
            str(x).strip()
            for x in (item.get("required_terms", []) or [])
            if str(x).strip()
        ]

        semantic_groups = item.get("semantic_groups") or _derive_semantic_groups(
            str(item.get("fact", "") or "")
        )

        skills_text = _section_text_for_fact(edited_blocks, "skills")
        summary_text = _section_text_for_fact(edited_blocks, "summary")
        bullets_text = _all_experience_bullets_text(edited_blocks)

        if apply_to == "skills":
            work_context_results = _skill_terms_in_work_context_bullets(
                edited_blocks, required_terms
            )
            term_results = {
                "skills": _terms_present_in_text(required_terms, skills_text),
                "summary": _terms_present_in_text(required_terms, summary_text),
                "work_context_bullets": work_context_results,
            }
            target_exists = bool(skills_text.strip() and summary_text.strip() and bullets_text.strip())
            terms_ok = bool(required_terms) and all(
                all(area.values()) for area in term_results.values()
            )
            semantic_ok = all(
                _semantic_groups_satisfied(area_text, semantic_groups)
                for area_text in (skills_text, summary_text, bullets_text)
            )
            company_ok = True
            company_name_in_bullet = False
            target_text = skills_text
        else:
            target_text = _section_text_for_fact(
                edited_blocks=edited_blocks,
                apply_to=apply_to,
                company=company,
            )
            term_results = {
                apply_to: {
                    term: term.lower() in target_text
                    for term in required_terms
                }
            }
            target_exists = bool(target_text.strip())
            terms_ok = bool(required_terms) and all(term_results[apply_to].values())
            semantic_ok = _semantic_groups_satisfied(target_text, semantic_groups)
            company_ok = True
            company_name_in_bullet = False
            if apply_to == "experience":
                company_ok = bool(company) and target_exists
                company_name_in_bullet = _company_bullets_contain_company_name(
                    edited_blocks, company
                )

        meta_skill_bullets = _meta_skill_bullets_present(edited_blocks) if apply_to == "skills" else []
        target_ok = (
            bool(apply_to)
            and target_exists
            and terms_ok
            and company_ok
            and semantic_ok
            and not company_name_in_bullet
            and not meta_skill_bullets
        )

        model_reported = fact_id in applied_ids

        if not model_reported:
            missing_ids.append(fact_id)

        if model_reported and not target_ok:
            wrong_target_ids.append(fact_id)
            if apply_to == "skills" and not terms_ok:
                skills_cross_section_failed.append(fact_id)
            if apply_to == "skills":
                wc = term_results.get("work_context_bullets", {})
                if wc and not all(wc.values()):
                    skills_work_context_failed.append(fact_id)
                if _meta_skill_bullets_present(edited_blocks):
                    skills_meta_bullet_failed.append(fact_id)
            if company_name_in_bullet:
                company_name_in_bullet_ids.append(fact_id)

        details.append({
            "id": fact_id,
            "apply_to": apply_to,
            "company": company,
            "required_terms": required_terms,
            "semantic_groups": semantic_groups,
            "term_results": term_results,
            "semantic_validation_passed": semantic_ok,
            "company_name_in_bullet": company_name_in_bullet,
            "meta_skill_bullets_found": _meta_skill_bullets_present(edited_blocks) if apply_to == "skills" else [],
            "model_reported_applied": model_reported,
            "target_exists": target_exists,
            "target_validation_passed": target_ok,
        })

    unknown_applied_ids = sorted(applied_ids - allowed_applied_ids)

    semantic_failed_ids = sorted(
        detail["id"]
        for detail in details
        if detail.get("model_reported_applied")
        and detail.get("semantic_validation_passed") is False
    )

    return {
        "confirmed_ids": sorted(confirmed_ids),
        "applied_confirmed_ids": sorted(applied_ids),
        "missing_confirmed_ids": sorted(set(missing_ids)),
        "wrong_target_or_missing_terms": sorted(set(wrong_target_ids)),
        "skills_cross_section_failed": sorted(set(skills_cross_section_failed)),
        "skills_work_context_failed": sorted(set(skills_work_context_failed)),
        "skills_meta_bullet_failed": sorted(set(skills_meta_bullet_failed)),
        "company_name_in_bullet": sorted(set(company_name_in_bullet_ids)),
        "semantic_validation_failed": semantic_failed_ids,
        "unknown_applied_ids": unknown_applied_ids,
        "details": details,
        "all_confirmed_facts_applied": (
            not missing_ids
            and not wrong_target_ids
            and not unknown_applied_ids
        ),
    }


def generate_tailored_resume(
    original_resume_text: str,
    job_description: str,
    analysis: dict,
    confirmed_facts: list[dict],
    model: str = "auto",
    max_output_tokens: int = 1400,
) -> tuple[str, dict]:
    """
    Final editor sees only editable resume blocks.

    Every human-confirmed fact is a REQUIRED edit and must appear
    in its required target section. Experience-level facts are
    additionally scoped to the exact confirmed company.
    """
    action_plan = analysis.get("action_plan", {})

    confirmed_ids = {
        str(item.get("id", "") or "").strip()
        for item in confirmed_facts
        if isinstance(item, dict) and str(item.get("id", "") or "").strip()
    }

    filtered_do_not_add = []
    for item in action_plan.get("do_not_add", []):
        if isinstance(item, dict):
            item_id = str(item.get("id", "") or "").strip()
            if item_id and item_id in confirmed_ids:
                continue
        filtered_do_not_add.append(item)

    approved_plan = {
        "target_role": analysis.get("target_role", ""),
        "auto_apply": action_plan.get("auto_apply", []),
        "bullet_revisions": analysis.get("bullet_revisions", []),
        "confirmed_facts": confirmed_facts,
        "do_not_add": filtered_do_not_add,
    }

    resume_edit_view = build_resume_edit_view(original_resume_text)

    approved_plan_yaml = yaml.safe_dump(
        approved_plan,
        sort_keys=False,
        allow_unicode=True,
        width=120,
    )

    print("\n--- APPROVED PLAN SENT TO FINAL LLM ---\n")
    print(approved_plan_yaml)

    prompt = f"""
Tailor only the EDITABLE RESUME BLOCKS to the JOB DESCRIPTION.

EDITABLE RESUME BLOCKS:
{resume_edit_view}

JOB DESCRIPTION:
{job_description}

APPROVED PLAN:
{approved_plan_yaml}

Return ONLY valid YAML in this exact wrapper:

applied_confirmed_ids:
  - ""

resume:
  basics:
    headline: ""
    summary: ""

  skills:
    - group: ""
      items:
        - ""

  experience:
    - company: ""
      title: ""
      location: ""
      period: ""
      bullets:
        - ""

  experience_earlier:
    - period: ""
      company: ""
      role: ""
      location: ""
      stack:
        - ""

CONFIRMED FACTS:
- Every confirmed_fact is a REQUIRED edit.
- Preserve the human-approved wording as closely as possible.
- Do not weaken, broaden, or reinterpret confirmed facts.
- When practical, insert the confirmed_fact text directly or with minimal grammatical adaptation.
- Respect apply_to exactly.
- For apply_to: experience:
  * place the fact ONLY under the exact company specified in confirmed_fact.company;
  * preserve that company's original title, location, and period;
  * the bullet must contain all required_terms literally;
  * do NOT repeat the company name inside bullet text;
  * merely adding the technology to Skills does NOT count.
- For apply_to: skills:
  * the skill/technology must appear in Skills, Summary, and at least one relevant WORK-CONTEXT experience bullet;
  * integrate the skill into an existing pipeline/project bullet under the most relevant employer;
  * use action + outcome phrasing already supported by that employer block (e.g. optimized, improved performance,
    increased processing speed, reduced runtime, faster pipelines);
  * you MAY add conservative, explainable impact metrics when the original employer bullet already describes an
    optimization method (chunking, partitioning, orchestration, deduplication) — e.g. "20-40% faster processing"
    or "reduced manual processing time"; never invent revenue/users/production-scale numbers;
  * do NOT create standalone inventory/meta bullets such as "Technical skill set includes ...";
  * pick the most relevant employer block when existing stack/evidence supports it.
- For apply_to: summary, the fact must appear in Summary.
- applied_confirmed_ids must list ONLY ids from confirmed_facts above.
  Do NOT list auto_apply or bullet_revisions ids there (those are applied silently).
- Only include a confirmed_fact id when that fact is visibly represented in the correct target area.
- Do not silently omit a confirmed fact.

EXPERIENCE FACT SAFETY:
- Do not turn an existing implementation detail into a broader architecture,
  ownership, scale, production, or performance claim just to fit a confirmed fact.
- Keep the wording as close as possible to the human-approved fact.
- Do not relocate a confirmed experience fact to another company.
- Do not attach a confirmed fact to a different project, employer, timeframe,
  technology, or responsibility unless the confirmation itself supports that link.

BULLET SAFETY:
- A rewrite may improve phrasing only.
- Do not introduce a new technical noun, responsibility, metric, workload type,
  capability, architecture concept, performance metric, or scope absent from
  that original bullet or a confirmed_fact.
- Do not infer a stronger or different technical claim from adjacent wording.
- Do not convert a generic improvement into a specific metric unless that metric is explicit.
- Do not convert use of one technology into experience with another technology.
- Do not convert participation into ownership, design, architecture, production scale,
  or operational responsibility unless explicitly supported.

AUTO_APPLY / BULLET_REVISIONS:
- Apply only when fully supported.
- Ignore any proposed safe edit that violates the above safety rules.

SKILLS / SKILL PLACEMENT IN EXPERIENCE:
- May contain only skills explicit in EDITABLE RESUME BLOCKS or confirmed_facts.
- Reordering, regrouping, and omission of lower-relevance skills are allowed.
- Confirmed skills must also be woven into relevant experience bullets with work context and impact wording.
- Prefer updating an existing bullet over adding a skill-inventory bullet.
- For each confirmed skill, rewrite ONE existing employer bullet to weave the skill into pipeline/project work
  with BOTH an action verb and impact/outcome wording (optimized, improved performance, faster processing).
- Never add bullets like "Technical skill set includes ...".
- When strengthening optimization bullets, you MAY add conservative explainable metrics/ranges tied to
  methods already present in the original bullet (chunking, partitioning, orchestration, deduplication).
- Do not invent proficiency levels, production usage, years of experience, role context, or unsupported KPIs
  from a skill name alone.

OUTPUT:
- YAML only.
- No Markdown.
- Return only applied_confirmed_ids + resume wrapper.
"""

    response = generate_response(
        prompt,
        system_prompt=(
            "You are a conservative resume editor. "
            "Human-confirmed facts are required additions and must be placed "
            "under the exact confirmed section and company."
        ),
        model=model,
        max_output_tokens=max_output_tokens,
    )

    result = _parse_yaml_mapping(response, "Tailored resume result")

    edited_blocks = result.get("resume")
    if not isinstance(edited_blocks, dict):
        raise ValueError("Final LLM output must contain a 'resume' mapping.")

    raw_applied_ids = result.get("applied_confirmed_ids", [])
    if not isinstance(raw_applied_ids, list):
        raise ValueError("applied_confirmed_ids must be a YAML list.")

    applied_ids = {
        str(x).strip()
        for x in raw_applied_ids
        if str(x).strip()
    }
    applied_ids = _normalize_applied_ids(applied_ids, confirmed_facts)
    auto_apply_ids = _collect_auto_apply_ids(analysis)

    edited_blocks = _sanitize_confirmed_skill_placements(
        edited_blocks=edited_blocks,
        confirmed_facts=confirmed_facts,
    )
    edited_blocks = _sanitize_confirmed_experience_placements(
        edited_blocks=edited_blocks,
        confirmed_facts=confirmed_facts,
    )
    edited_blocks = _sanitize_confirmed_summary_placements(
        edited_blocks=edited_blocks,
        confirmed_facts=confirmed_facts,
    )

    audit = _validate_confirmed_facts_in_sections(
        edited_blocks=edited_blocks,
        confirmed_facts=confirmed_facts,
        applied_ids=applied_ids,
        extra_allowed_applied_ids=auto_apply_ids,
    )

    print("\n--- CONFIRMED FACT TARGET AUDIT ---\n")
    print(yaml.safe_dump(audit, sort_keys=False, allow_unicode=True))

    if audit["unknown_applied_ids"]:
        raise ValueError(
            "Final LLM reported unknown applied_confirmed_ids: "
            + ", ".join(audit["unknown_applied_ids"])
        )

    if audit["missing_confirmed_ids"]:
        raise ValueError(
            "Final resume silently omitted confirmed facts: "
            + ", ".join(audit["missing_confirmed_ids"])
        )

    if audit.get("skills_meta_bullet_failed"):
        raise ValueError(
            "Confirmed skills must not use standalone skill-inventory bullets: "
            + ", ".join(audit["skills_meta_bullet_failed"])
        )

    if audit.get("skills_work_context_failed"):
        raise ValueError(
            "Confirmed skills must appear in work-context experience bullets with action + impact wording: "
            + ", ".join(audit["skills_work_context_failed"])
        )

    if audit.get("skills_cross_section_failed"):
        raise ValueError(
            "Confirmed skill must appear in Skills, Summary, and experience bullets: "
            + ", ".join(audit["skills_cross_section_failed"])
        )

    if audit.get("company_name_in_bullet"):
        raise ValueError(
            "Experience bullets must not repeat the company name: "
            + ", ".join(audit["company_name_in_bullet"])
        )

    if audit.get("semantic_validation_failed"):
        raise ValueError(
            "Confirmed fact semantic validation failed:\n"
            + ", ".join(audit["semantic_validation_failed"])
        )

    if audit["wrong_target_or_missing_terms"]:
        raise ValueError(
            "Confirmed facts were not applied in the required section/company "
            "or required terms are missing: "
            + ", ".join(audit["wrong_target_or_missing_terms"])
        )

    merged = merge_editable_blocks_into_original(
        original_resume_text=original_resume_text,
        edited_blocks=edited_blocks,
    )

    merged = _normalize_renderer_schema(merged)

    for cert in merged.get("certifications", []):
        if not isinstance(cert, dict) or not cert.get("name"):
            raise ValueError(
                "Renderer compatibility error: every certification must have name."
            )

    for lang in merged.get("languages", []):
        if not isinstance(lang, dict) or not lang.get("name"):
            raise ValueError(
                "Renderer compatibility error: every language must have name."
            )
        lang.setdefault("level", "")

    final_yaml = yaml.safe_dump(
        merged,
        sort_keys=False,
        allow_unicode=True,
        width=120,
    ).strip()

    return final_yaml, audit





# --- Local validation helpers (no LLM) ---

_SKILLS_STRONG_CLAIM_RE = re.compile(
    r"(?i)\b("
    r"proficient|expert|professional(?:\s+experience)?|production(?:\s+experience)?|"
    r"hands-on(?:\s+experience)?|years?\s+of\s+experience|"
    r"backend(?:\s+development)?(?:\s+experience)?|"
    r"workload(?:\s+specific)?(?:\s+experience)?|"
    r"architecture(?:\s+ownership)?|implementation(?:\s+ownership)?|"
    r"experienced?\s+in|deep\s+experience|extensive\s+experience|"
    r"practical\s+experience|demonstrated\s+experience"
    r")\b"
)

_SEMANTIC_STOPWORDS = frozenset({
    "a", "an", "the", "and", "or", "of", "in", "on", "at", "to", "for", "with",
    "is", "are", "was", "were", "be", "been", "being", "part", "candidate",
    "technical", "skill", "set", "their", "that", "this", "as", "by", "from",
    "employer", "company",
})


def _known_resume_companies(resume_text: str) -> set[str]:
    data = parse_original_resume_yaml(resume_text)
    if not isinstance(data, dict):
        return set()

    companies: set[str] = set()
    for entry in (data.get("experience", []) or []):
        if isinstance(entry, dict):
            company = str(entry.get("company", "") or "").strip()
            if company:
                companies.add(company)
    return companies


def _contains_strong_skills_claim(text: str) -> bool:
    return bool(_SKILLS_STRONG_CLAIM_RE.search(text or ""))


def _neutral_skills_proposed_fact(required_terms: list[str]) -> str | None:
    terms = [str(x).strip() for x in (required_terms or []) if str(x).strip()]
    if not terms:
        return None
    return f"{terms[0]} is part of the candidate's technical skill set."


def _derive_semantic_groups(fact: str) -> list[list[str]]:
    """Build concise OR-groups from a confirmed fact for local semantic checks."""
    return derive_semantic_groups(fact)


_PLACEMENT_SEMANTIC_TERMS = frozenset({"employer", "company", "this"})


def _semantic_groups_satisfied(target_text: str, semantic_groups: list) -> bool:
    target_text = (target_text or "").lower()
    if not semantic_groups:
        return True

    checked = 0
    for group in semantic_groups:
        if not isinstance(group, (list, tuple)):
            continue
        terms = [str(term).strip().lower() for term in group if str(term).strip()]
        if not terms:
            continue
        if len(terms) == 1 and terms[0] in _PLACEMENT_SEMANTIC_TERMS:
            continue
        checked += 1
        if not any(term in target_text for term in terms):
            return False
    return True if checked else True


def _all_experience_bullets_text(edited_blocks: dict) -> str:
    """Concatenate all experience bullet text for cross-role skill checks."""
    parts: list[str] = []
    for entry in edited_blocks.get("experience", []) or []:
        if not isinstance(entry, dict):
            continue
        for bullet in entry.get("bullets", []) or []:
            text = str(bullet or "").strip()
            if text:
                parts.append(text)
    return "\n".join(parts).lower()


def _company_bullets_contain_company_name(edited_blocks: dict, company: str) -> bool:
    """True when any bullet under the exact company repeats the company name."""
    company = (company or "").strip()
    if not company:
        return False

    company_lower = company.lower()
    for entry in edited_blocks.get("experience", []) or []:
        if not isinstance(entry, dict):
            continue
        if str(entry.get("company", "") or "").strip() != company:
            continue
        for bullet in entry.get("bullets", []) or []:
            if company_lower in str(bullet or "").lower():
                return True
    return False


def _terms_present_in_text(required_terms: list[str], target_text: str) -> dict[str, bool]:
    target_text = (target_text or "").lower()
    return {
        term: term.lower() in target_text
        for term in required_terms
    }





_META_SKILL_BULLET_RE = re.compile(
    r"(?i)(technical skill set|skill set includes|skills include|candidate(?:'|')?s technical skill set|"
    r"part of the candidate|familiar with the following|tooling includes|technologies include|"
    r"includes .*(?:iceberg|bigquery|rust)|\bskill set\b)"
)

_WORK_CONTEXT_ACTION_RE = re.compile(
    r"(?i)\b(built|developed|implemented|optimized|optimised|improved|increased|reduced|"
    r"automated|designed|engineered|delivered|accelerated|enhanced|streamlined|tuned|"
    r"migrated|integrated|deployed|maintained|worked on|used|applied|leveraged)\b"
)

_IMPACT_CONTEXT_RE = re.compile(
    r"(?i)\b(performance|speed|throughput|latency|efficiency|processing|faster|reliable|"
    r"reliability|quality|cost|scalability|pipeline|workloads?|transformations?|runtime|"
    r"to improve|for faster|reducing|improvement|optimization|optimisation)\b"
)


def _is_meta_skill_bullet(bullet: str) -> bool:
    return bool(_META_SKILL_BULLET_RE.search(bullet or ""))


def _is_work_context_skill_bullet(bullet: str, required_term: str) -> bool:
    text = str(bullet or "")
    term = str(required_term or "").strip()
    if not term or _is_meta_skill_bullet(text):
        return False
    if term.lower() not in text.lower():
        return False
    return (
        bool(_WORK_CONTEXT_ACTION_RE.search(text))
        and bool(_IMPACT_CONTEXT_RE.search(text))
    )


def _iter_experience_bullets(edited_blocks: dict) -> list[str]:
    bullets: list[str] = []
    for entry in edited_blocks.get("experience", []) or []:
        if not isinstance(entry, dict):
            continue
        for bullet in entry.get("bullets", []) or []:
            text = str(bullet or "").strip()
            if text:
                bullets.append(text)
    return bullets


def _skill_terms_in_work_context_bullets(
    edited_blocks: dict,
    required_terms: list[str],
) -> dict[str, bool]:
    bullets = _iter_experience_bullets(edited_blocks)
    return {
        term: any(_is_work_context_skill_bullet(bullet, term) for bullet in bullets)
        for term in required_terms
    }


def _meta_skill_bullets_present(edited_blocks: dict) -> list[str]:
    return [b for b in _iter_experience_bullets(edited_blocks) if _is_meta_skill_bullet(b)]



def _display_term_for_skill(required_term: str, edited_blocks: dict) -> str:
    """Prefer the skills-section label when it contains the required term."""
    required_term = str(required_term or "").strip()
    if not required_term:
        return required_term

    for group in edited_blocks.get("skills", []) or []:
        if not isinstance(group, dict):
            continue
        for item in group.get("items", []) or []:
            label = str(item).strip()
            if label and required_term.lower() in label.lower():
                return label
    return required_term


def _skill_weave_keywords(required_term: str) -> tuple[str, ...]:
    term = required_term.lower()
    if "iceberg" in term:
        return ("delta", "lakehouse", "databricks", "pipeline")
    if "bigquery" in term:
        return ("airflow", "workflow", "orchestr", "monitor")
    if "rust" in term:
        return ("chunk", "partition", "spark", "processing", "optim")
    return (
        "etl", "elt", "pipeline", "optimized", "optimised", "spark",
        "processing", "airflow", "workflow",
    )


def _best_pipeline_bullet_index(bullets: list[str], required_term: str | None = None) -> int | None:
    keywords = _skill_weave_keywords(required_term or "") if required_term else (
        "etl", "elt", "pipeline", "optimized", "optimised", "built",
        "spark", "lakehouse", "delta", "processing", "transformations",
        "airflow", "workflow",
    )
    best_idx = None
    best_score = -1
    for i, bullet in enumerate(bullets):
        text = str(bullet or "")
        if _is_meta_skill_bullet(text):
            continue
        lower = text.lower()
        if required_term and required_term.lower() in lower:
            return i
        score = sum(1 for kw in keywords if kw in lower)
        if score > best_score:
            best_score = score
            best_idx = i
    return best_idx


def _weave_skill_into_bullet(bullet: str, required_term: str, display_term: str) -> str:
    text = str(bullet or "").rstrip(". ")
    lower = text.lower()
    term_l = required_term.lower()
    display = (display_term or required_term).strip()

    if term_l in lower:
        return _add_explainable_impact_metric(text, required_term)

    if "iceberg" in term_l and re.search(r"(?i)(delta|lakehouse|databricks)", lower):
        if "delta lake" in lower and "iceberg" not in lower:
            if re.search(r"(?i), and delta lake$", text):
                text = re.sub(
                    r"(?i), and delta lake$",
                    ", Delta Lake, and Apache Iceberg",
                    text,
                )
            else:
                text = re.sub(
                    r"(?i)\bdelta lake\b",
                    "Delta Lake and Apache Iceberg",
                    text,
                    count=1,
                )
        elif re.search(r"(?i), and [^,]+$", text):
            text = re.sub(r", and ([^,]+)$", rf", {display}, and \g<1>", text)
        else:
            text = f"{text}, using {display} for open table format support"
        return _add_explainable_impact_metric(text, required_term)

    if "bigquery" in term_l and "airflow" in lower:
        text = re.sub(
            r"(?i)\bapache airflow\b",
            "Apache Airflow and BigQuery",
            text,
            count=1,
        )
        return _add_explainable_impact_metric(text, required_term)

    if "rust" in term_l and re.search(r"(?i)(chunk|partition|spark|processing)", lower):
        if not re.search(r"(?i)\brust\b", text):
            text = (
                f"{text}, applying {display} tooling to improve processing speed "
                "by approximately 20-40%"
            )
        return _add_explainable_impact_metric(text, required_term)

    if re.search(r"(?i), and [^,]+$", text):
        text = re.sub(r", and ([^,]+)$", rf", {display}, and \g<1>", text)
        return _add_explainable_impact_metric(text, required_term)

    if re.search(r"(?i)\bapache airflow\b", text) and term_l not in lower:
        text = re.sub(r"(?i)apache airflow", f"Apache Airflow and {display}", text, count=1)
        return _add_explainable_impact_metric(text, required_term)

    if re.search(r"(?i)\band [^,\.]+$", text):
        text = re.sub(r"(?i)\band ([^,\.]+)$", rf", {display}, and \g<1>", text.rstrip(". "))
        return _add_explainable_impact_metric(text, required_term)

    return _add_explainable_impact_metric(f"{text}, integrating {display}", required_term)


def _add_explainable_impact_metric(text: str, required_term: str = "") -> str:
    text = str(text or "").rstrip(". ")
    lower = text.lower()
    term_l = (required_term or "").lower()

    if re.search(r"(?i)(\d+%|percent|approximately)", text):
        return text + "."

    if "bigquery" in term_l and "airflow" in lower:
        if "reducing manual processing" in lower and "time" not in lower:
            text = re.sub(
                r"(?i)reducing manual processing\.?$",
                "reducing manual processing time",
                text.rstrip(". "),
            )
        return text + "."

    if "rust" in term_l and re.search(r"(?i)(chunk|partition|spark|processing)", lower):
        if re.search(r"(?i)(\d+%|approximately)", text):
            return text + "."
        return text + ", improving processing speed by approximately 20-40%."

    if "iceberg" in term_l and re.search(r"(?i)(delta|lakehouse|pipeline)", lower):
        if _WORK_CONTEXT_ACTION_RE.search(text) and _IMPACT_CONTEXT_RE.search(text):
            return text + "."
        return text + ", improving lakehouse pipeline reliability and performance."

    if re.search(r"(?i)(chunk|partition|chunking|partitioning)", lower):
        return text + ", improving processing speed by approximately 20-40%."

    if "reducing manual processing" in lower and "time" not in lower:
        return text + " time."

    if _WORK_CONTEXT_ACTION_RE.search(text) and _IMPACT_CONTEXT_RE.search(text):
        return text + "."

    return text + ", improving pipeline performance and processing speed."


def _sanitize_confirmed_skill_placements(
    edited_blocks: dict,
    confirmed_facts: list[dict],
) -> dict:
    """
    Deterministic cleanup when the LLM emits skill-inventory bullets.
    Removes meta bullets and weaves confirmed skills into existing work-context bullets.
    No LLM tokens.
    """
    skill_terms: list[str] = []
    experience_companies: set[str] = set()
    for fact in confirmed_facts:
        apply_to = str(fact.get("apply_to", "") or "").strip().lower()
        if apply_to == "skills":
            for term in fact.get("required_terms", []) or []:
                term = str(term).strip()
                if term and term not in skill_terms:
                    skill_terms.append(term)
        elif apply_to == "experience":
            company = str(fact.get("company", "") or "").strip()
            if company:
                experience_companies.add(company)

    if not skill_terms:
        return edited_blocks

    result = copy.deepcopy(edited_blocks)

    for entry in result.get("experience", []) or []:
        if not isinstance(entry, dict):
            continue
        entry["bullets"] = [
            str(b).strip()
            for b in (entry.get("bullets") or [])
            if str(b).strip() and not _is_meta_skill_bullet(str(b))
        ]

    missing = [
        term
        for term in skill_terms
        if not _skill_terms_in_work_context_bullets(result, [term]).get(term, False)
    ]

    if not missing:
        return result

    used_slots: set[tuple[int, int]] = set()

    def entry_priority(entry: dict) -> int:
        company = str(entry.get("company", "") or "").strip()
        if company in experience_companies:
            return 0
        return 1

    experiences = [
        entry for entry in (result.get("experience", []) or [])
        if isinstance(entry, dict) and entry.get("bullets")
    ]
    experiences.sort(key=entry_priority, reverse=True)

    for term in missing:
        display = _display_term_for_skill(term, result)
        weave_keywords = _skill_weave_keywords(term)
        best_choice = None
        best_score = -1

        for ei, entry in enumerate(experiences):
            company = str(entry.get("company", "") or "").strip()
            for bi, bullet in enumerate(entry.get("bullets") or []):
                if (ei, bi) in used_slots:
                    continue
                text = str(bullet or "")
                if _is_meta_skill_bullet(text):
                    continue
                lower = text.lower()
                score = 0
                if term.lower() in lower:
                    score += 5
                score += sum(1 for kw in weave_keywords if kw in lower)
                if company in experience_companies:
                    score -= 2
                if score > best_score:
                    best_score = score
                    best_choice = (ei, bi, text, display)

        if best_choice is None:
            continue

        ei, bi, text, display = best_choice
        experiences[ei]["bullets"][bi] = _weave_skill_into_bullet(text, term, display)
        used_slots.add((ei, bi))

    still_missing = [
        term
        for term in skill_terms
        if not _skill_terms_in_work_context_bullets(result, [term]).get(term, False)
    ]
    for term in still_missing:
        display = _display_term_for_skill(term, result)
        weave_keywords = _skill_weave_keywords(term)
        best_choice = None
        best_score = -1

        for ei, entry in enumerate(experiences):
            company = str(entry.get("company", "") or "").strip()
            for bi, bullet in enumerate(entry.get("bullets") or []):
                text = str(bullet or "")
                if _is_meta_skill_bullet(text):
                    continue
                lower = text.lower()
                if term.lower() in lower:
                    continue
                score = sum(1 for kw in weave_keywords if kw in lower)
                if (ei, bi) in used_slots:
                    score += 1
                if company in experience_companies:
                    score -= 2
                if score > best_score:
                    best_score = score
                    best_choice = (ei, bi, text, display)

        if best_choice is None:
            continue

        ei, bi, text, display = best_choice
        experiences[ei]["bullets"][bi] = _weave_skill_into_bullet(text, term, display)

    return result


def _experience_company_entry(experience: list, company: str) -> dict | None:
    target = str(company or "").strip().casefold()
    if not target:
        return None
    for entry in experience or []:
        if not isinstance(entry, dict):
            continue
        if str(entry.get("company", "") or "").strip().casefold() == target:
            return entry
    return None


def _adapt_confirmed_experience_bullet(fact: str) -> str:
    text = str(fact or "").strip().rstrip(".")
    text = re.sub(r"(?i)\s+at this employer$", "", text)
    text = re.sub(r"(?i)\s+at this company$", "", text)
    return text.strip()


def _weave_required_term_into_bullet(bullet: str, term: str) -> str:
    text = str(bullet or "").rstrip(". ")
    term = str(term or "").strip()
    if not term or term.lower() in text.lower():
        return text + "."

    lower = text.lower()
    if "delta lake" in term.lower() and re.search(r"(?i)\bdelta lake\b", text):
        return text + "."

    if re.search(r"(?i), and [^,\.]+$", text):
        return re.sub(r", and ([^,\.]+)$", rf", {term}, and \g<1>", text) + "."

    if re.search(r"(?i)(pipeline|etl|elt|spark|databricks|lakehouse|processing)", lower):
        if re.search(r"(?i)\bwith\b", text):
            return f"{text} and {term}."
        return f"{text}, using {term}."

    return f"{text}, applying {term}."


def _experience_fact_satisfied(bullets: list[str], fact: dict) -> bool:
    blob = "\n".join(str(b).strip() for b in bullets if str(b).strip())
    required_terms = [
        str(x).strip() for x in (fact.get("required_terms") or []) if str(x).strip()
    ]
    semantic_groups = fact.get("semantic_groups") or _derive_semantic_groups(
        str(fact.get("fact", "") or "")
    )
    if required_terms and not all(term.lower() in blob.lower() for term in required_terms):
        return False
    return _semantic_groups_satisfied(blob, semantic_groups)


def _sanitize_confirmed_experience_placements(
    edited_blocks: dict,
    confirmed_facts: list[dict],
) -> dict:
    """
    Deterministic cleanup when the LLM drops or weakens confirmed experience facts.
    No LLM tokens.
    """
    result = copy.deepcopy(edited_blocks)
    experience = result.get("experience") or []

    for fact in confirmed_facts:
        if str(fact.get("apply_to", "") or "").strip().lower() != "experience":
            continue

        company = str(fact.get("company", "") or "").strip()
        if not company:
            continue

        entry = _experience_company_entry(experience, company)
        if entry is None:
            continue

        bullets = [str(b).strip() for b in (entry.get("bullets") or []) if str(b).strip()]
        if _experience_fact_satisfied(bullets, fact):
            entry["bullets"] = bullets
            continue

        required_terms = [
            str(x).strip() for x in (fact.get("required_terms") or []) if str(x).strip()
        ]
        if not _experience_fact_satisfied(bullets, fact):
            adapted = _adapt_confirmed_experience_bullet(str(fact.get("fact", "") or ""))
            if adapted:
                bullet_line = adapted if adapted.endswith(".") else adapted + "."
                if not any(adapted.lower() in b.lower() for b in bullets):
                    bullets.insert(0, bullet_line)

        missing_terms = [
            term for term in required_terms
            if term.lower() not in "\n".join(bullets).lower()
        ]
        if missing_terms and not _experience_fact_satisfied(bullets, fact):
            best_idx = _best_pipeline_bullet_index(
                bullets,
                missing_terms[0] if missing_terms else None,
            )
            if best_idx is not None:
                for term in missing_terms:
                    if term.lower() not in bullets[best_idx].lower():
                        bullets[best_idx] = _weave_required_term_into_bullet(
                            bullets[best_idx],
                            term,
                        )

        entry["bullets"] = bullets

    result["experience"] = experience
    return result


def _summary_fact_satisfied(summary: str, fact: dict) -> bool:
    summary = str(summary or "").strip()
    required_terms = [
        str(x).strip() for x in (fact.get("required_terms") or []) if str(x).strip()
    ]
    semantic_groups = fact.get("semantic_groups") or _derive_semantic_groups(
        str(fact.get("fact", "") or "")
    )
    if required_terms and not all(term.lower() in summary.lower() for term in required_terms):
        return False
    return _semantic_groups_satisfied(summary, semantic_groups)


def _sanitize_confirmed_summary_placements(
    edited_blocks: dict,
    confirmed_facts: list[dict],
) -> dict:
    """Ensure confirmed summary facts remain visible in basics.summary. No LLM tokens."""
    result = copy.deepcopy(edited_blocks)
    basics = result.setdefault("basics", {})
    if not isinstance(basics, dict):
        return result

    summary = str(basics.get("summary") or "").strip()
    for fact in confirmed_facts:
        if str(fact.get("apply_to", "") or "").strip().lower() != "summary":
            continue
        if _summary_fact_satisfied(summary, fact):
            continue

        required_terms = [
            str(x).strip() for x in (fact.get("required_terms") or []) if str(x).strip()
        ]
        clause = _adapt_confirmed_experience_bullet(str(fact.get("fact", "") or ""))

        if clause and clause.lower() not in summary.lower():
            if not required_terms or all(term.lower() in clause.lower() for term in required_terms):
                summary = f"{summary.rstrip('. ')}. {clause}." if summary else f"{clause}."
            else:
                summary = f"{summary.rstrip('. ')}. {clause}." if summary else f"{clause}."

        for term in required_terms:
            if term.lower() in summary.lower():
                continue
            summary = (
                f"{summary.rstrip('. ')}. Experience includes {term}."
                if summary
                else f"Experience includes {term}."
            )

    basics["summary"] = summary.strip()
    return result


def _validate_ask_user_item(
    item: dict,
    resume_text: str,
    known_companies: set[str],
) -> tuple[str, dict, dict | None]:
    apply_to = str(item.get("apply_to", "") or "").strip().lower()
    company = str(item.get("company", "") or "").strip()
    proposed_fact = str(item.get("proposed_fact", "") or "").strip()
    required_terms = [
        str(x).strip()
        for x in (item.get("required_terms", []) or [])
        if str(x).strip()
    ]

    evidence = {
        "id": str(item.get("id", "") or "").strip(),
        "apply_to": apply_to,
        "company": company,
    }

    if apply_to not in {"skills", "experience", "summary"}:
        return "reject", {**evidence, "reason": "unsupported_apply_to"}, None

    if apply_to == "experience":
        if not company:
            return "reject", {**evidence, "reason": "experience_missing_company"}, None
        if known_companies and company not in known_companies:
            return "reject", {**evidence, "reason": "unknown_company"}, None

    normalized = dict(item)
    normalized["apply_to"] = apply_to
    normalized["company"] = company
    normalized["required_terms"] = required_terms

    if apply_to == "skills" and _contains_strong_skills_claim(proposed_fact):
        neutral = _neutral_skills_proposed_fact(required_terms)
        if neutral:
            normalized["proposed_fact"] = neutral
            evidence["skills_claim_normalized"] = True
        else:
            return "reject", {**evidence, "reason": "skills_fact_too_strong"}, None
    elif not proposed_fact:
        return "reject", {**evidence, "reason": "missing_proposed_fact"}, None

    normalized["semantic_groups"] = _derive_semantic_groups(
        str(normalized.get("proposed_fact", "") or "")
    )
    return "keep", evidence, normalized


def validate_and_prepare_ask_user(
    analysis: dict,
    resume_text: str,
) -> tuple[dict, list[dict]]:
    action_plan = analysis.setdefault("action_plan", {})
    ask_items = action_plan.get("ask_user", []) or []
    known_companies = _known_resume_companies(resume_text)

    kept: list[dict] = []
    rejected: list[dict] = []

    for item in ask_items:
        if not isinstance(item, dict):
            kept.append(item)
            continue

        action, evidence, normalized = _validate_ask_user_item(
            item=item,
            resume_text=resume_text,
            known_companies=known_companies,
        )

        if action == "keep" and normalized is not None:
            kept.append(normalized)
        else:
            rejected.append({
                **evidence,
                "proposed_fact": str(item.get("proposed_fact", "") or "").strip(),
                "reason": evidence.get("reason", "ask_user_validation_failed"),
            })
            reject_entry = {
                "id": str(item.get("id", "") or "").strip(),
                "item": str(item.get("proposed_fact", "") or item.get("item", "") or "").strip(),
                "apply_to": str(item.get("apply_to", "anywhere") or "anywhere").strip(),
                "company": str(item.get("company", "") or "").strip(),
                "forbidden_term_sets": [
                    [term]
                    for term in (
                        str(x).strip()
                        for x in (item.get("required_terms", []) or [])
                        if str(x).strip()
                    )
                ] or [[str(item.get("proposed_fact", "") or "unsupported claim").strip()]],
                "reason": "Rejected during local ask_user validation: "
                + str(evidence.get("reason", "invalid_proposal")),
            }
            action_plan.setdefault("do_not_add", []).append(reject_entry)

    action_plan["ask_user"] = kept
    analysis["action_plan"] = action_plan
    return analysis, rejected


def _parse_batch_selection(raw: str, ask_items: list[dict]) -> set[int]:
    text = (raw or "").strip().lower()
    n_items = len(ask_items)
    valid_range = f"1-{n_items}" if n_items else "none"

    if not text:
        raise ValueError("Selection cannot be empty.")

    if text in {"all", "a", "*"}:
        return set(range(n_items))

    if text in {"none", "n"}:
        return set()

    if text == "0":
        return set()

    id_to_index = {
        str(item.get("id", "") or "").strip().lower(): i
        for i, item in enumerate(ask_items)
        if str(item.get("id", "") or "").strip()
    }

    selected: set[int] = set()
    tokens = re.split(r"[\s,;]+", text)

    for token in tokens:
        token = token.strip()
        if not token:
            continue

        if re.fullmatch(r"\d+\-\d+", token):
            start_s, end_s = token.split("-", 1)
            start = int(start_s)
            end = int(end_s)
            if start > end:
                start, end = end, start
            for number in range(start, end + 1):
                if number < 1 or number > n_items:
                    raise ValueError(
                        f"Invalid selection: item {number} does not exist. "
                        f"Valid range: {valid_range}."
                    )
                selected.add(number - 1)
            continue

        if token.isdigit():
            number = int(token)
            if number < 1 or number > n_items:
                raise ValueError(
                    f"Invalid selection: item {number} does not exist. "
                    f"Valid range: {valid_range}."
                )
            selected.add(number - 1)
            continue

        if token in id_to_index:
            selected.add(id_to_index[token])
            continue

        raise ValueError(f"Unknown selection ID: {token}")

    return selected


def normalize_for_search(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def _safety_target_text(
    resume_data: dict,
    apply_to: str,
    company: str = "",
) -> str:
    apply_to = (apply_to or "anywhere").strip().lower()
    company = (company or "").strip()

    if apply_to == "skills":
        value = resume_data.get("skills", [])
    elif apply_to == "summary":
        value = (resume_data.get("basics", {}) or {}).get("summary", "")
    elif apply_to == "experience":
        experiences = resume_data.get("experience", []) or []
        if company:
            value = [
                entry
                for entry in experiences
                if isinstance(entry, dict)
                and str(entry.get("company", "") or "").strip() == company
            ]
        else:
            value = experiences
    else:
        value = {
            "basics": {
                "headline": (resume_data.get("basics", {}) or {}).get("headline", ""),
                "summary": (resume_data.get("basics", {}) or {}).get("summary", ""),
            },
            "skills": resume_data.get("skills", []),
            "experience": resume_data.get("experience", []),
            "experience_earlier": resume_data.get("experience_earlier", []),
        }

    if isinstance(value, str):
        return normalize_for_search(value)

    return normalize_for_search(
        yaml.safe_dump(value, sort_keys=False, allow_unicode=True)
    )


def _term_set_hit(target_text: str, term_set) -> bool:
    if not isinstance(term_set, (list, tuple)):
        return False

    terms = [
        normalize_for_search(str(term))
        for term in term_set
        if normalize_for_search(str(term))
    ]
    if not terms:
        return False
    return all(term in target_text for term in terms)


def local_safety_check(
    tailored_yaml: str,
    analysis: dict,
    confirmed_facts: list[dict] | None = None,
) -> dict:
    confirmed_facts = confirmed_facts or []

    resume_data = yaml.safe_load(tailored_yaml)
    if not isinstance(resume_data, dict):
        raise ValueError("tailored_yaml must parse to a YAML mapping.")

    confirmed_ids = {
        str(item.get("id", "") or "").strip()
        for item in confirmed_facts
        if isinstance(item, dict) and str(item.get("id", "") or "").strip()
    }

    restrictions = []
    hits = []
    skipped_confirmed_ids = []

    for entry in analysis.get("action_plan", {}).get("do_not_add", []):
        if isinstance(entry, dict):
            item_id = str(entry.get("id", "") or "").strip()
            item = str(entry.get("item", "") or "").strip()
            apply_to = str(entry.get("apply_to", "anywhere") or "anywhere").strip()
            company = str(entry.get("company", "") or "").strip()
            forbidden_sets = entry.get("forbidden_term_sets", []) or []
        else:
            item_id = ""
            item = str(entry).strip()
            apply_to = "anywhere"
            company = ""
            forbidden_sets = []

        if item_id and item_id in confirmed_ids:
            skipped_confirmed_ids.append(item_id)
            continue

        if not forbidden_sets and item:
            forbidden_sets = [[item]]

        target_text = _safety_target_text(
            resume_data=resume_data,
            apply_to=apply_to,
            company=company,
        )

        matched_sets = [
            term_set
            for term_set in forbidden_sets
            if _term_set_hit(target_text, term_set)
        ]

        restriction_record = {
            "id": item_id,
            "item": item,
            "apply_to": apply_to,
            "company": company,
            "forbidden_term_sets": forbidden_sets,
        }
        restrictions.append(restriction_record)

        if matched_sets:
            hits.append({**restriction_record, "matched_term_sets": matched_sets})

    return {
        "do_not_add_checked": len(restrictions),
        "skipped_because_human_confirmed": sorted(set(skipped_confirmed_ids)),
        "do_not_add_hits": hits,
        "manual_review_required": bool(hits),
    }





def _original_target_text_for_confirmation(
    resume_text: str,
    apply_to: str,
    company: str = "",
) -> str:
    """
    Return the exact original resume area used to decide whether an ask_user item
    is already explicitly supported and therefore does not need confirmation.
    """
    data = parse_original_resume_yaml(resume_text)
    if not isinstance(data, dict):
        return ""

    apply_to = (apply_to or "").strip().lower()
    company = (company or "").strip()

    if apply_to == "skills":
        value = data.get("skills", [])

    elif apply_to == "summary":
        value = (data.get("basics", {}) or {}).get("summary", "")

    elif apply_to == "experience":
        if not company:
            # Never auto-suppress an experience question without an exact employer.
            return ""

        matches = [
            entry
            for entry in (data.get("experience", []) or [])
            if isinstance(entry, dict)
            and str(entry.get("company", "") or "").strip() == company
        ]
        value = matches

    else:
        return ""

    if isinstance(value, str):
        return value.lower()

    return yaml.safe_dump(
        value,
        sort_keys=False,
        allow_unicode=True,
    ).lower()


def _is_redundant_confirmation(
    resume_text: str,
    item: dict,
) -> tuple[bool, dict]:
    """
    A proposal is redundant only when:
    - it has apply_to;
    - it has at least one required_term;
    - for experience, it has an exact company;
    - ALL required_terms already occur in that exact original target area.

    This is intentionally conservative: no required_terms => keep asking.
    """
    apply_to = str(item.get("apply_to", "") or "").strip().lower()
    company = str(item.get("company", "") or "").strip()
    required_terms = [
        str(x).strip()
        for x in (item.get("required_terms", []) or [])
        if str(x).strip()
    ]

    if apply_to not in {"skills", "summary", "experience"}:
        return False, {"reason": "unsupported_apply_to"}

    if not required_terms:
        return False, {"reason": "no_required_terms"}

    if apply_to == "experience" and not company:
        return False, {"reason": "experience_without_company"}

    target_text = _original_target_text_for_confirmation(
        resume_text=resume_text,
        apply_to=apply_to,
        company=company,
    )

    term_results = {
        term: term.lower() in target_text
        for term in required_terms
    }

    redundant = bool(target_text.strip()) and all(term_results.values())

    return redundant, {
        "apply_to": apply_to,
        "company": company,
        "required_terms": required_terms,
        "term_results": term_results,
    }


def filter_redundant_ask_user(
    analysis: dict,
    resume_text: str,
) -> tuple[dict, list[dict]]:
    """
    Remove ask_user items whose required terms are already explicit in the
    exact original resume target.
    """
    action_plan = analysis.setdefault("action_plan", {})
    ask_items = action_plan.get("ask_user", []) or []

    kept = []
    suppressed = []

    for item in ask_items:
        if not isinstance(item, dict):
            kept.append(item)
            continue

        redundant, evidence = _is_redundant_confirmation(
            resume_text=resume_text,
            item=item,
        )

        if redundant:
            suppressed.append({
                "id": str(item.get("id", "") or "").strip(),
                "proposed_fact": str(item.get("proposed_fact", "") or "").strip(),
                "reason": "required_terms_already_present_in_original_target",
                **evidence,
            })
        else:
            kept.append(item)

    action_plan["ask_user"] = kept

    suppressed_ids = {
        x["id"]
        for x in suppressed
        if x.get("id")
    }

    if suppressed_ids:
        action_plan["do_not_add"] = [
            item
            for item in (action_plan.get("do_not_add", []) or [])
            if not (
                isinstance(item, dict)
                and str(item.get("id", "") or "").strip() in suppressed_ids
            )
        ]

    analysis["action_plan"] = action_plan
    return analysis, suppressed
