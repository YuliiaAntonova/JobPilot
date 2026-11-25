"""Unit tests for L7 crew_tailoring adapters (no LLM / no CrewAI kickoff)."""

from __future__ import annotations

from unittest.mock import patch

from job_application.resume.crew_tailoring.adapter import build_crew_kickoff_inputs
from job_application.resume.crew_tailoring.cv_inputs import (
    extract_personal_writeup,
    synthesize_personal_writeup,
)
from job_application.resume.crew_tailoring.md_to_cv_json import (
    backfill_basics_contacts,
    l7_json_to_slim_cv,
)
from job_application.resume.crew_tailoring.resume_md import structured_to_resume_md
from job_application.resume.cv_schema import normalize_to_cv
from job_application.resume.safe_tailoring.orchestrator import run_analyze, run_generate


MINIMAL_CV = {
    "basics": {
        "name": "Jane Doe",
        "headline": "Obtain Data Engineer position",
        "location": "Berlin",
        "email": "jane@example.com",
        "phone": "+49 100",
        "summary": "Data engineer with Python and AWS.",
        "note": "",
        "links": [
            {"label": "GitHub", "text": "jane", "url": "https://github.com/jane"},
            {"label": "LinkedIn", "text": "jane", "url": "https://linkedin.com/in/jane"},
        ],
    },
    "skills": [{"group": "Languages", "items": ["Python", "SQL"]}],
    "experience": [
        {
            "company": "Acme",
            "title": "Data Engineer",
            "location": "Remote",
            "period": "2020–2024",
            "project_context": "Built ETL on AWS.",
            "bullets": ["Built ETL pipelines with Python."],
        }
    ],
    "experience_earlier": [],
    "projects": [{"name": "Side Project", "url": "", "bullets": ["Demo app"]}],
    "education": [],
    "certifications": [],
    "languages": [],
}

LONG_JD = (
    "Senior Data Engineer at Glimmer. Design data platforms, pipelines, "
    "and cloud infrastructure. Python, Spark, AWS Glue required. "
    "Join our European team building AI-first analytics."
)


def test_extract_personal_writeup_uses_summary():
    assert "Data engineer with Python" in extract_personal_writeup(MINIMAL_CV)


def test_synthesize_personal_writeup_without_summary():
    cv = {
        "basics": {"name": "Alex Smith", "headline": "ML Engineer", "summary": "", "note": ""},
        "skills": [{"group": "ML", "items": ["PyTorch", "Python"]}],
        "experience": [
            {
                "title": "ML Engineer",
                "company": "Co",
                "period": "2018–2024",
                "project_context": "Models in prod",
            }
        ],
    }
    text = synthesize_personal_writeup(cv)
    assert "Alex" in text
    assert "ML Engineer" in text


def test_structured_to_resume_md_has_sections():
    md = structured_to_resume_md(MINIMAL_CV)
    assert md.startswith("# Jane Doe")
    assert "## Skills" in md
    assert "## Experience" in md
    assert "jane@example.com" in md
    assert "https://github.com/jane" in md
    assert "## Selected Projects" in md


def test_build_crew_kickoff_inputs_mapping():
    out = build_crew_kickoff_inputs(structured=MINIMAL_CV, job_description=LONG_JD)
    assert set(out.keys()) >= {
        "personal_writeup",
        "job_posting_text",
        "resume_text",
        "cv",
    }
    assert out["job_posting_text"] == LONG_JD
    assert "# Jane Doe" in out["resume_text"]
    assert "Data engineer" in out["personal_writeup"]
    assert "github.com/jane" in out["github_url"]


