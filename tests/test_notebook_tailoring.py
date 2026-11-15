"""Unit tests for Untitled.ipynb tailoring helpers (no LLM)."""

from __future__ import annotations

from job_application.resume.notebook_tailoring.pipeline import flatten_skills, get_skill_match_score
from job_application.resume.notebook_tailoring.cv_bridge import apply_notebook_resume_to_cv


def test_get_skill_match_score_partial_overlap():
    score, matched, missing = get_skill_match_score(
        ["Python", "SQL", "Tableau"],
        ["Python", "TensorFlow", "SQL"],
    )
    assert score > 66.0
    assert "Python" in matched
    assert "TensorFlow" in missing


def test_flatten_skills_dict():
    assert flatten_skills({"Technical": ["Python", "SQL"], "Soft": "Communication"}) == [
        "Python",
        "SQL",
        "Communication",
    ]


def test_apply_notebook_resume_to_cv_merges_experience():
    original = {
        "basics": {"name": "Jane Doe", "headline": "DS", "email": "j@e.c"},
        "skills": [{"group": "Lang", "items": ["Python"]}],
        "experience": [
            {
                "company": "OldCo",
                "title": "Analyst",
                "period": "2020–2022",
                "bullets": ["Did stuff"],
            }
        ],
        "education": [],
    }
    notebook = {
        "name": "Jane Doe",
        "work_experience": [
            {
                "company": "NewCo",
                "title": "Data Scientist",
                "duration": "2022–Present",
                "achievements": ["Built ML models", "Shipped dashboards"],
            }
        ],
        "skills": ["Python", "SQL", "TensorFlow"],
    }
    out = apply_notebook_resume_to_cv(original, notebook)
    assert out["experience"][0]["company"] == "NewCo"
    assert len(out["experience"][0]["bullets"]) == 2
    assert out["skills"][0]["group"] == "Lang"
    assert out["skills"][0]["items"] == ["Python", "SQL", "TensorFlow"]
