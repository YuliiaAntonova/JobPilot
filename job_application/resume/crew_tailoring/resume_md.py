"""Export structured CV to filled_cv.md-style Markdown (from crew_job/render.cv_to_markdown)."""

from __future__ import annotations

from typing import Any


def _visible(entry: dict, variant: str | None) -> bool:
    if not variant:
        return True
    tag = entry.get("variant")
    if not tag:
        return True
    tags = [tag] if isinstance(tag, str) else list(tag)
    return variant in tags


def _join_meta(*parts: object) -> str:
    return " · ".join(str(p).strip() for p in parts if p)


def _project_list(cv: dict[str, Any]) -> list[dict[str, Any]]:
    """Prefer selected_projects (L7), fall back to slim projects."""
    raw = cv.get("selected_projects")
    if not isinstance(raw, list) or not raw:
        raw = cv.get("projects") or []
    return [p for p in raw if isinstance(p, dict)]


def structured_to_resume_md(cv: dict[str, Any], *, variant: str | None = None) -> str:
    """Convert filled CV JSON dict to a readable Markdown string (L7 filled_cv.md style)."""
    lines: list[str] = []
    b = cv.get("basics") or {}
    name = b.get("name") or "Resume"
    lines.append(f"# {name}")
    lines.append("")
    if b.get("headline"):
        lines.append(f"**{b['headline']}**")
        lines.append("")
    meta = _join_meta(b.get("location"), b.get("email"), b.get("phone"))
    if meta:
        lines.append(meta)
        lines.append("")
    for link in b.get("links") or []:
        if not isinstance(link, dict):
            continue
        label = link.get("label") or link.get("text") or "Link"
        url = link.get("url") or ""
        if url:
            lines.append(f"- [{label}]({url})")
    if b.get("links"):
        lines.append("")
    if b.get("summary"):
        lines.append(str(b["summary"]).strip())
        lines.append("")

    skills = cv.get("skills") or []
    if skills:
        lines.append("## Skills")
        lines.append("")
        for group in skills:
            if not isinstance(group, dict):
                continue
            title = group.get("group") or "Skills"
            items = group.get("items") or []
            if items:
                lines.append(f"**{title}:** {', '.join(str(i) for i in items)}")
                lines.append("")

    experience = [
        e for e in (cv.get("experience") or []) if isinstance(e, dict) and _visible(e, variant)
    ]
    if experience:
        lines.append("## Experience")
        lines.append("")
        for job in experience:
            title = job.get("title") or job.get("role") or "Role"
            company = job.get("company") or ""
            heading = f"### {title}" + (f" — {company}" if company else "")
            lines.append(heading)
            meta = _join_meta(job.get("period"), job.get("location"))
            if meta:
                lines.append(f"*{meta}*")
                lines.append("")
            ctx = job.get("project_context") or job.get("context")
            if ctx:
                lines.append(str(ctx).strip())
                lines.append("")
            for bullet in job.get("bullets") or []:
                lines.append(f"- {bullet}")
            lines.append("")

    earlier = cv.get("experience_earlier") or []
    if earlier:
        lines.append("## Earlier Experience")
        lines.append("")
        for job in earlier:
            if not isinstance(job, dict):
                continue
            stack = job.get("stack") or []
            stack_s = f" ({', '.join(str(s) for s in stack)})" if stack else ""
            role = job.get("role") or job.get("title") or ""
            company = job.get("company") or ""
            period = job.get("period") or ""
            lines.append(f"- **{period}** — {role}, {company}{stack_s}".rstrip(" ,"))
        lines.append("")

    projects = [p for p in _project_list(cv) if _visible(p, variant)]
    if projects:
        lines.append("## Selected Projects")
        lines.append("")
        for proj in projects:
            pname = proj.get("name") or "Project"
            url = proj.get("url")
            lines.append(f"### [{pname}]({url})" if url else f"### {pname}")
            lines.append("")
            for bullet in proj.get("bullets") or []:
                lines.append(f"- {bullet}")
            lines.append("")

    education = cv.get("education") or []
    if education:
        lines.append("## Education")
        lines.append("")
        for edu in education:
            if not isinstance(edu, dict):
                continue
            degree = edu.get("degree") or ""
            school = edu.get("school") or ""
            period = edu.get("period")
            note = edu.get("note")
            line = f"- **{degree}** — {school}" if school else f"- **{degree}**"
            if period:
                line += f", {period}"
            if note:
                line += f" ({note})"
            lines.append(line)
        lines.append("")

    certs = cv.get("certifications") or []
    if certs:
        lines.append("## Certifications")
        lines.append("")
        for c in certs:
            lines.append(f"- {c}")
        lines.append("")

    languages = cv.get("languages") or []
    if languages:
        lines.append("## Languages")
        lines.append("")
        for lang in languages:
            if isinstance(lang, dict):
                lines.append(f"- **{lang.get('name', '')}** — {lang.get('level', '')}")
            else:
                lines.append(f"- {lang}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
