"""Tailored resume save: plain text, PDF structured, desired role dedupe."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from job_application.documents.resume_normalize import normalize_structured_for_render
from job_application.resume.profile_service import (
    _structured_for_scoring_from_profile,
    normalize_tailored_profile_text,
    structured_for_render_from_profile,
    update_profile_plain_text,
)
from job_application.config import RESUME_PLAIN_TEXT_KEY


class TestTailoredProfile(unittest.TestCase):
    def test_normalize_strips_duplicate_desired_role(self):
        text = "Experience line\n\nDesired role: Sr Data Engineer\n\nDesired role: Data engineer"
        clean, role = normalize_tailored_profile_text(text, fallback_desired_role="Old")
        self.assertEqual(role, "Data engineer")
        self.assertNotIn("Desired role:", clean)
        self.assertIn("Experience line", clean)

    def test_pdf_render_prefers_structured_when_tailored(self):
        prof = MagicMock()
        prof.source = "tailored"
        prof.structured = {
            "_resume_plain_text": "Tailored plain",
            "experience": [{"title": "New Job", "company": "Co", "highlights": ["Data Governance"]}],
        }
        prof.chat_answers = {
            "fullName": "Test",
            "email": "t@e.c",
            "job_1_result": "Old chat job text",
        }
        rendered = structured_for_render_from_profile(prof)
        self.assertEqual(rendered.get("_resume_plain_text"), "Tailored plain")
        self.assertEqual(rendered["experience"][0]["title"], "New Job")

    def test_tailored_save_keeps_pdf_plain_and_experience_bullets(self):
        original_plain = (
            "Big Data Engineer. Trinetix. February 2024 - Current\n"
            "Manage data flow through all layers.\n"
            "Work with Step Functions to orchestrate Glue Jobs and automate daily pipelines.\n"
            "Work with Aurora (AppData/OLTP) and OpenSearch for data storage and querying.\n"
        )
        scrambled_tailored = (
            "Manage data flow through all layers: Ingestion → Raw → Derived → Datamart.\n"
            "Work with Step Functions to orchestration tools daily pipelines.\n"
            "Data Modeling and schemas optimised for analytics;\n"
        )
        stored_structured = {
            RESUME_PLAIN_TEXT_KEY: original_plain,
            "_experience_baseline": [
                {
                    "title": "Big Data Engineer",
                    "company": "Trinetix",
                    "dates": "February 2024 - Current",
                    "highlights": [
                        "Manage data flow through all layers: Ingestion → Raw → Derived → Datamart.",
                        "Work with Step Functions to orchestrate Glue Jobs and automate daily pipelines.",
                        "Work with Aurora (AppData/OLTP) and OpenSearch for data storage and querying.",
                    ],
                },
                {
                    "title": "Data Engineer",
                    "company": "Self-employed",
                    "dates": "August 2023-February 2024",
                    "highlights": [
                        "Implemented and managed ETL processes for data integration",
                        "Developed and implemented data models and schemas optimised for analytics",
                        "Monitoring and troubleshooted system performance and data issues.",
                    ],
                },
            ],
            "experience": [
                {
                    "title": "Big Data Engineer",
                    "company": "Trinetix",
                    "dates": "February 2024 - Current",
                    "highlights": [
                        "Manage data flow through all layers: Ingestion → Raw → Derived → Datamart.",
                        "Work with Step Functions to orchestrate Glue Jobs and automate daily pipelines.",
                        "Work with Aurora (AppData/OLTP) and OpenSearch for data storage and querying.",
                    ],
                },
                {
                    "title": "Data Engineer",
                    "company": "Self-employed",
                    "dates": "August 2023-February 2024",
                    "highlights": [
                        "Implemented and managed ETL processes for data integration",
                        "Developed and implemented data models and schemas optimised for analytics",
                        "Monitoring and troubleshooted system performance and data issues.",
                    ],
                },
            ],
        }
        row = MagicMock()
        row.structured = stored_structured
        row.chat_answers = {"fullName": "Yuliia Antonova"}
        row.desired_role = "Data Engineer"
        row.profile_text = original_plain

        ats = [
            {
                "resume_phrase": "data storage and querying",
                "jd_phrase": "Data Platforms",
                "match_type": "phrase_semantic",
                "similarity": 0.7,
            },
            {
                "resume_phrase": "data models",
                "jd_phrase": "Data Modeling",
                "match_type": "phrase_semantic",
                "similarity": 0.8,
            },
        ]

        with patch("job_application.resume.profile_service.db_users") as db_users:
            db_users.get_profile_for_user.return_value = row
            db_users.upsert_profile.side_effect = lambda _db, _uid, **kwargs: MagicMock(**kwargs)

            update_profile_plain_text(
                MagicMock(),
                "user-1",
                scrambled_tailored * 5,
                reparse_structured=False,
                ats_substitutions=ats,
            )

            saved = db_users.upsert_profile.call_args.kwargs
            self.assertEqual(saved["structured"][RESUME_PLAIN_TEXT_KEY], original_plain)
            from job_application.resume.profile_text import _job_highlights

            trinetix = _job_highlights(saved["structured"]["experience"][0])
            self.assertEqual(len(trinetix), 3)
            self.assertIn("Data Platforms", trinetix[-1])
            self_emp = _job_highlights(saved["structured"]["experience"][1])
            self.assertIn("Data Modeling", self_emp[1])
            self.assertIn("EXPERIENCE", saved["profile_text"])
            self.assertIn("Data Platforms", saved["profile_text"])

            norm = normalize_structured_for_render(saved["structured"])
            norm_trinetix = _job_highlights(norm["experience"][0])
            self.assertEqual(len(norm_trinetix), 3)
            self.assertIn("Data Platforms", norm_trinetix[-1])

    def test_llm_tailored_save_keeps_submitted_plain_for_scoring(self):
        llm_plain = (
            "Yuliia Antonova\nData Engineer\n\n"
            "EXPERIENCE\n"
            "Trinetix — Built PySpark ETL pipelines with Airflow orchestration and AWS Glue.\n"
            "Added Spark Structured Streaming and Kafka ingestion for real-time analytics.\n\n"
            "SKILLS\nPython, PySpark, Airflow, AWS Glue, Kafka, SQL\n"
        )
        row = MagicMock()
        row.structured = {
            RESUME_PLAIN_TEXT_KEY: "Old PDF extract " * 20,
            "experience": [
                {
                    "title": "Big Data Engineer",
                    "company": "Trinetix",
                    "highlights": ["Work with Step Functions to orchestrate Glue Jobs."],
                }
            ],
            "skills": ["Python", "SQL"],
        }
        row.chat_answers = {"fullName": "Yuliia Antonova"}
        row.desired_role = "Data Engineer"
        row.profile_text = "Old PDF extract " * 20

        captured: dict = {}

        def _capture(_db, _uid, **kwargs):
            captured.update(kwargs)
            return MagicMock(**kwargs)

        with patch("job_application.resume.profile_service.db_users") as db_users:
            db_users.get_profile_for_user.return_value = row
            db_users.upsert_profile.side_effect = _capture
            update_profile_plain_text(MagicMock(), "user-1", llm_plain, reparse_structured=False)

        self.assertIn("Airflow orchestration", captured["profile_text"])
        self.assertIn("Kafka", captured["profile_text"])
        self.assertEqual(captured["structured"][RESUME_PLAIN_TEXT_KEY], llm_plain.strip())
        self.assertIn("Kafka", captured["chat_answers"][RESUME_PLAIN_TEXT_KEY])

    def test_tailored_save_uses_harvard_template(self):
        from job_application.resume.profile_service import update_profile_plain_text
        from unittest.mock import MagicMock, patch

        row = MagicMock()
        row.structured = {
            "resume_template": "hursh",
            "_resume_plain_text": "SKILLS & ACCOMPLISHMENT\nPROFESSIONAL EXPERIENCE\n",
            "experience": [
                {
                    "company": "Trinetix",
                    "title": "Big Data Engineer",
                    "highlights": ["Work with Step Functions to orchestrate Glue Jobs and automate daily pipelines."],
                }
            ],
        }
        row.chat_answers = {}
        row.desired_role = "Data Engineer"
        row.profile_text = "x" * 200

        captured: dict = {}

        def _capture(_db, _uid, **kwargs):
            captured.update(kwargs)
            return MagicMock(**kwargs)

        with patch("job_application.resume.profile_service.db_users") as db_users:
            db_users.get_profile_for_user.return_value = row
            db_users.upsert_profile.side_effect = _capture
            update_profile_plain_text(MagicMock(), "user-1", "x" * 200, reparse_structured=False)

        self.assertEqual(captured["structured"].get("resume_template"), "harvard")

    def test_render_pdf_uses_workshop_renderer(self):
        from job_application.application.export_service import ExportService
        from job_application.resume.profile_router import RenderResumeBody, _structured_from_render_body

        stored = {
            "resume_template": "yuliia",
            "_resume_plain_text": "Y U L I I A\nA N T O N O V A\nOBJECTIVE\nSKILLS\nEXPERIENCE",
            "experience": [
                {
                    "title": "Big Data Engineer",
                    "company": "Trinetix",
                    "highlights": [
                        "Work with Step Functions to use orchestration tools for Glue Jobs and automate daily pipelines.",
                    ],
                }
            ],
        }
        body = RenderResumeBody(
            structured=stored,
            chat_answers={
                "job_0_description": "Work with Step Functions to orchestrate Glue Jobs and automate daily pipelines.",
                "job_0_company": "Trinetix",
                "job_0_roleAndDates": "Big Data Engineer, 2024 - Current",
            },
        )
        rendered = _structured_from_render_body(body)
        self.assertEqual(rendered.get("resume_template"), "harvard")
        renderer = ExportService()._pick_renderer(rendered, template=None)
        self.assertEqual(renderer.name, "workshop")

    def test_render_pdf_prefers_structured_over_stale_chat_answers(self):
        from job_application.resume.profile_router import _structured_from_render_body
        from job_application.resume.profile_router import RenderResumeBody

        body = RenderResumeBody(
            structured={
                "experience": [
                    {
                        "title": "Big Data Engineer",
                        "company": "Trinetix",
                        "highlights": [
                            "Work with Step Functions to use orchestration tools for Glue Jobs and automate daily pipelines.",
                        ],
                    }
                ]
            },
            chat_answers={
                "job_0_description": "Work with Step Functions to orchestrate Glue Jobs and automate daily pipelines.",
                "job_0_raw_description": "Work with Step Functions to orchestrate Glue Jobs and automate daily pipelines.",
            },
        )
        rendered = _structured_from_render_body(body)
        bullet = rendered["experience"][0]["highlights"][0]
        self.assertIn("use orchestration tools for Glue Jobs", bullet)
        self.assertNotIn("orchestrate Glue Jobs", bullet)

    def test_plain_text_prefers_experience_highlights_over_stale_experience_text(self):
        from job_application.resume.profile_text import structured_profile_to_plain_text

        structured = {
            "personal": {"full_name": "Yuliia Antonova"},
            "_keep_stored_experience_bullets": True,
            "experience_text": (
                "Big Data Engineer | Trinetix\n"
                "- Work with Step Functions to orchestrate Glue Jobs and automate daily pipelines."
            ),
            "experience": [
                {
                    "title": "Big Data Engineer",
                    "company": "Trinetix",
                    "dates": "2024 - Current",
                    "highlights": [
                        "Work with Step Functions to use orchestration tools for Glue Jobs and automate daily pipelines.",
                    ],
                }
            ],
        }
        plain = structured_profile_to_plain_text(structured)
        self.assertIn("use orchestration tools for Glue Jobs", plain)
        self.assertNotIn("orchestrate Glue Jobs", plain)

    def test_sync_job_narrative_fields_for_pdf_export(self):
        from job_application.resume.profile_service import _sync_job_narrative_fields
        from job_application.resume.profile_text import _job_highlights

        job = _sync_job_narrative_fields(
            {
                "company": "Trinetix",
                "highlights": [
                    "Work with Aurora (AppData/OLTP) and OpenSearch for Data Platforms",
                ],
                "responsibilities": [
                    "Work with Aurora (AppData/OLTP) and OpenSearch for data storage and querying.",
                ],
                "summary": "Work with Aurora (AppData/OLTP) and OpenSearch for data storage and querying.",
            }
        )
        bullets = _job_highlights(job)
        self.assertEqual(len(bullets), 1)
        self.assertIn("Data Platforms", bullets[0])
        self.assertNotIn("storage and querying", bullets[0])

    def test_ats_finalize_drops_original_when_jd_present(self):
        from job_application.resume.profile_service import _finalize_highlight_bullets

        bullets = [
            "Work with Aurora (AppData/OLTP) and OpenSearch for Data Platforms",
            "Work with Aurora (AppData/OLTP) and OpenSearch for data storage and querying.",
            "Work with Aurora (AppData/OLTP) and OpenSearch for Data Platforms",
        ]
        ats = [
            {
                "resume_phrase": "data storage and querying",
                "jd_phrase": "Data Platforms",
                "match_type": "phrase_semantic",
                "similarity": 0.7,
            }
        ]
        out = _finalize_highlight_bullets(bullets, ats_substitutions=ats)
        self.assertEqual(len(out), 1)
        self.assertIn("Data Platforms", out[0])
        self.assertNotIn("storage and querying", out[0])

    def test_save_without_ats_keeps_prior_jd_wording(self):
        from job_application.resume.profile_service import _merge_experience_keep_richest

        baseline = [
            {
                "company": "Trinetix",
                "highlights": [
                    "Work with Aurora (AppData/OLTP) and OpenSearch for data storage and querying.",
                ],
            }
        ]
        current = [
            {
                "company": "Trinetix",
                "highlights": [
                    "Work with Aurora (AppData/OLTP) and OpenSearch for Data Platforms",
                ],
            }
        ]
        without_baseline = _merge_experience_keep_richest(current, ats_substitutions=None)
        self.assertIn("Data Platforms", without_baseline[0]["highlights"][0])

        with_baseline = _merge_experience_keep_richest(baseline, current, ats_substitutions=None)
        self.assertIn("Data Platforms", with_baseline[0]["highlights"][0])

    def test_repeated_save_keeps_all_baseline_bullets(self):
        from job_application.resume.profile_service import (
            EXPERIENCE_BASELINE_KEY,
            _merge_experience_keep_richest,
        )

        baseline = [
            {
                "company": "Trinetix",
                "title": "Big Data Engineer",
                "highlights": ["a", "b", "c"],
            }
        ]
        corrupted = [{"company": "Trinetix", "title": "Big Data Engineer", "highlights": ["a", "bad"]}]
        merged = _merge_experience_keep_richest(baseline, corrupted)
        self.assertEqual(len(merged[0]["highlights"]), 3)

    def test_scoring_structured_matches_tailored_not_stale_chat(self):
        prof = MagicMock()
        prof.source = "tailored"
        prof.structured = {
            "_resume_plain_text": "Tailored plain",
            "skills": ["Python", "SQL", "data pipelines"],
            "experience": [{"title": "New Job", "company": "Co", "highlights": ["modern data pipelines"]}],
        }
        prof.chat_answers = {
            "fullName": "Test",
            "email": "t@e.c",
            "mainTechStack": "Python only",
        }
        scoring = _structured_for_scoring_from_profile(prof)
        self.assertIn("data pipelines", scoring.get("skills") or [])


if __name__ == "__main__":
    unittest.main()
