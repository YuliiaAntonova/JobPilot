"""Skills merge from notebook flat list → Harvard groups (no duplication)."""

from __future__ import annotations

from job_application.resume.notebook_tailoring.cv_bridge import (
    _redistribute_flat_skills_to_groups,
    apply_notebook_resume_to_cv,
)


def test_flat_skills_redistributed_not_duplicated_in_first_group():
    original_groups = [
        {"group": "AI & RAG", "items": ["RAG Patterns", "Python"]},
        {"group": "Cloud", "items": ["Azure Databricks", "AWS Glue"]},
    ]
    flat = [
        "RAG Patterns",
        "Agentic AI Systems",
        "Python",
        "Azure Databricks",
        "AWS Glue",
        "PySpark",
    ]
    out = _redistribute_flat_skills_to_groups(flat, original_groups)
    assert len(out) == 2
    assert out[0]["group"] == "AI & RAG"
    assert "Agentic AI Systems" in out[0]["items"]
    assert "PySpark" in out[0]["items"]  # new skill → first group
    assert "Azure Databricks" in out[1]["items"]
    all_items = [it for g in out for it in g["items"]]
    assert len(all_items) == len(set(i.lower() for i in all_items))


def test_apply_notebook_preserves_experience_context_and_skips_new_projects():
    structured = {
        "basics": {"name": "Test User", "headline": "Engineer"},
        "skills": [{"group": "Tech", "items": ["Python"]}],
        "experience": [
            {
                "company": "Acme Corp",
                "title": "Data Engineer",
                "period": "2024 – Present",
                "bullets": ["Did data work"],
                "context": "Platform modernization program",
            }
        ],
    }
    notebook = {
        "work_experience": [
            {
                "company": "Acme Corp",
                "title": "Data Engineer",
                "duration": "2024 – Present",
                "achievements": ["Did tailored data work"],
            }
        ],
        "skills": ["Python", "SQL"],
        "projects": [{"title": "Extra Project", "description": "Should not appear"}],
    }
    merged = apply_notebook_resume_to_cv(structured, notebook)
    assert merged["experience"][0].get("context") == "Platform modernization program"
    assert "projects" not in merged
