"""Unit tests for safe YAML resume tailoring orchestrator."""

from __future__ import annotations

import yaml

from job_application.resume.safe_tailoring.orchestrator import (
    confirmed_facts_from_selection,
    structured_to_resume_yaml_text,
)
from job_application.resume.safe_tailoring import _core as core


MINIMAL_CV = {
    "basics": {
        "name": "Test User",
        "headline": "Engineer",
        "location": "Berlin",
        "email": "t@example.com",
        "phone": "",
        "summary": "Data engineer with Python.",
        "note": "",
        "links": [],
    },
    "skills": [{"group": "Languages", "items": ["Python"]}],
    "experience": [
        {
            "company": "Acme",
            "title": "DE",
            "location": "Remote",
            "period": "2020–2024",
            "bullets": ["Built ETL pipelines with Python."],
        }
    ],
    "experience_earlier": [],
    "education": [],
    "certifications": [],
    "languages": [],
}


def test_structured_to_resume_yaml_text_roundtrip():
    text = structured_to_resume_yaml_text(MINIMAL_CV)
    parsed = yaml.safe_load(text)
    assert isinstance(parsed, dict)
    assert parsed["basics"]["name"] == "Test User"


def test_confirmed_facts_from_selection_by_id():
    ask_items = [
        {
            "id": "snowflake",
            "proposed_fact": "Snowflake is part of the candidate's technical skill set.",
            "apply_to": "skills",
            "required_terms": ["Snowflake"],
        },
        {
            "id": "rust_exp",
            "proposed_fact": "Used Rust for data tooling.",
            "apply_to": "experience",
            "company": "Acme",
            "required_terms": ["Rust"],
        },
    ]
    facts, events = confirmed_facts_from_selection(ask_items, ["snowflake"])
    assert len(facts) == 1
    assert facts[0]["id"] == "snowflake"
    assert any(e["type"] == "fact_confirmed" for e in events)
    assert any(e["type"] == "fact_rejected" for e in events)


def test_unknown_applied_ids_allows_auto_apply():
    confirmed = [
        {
            "id": "snowflake",
            "fact": "Snowflake is part of the candidate's technical skill set.",
            "apply_to": "skills",
            "required_terms": ["Snowflake"],
            "semantic_groups": [["snowflake"]],
        }
    ]
    edited = {
        "basics": {"summary": "Snowflake and Python."},
        "skills": [{"group": "Tools", "items": ["Snowflake", "Python"]}],
        "experience": [
            {
                "company": "Acme",
                "title": "DE",
                "location": "",
                "period": "",
                "bullets": ["Built Snowflake loads with Python."],
            }
        ],
    }
    analysis = {
        "action_plan": {
            "auto_apply": [
                {"id": "summary_reframe", "section": "summary", "instruction": "tighten summary"},
            ]
        }
    }
    audit = core._validate_confirmed_facts_in_sections(
        edited_blocks=edited,
        confirmed_facts=confirmed,
        applied_ids={"snowflake", "summary_reframe"},
        extra_allowed_applied_ids=core._collect_auto_apply_ids(analysis),
    )
    assert audit["unknown_applied_ids"] == []


def test_normalize_applied_ids_case_insensitive():
    confirmed = [{"id": "Snowflake_Skill", "fact": "x", "apply_to": "skills", "required_terms": ["Snowflake"]}]
    normalized = core._normalize_applied_ids({"snowflake_skill"}, confirmed)
    assert normalized == {"Snowflake_Skill"}


def test_filter_redundant_ask_user_removes_already_present_skill():
    resume_yaml = structured_to_resume_yaml_text(MINIMAL_CV)
    analysis = {
        "action_plan": {
            "ask_user": [
                {
                    "id": "python_skill",
                    "proposed_fact": "Python is part of the candidate's technical skill set.",
                    "apply_to": "skills",
                    "required_terms": ["Python"],
                }
            ],
            "do_not_add": [
                {"id": "python_skill", "item": "fake python claim", "apply_to": "skills"},
            ],
        }
    }
    filtered, suppressed = core.filter_redundant_ask_user(analysis, resume_yaml)
    assert filtered["action_plan"]["ask_user"] == []
    assert len(suppressed) == 1
