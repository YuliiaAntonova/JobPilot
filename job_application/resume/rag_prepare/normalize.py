"""Map RAG/L7 CV JSON keys onto slim Harvard cv.yml shape (no CrewAI import)."""

from __future__ import annotations

from typing import Any


def _cert_to_scalar(item: Any) -> str:
    if isinstance(item, str):
        return item.strip()
    if not isinstance(item, dict):
        return str(item)
    name = str(item.get("name") or item.get("title") or "").strip()
    issuer = str(item.get("issuer") or item.get("organization") or "").strip()
    when = str(
        item.get("date")
        or item.get("year")
        or item.get("period")
        or item.get("issued")
        or ""
    ).strip()
    parts = [p for p in (name, issuer, when) if p]
    return " — ".join(parts) if parts else str(item)


def l7_json_to_slim_cv(filled: dict[str, Any]) -> dict[str, Any]:
    """Map L7/RAG template keys (selected_projects) onto slim cv.yml."""
    data = dict(filled)
    selected = data.pop("selected_projects", None)
    projects = data.get("projects")
    if isinstance(selected, list) and selected:
        if not isinstance(projects, list) or not projects:
            data["projects"] = selected
    certs = data.get("certifications")
    if isinstance(certs, list):
        data["certifications"] = [_cert_to_scalar(x) for x in certs if x is not None]
    return data