def test_build_crew_kickoff_inputs_prepends_company_and_title():
    from job_application.resume.crew_tailoring.adapter import enrich_job_posting_text

    enriched = enrich_job_posting_text(
        LONG_JD,
        company_name="Glimmer",
        job_title="Data Engineer",
    )
    assert enriched.startswith("Company: Glimmer\nJob title: Data Engineer\n\n")
    assert LONG_JD in enriched

    out = build_crew_kickoff_inputs(
        structured=MINIMAL_CV,
        job_description=LONG_JD,
        company_name="Glimmer",
        job_title="Data Engineer",
    )
    assert out["company_name"] == "Glimmer"
    assert out["job_title"] == "Data Engineer"
    assert out["job_posting_text"].startswith("Company: Glimmer")


def test_apply_target_meta_replaces_company_placeholder():
    from job_application.resume.safe_tailoring.orchestrator import (
        _apply_target_meta_to_structured,
    )

    structured = {
        "basics": {
            "summary": "To obtain a Data Engineer position at [Company Name], where I can help.",
            "headline": "[Job Title]",
        }
    }
    _apply_target_meta_to_structured(
        structured,
        company_name="Glimmer",
        job_title="Data Engineer",
    )
    assert "[Company Name]" not in structured["basics"]["summary"]
    assert "Glimmer" in structured["basics"]["summary"]
    assert structured["basics"]["headline"] == "Data Engineer"


def test_backfill_basics_contacts_overwrites_placeholders():
    filled = {
        "basics": {
            "location": "[Your location]",
            "email": "",
            "phone": "your phone",
            "links": [{"label": "GitHub", "text": "x", "url": "https://example.com"}],
        }
    }
    backfill_basics_contacts(filled, MINIMAL_CV)
    assert filled["basics"]["location"] == "Berlin"
    assert filled["basics"]["email"] == "jane@example.com"
    assert filled["basics"]["links"][0]["url"] == "https://github.com/jane"


def test_normalize_and_render_prefer_link_labels():
    from job_application.resume.crew_tailoring.md_to_cv_json import (
        normalize_basics_link_labels,
    )
    from job_application.resume.pdf.render import link_display_text, render_header

    filled = {
        "basics": {
            "name": "Yuliia",
            "location": "Lengerich, Germany",
            "email": "a@b.com",
            "phone": "+49 1",
            "links": [
                {
                    "label": "Yuliia Antonova",
                    "text": "Yuliia Antonova",
                    "url": "https://www.linkedin.com/in/yuliia",
                },
                {
                    "label": "YuliiaAntonova",
                    "text": "YuliiaAntonova",
                    "url": "https://github.com/YuliiaAntonova",
                },
                {"label": None, "text": "yuliya25", "url": "https://www.xing.com/profile/yuliya25"},
            ],
        }
    }
    normalize_basics_link_labels(filled)
    labels = [ln["label"] for ln in filled["basics"]["links"]]
    assert labels == ["LinkedIn", "GitHub", "Xing"]

    html = render_header(filled["basics"])
    assert ">LinkedIn<" in html
    assert ">GitHub<" in html
    assert ">Xing<" in html
    assert ">YuliiaAntonova<" not in html
    assert ">yuliya25<" not in html
    assert link_display_text(filled["basics"]["links"][0]) == "LinkedIn"


def test_l7_json_selected_projects_maps_to_projects():
    filled = {
        "basics": {"name": "X"},
        "selected_projects": [{"name": "P1", "url": None, "bullets": ["a"]}],
        "certifications": [{"name": "AWS SAA", "issuer": "Amazon", "date": "2024"}],
    }
    slim = l7_json_to_slim_cv(filled)
    assert "selected_projects" not in slim or slim.get("projects")
    assert slim["projects"][0]["name"] == "P1"
    assert isinstance(slim["certifications"][0], str)
    assert "AWS" in slim["certifications"][0]


def test_normalize_to_cv_keeps_projects_after_l7_map():
    filled = {
        "basics": {
            "name": "Jane",
            "headline": "DE",
            "location": "Berlin",
            "email": "j@e.c",
            "phone": "",
            "summary": "x" * 20,
            "note": "",
            "links": [],
        },
        "skills": [],
        "experience": [],
        "experience_earlier": [],
        "selected_projects": [{"name": "P", "bullets": ["b"]}],
        "education": [],
        "certifications": [],
        "languages": [],
    }
    slim = l7_json_to_slim_cv(filled)
    cv = normalize_to_cv(slim)
    assert cv.get("projects") or cv.get("selected_projects")


def test_run_analyze_crew_l7_stashes_inputs(monkeypatch):
    monkeypatch.setenv("TAILORING_PIPELINE", "crew_l7")
    # Reload config-backed flag via orchestrator helper: patch _pipeline_mode
    with patch(
        "job_application.resume.safe_tailoring.orchestrator._pipeline_mode",
        return_value="crew_l7",
    ), patch(
        "job_application.resume.safe_tailoring.orchestrator.run_jobbert_match_score",
        return_value={"score": 0.5},
    ):
        out = run_analyze(
            job_description=LONG_JD,
            structured=MINIMAL_CV,
            include_jobbert=True,
        )
    assert out["phase"] == "ready_to_generate"
    assert out["ask_user"] == []
    assert out["analysis"]["pipeline"] == "crew_l7"
    assert "# Jane Doe" in out["analysis"]["resume_text"]
    assert out["analysis"]["personal_writeup"]
    assert out["jobbert_score_before"]["score"] == 0.5


def test_run_generate_crew_l7_mocked_kickoff(monkeypatch):
    monkeypatch.setenv("TAILORING_PIPELINE", "crew_l7")
    fixture_md = structured_to_resume_md(MINIMAL_CV)
    l7_shape = {
        "basics": {
            "name": "Jane Doe",
            "headline": "To obtain a Senior Data Engineer position at Glimmer",
            "location": "Berlin",
            "email": "jane@example.com",
            "phone": "+49 100",
            "summary": "To obtain a Senior Data Engineer position at Glimmer.",
            "note": None,
            "links": MINIMAL_CV["basics"]["links"],
        },
        "skills": [{"group": "Languages", "items": ["Python", "SQL"]}],
        "experience": MINIMAL_CV["experience"],
        "experience_earlier": [],
        "selected_projects": [{"name": "Side Project", "url": None, "bullets": ["Demo app"]}],
        "education": [],
        "certifications": [],
        "languages": [],
    }

    analysis = {
        "pipeline": "crew_l7",
        "personal_writeup": extract_personal_writeup(MINIMAL_CV),
        "resume_text": fixture_md,
        "job_posting_text": LONG_JD,
    }

    mock_crew_out = {
        "tailored_markdown": fixture_md,
        "tailored_structured": normalize_to_cv(l7_json_to_slim_cv(l7_shape)),
        "l7_json": l7_shape,
        "usage_calls": [
            {
                "step": "crew_l7_kickoff",
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
            }
        ],
        "model": "gpt-4o-mini",
    }

    with patch(
        "job_application.resume.safe_tailoring.orchestrator._pipeline_mode",
        return_value="crew_l7",
    ), patch(
        "job_application.resume.crew_tailoring.runner.run_crew_tailoring",
        return_value=mock_crew_out,
    ), patch(
        "job_application.resume.safe_tailoring.orchestrator.run_jobbert_match_score",
        return_value={"score": 0.7},
    ), patch(
        "job_application.resume.safe_tailoring.orchestrator._write_preview",
        return_value={"cv_html": "x.html", "cv_yml": "x.yml", "scope": "job_tailored_draft"},
    ):
        out = run_generate(
            job_description=LONG_JD,
            analysis=analysis,
            structured=MINIMAL_CV,
            include_jobbert=True,
        )

    assert out["phase"] == "done"
    assert out["safety_check"]["pipeline"] == "crew_l7"
    assert out["cover_letter"] == ""
    assert out["tailored_structured"]["basics"]["name"] == "Jane Doe"
    assert out["tailored_resume_text"]
    assert out["cv_preview"]["scope"] == "job_tailored_draft"
    assert out["jobbert_score_after"]["score"] == 0.7
    assert out["token_usage"]["operation"] == "crew_l7_generate"
