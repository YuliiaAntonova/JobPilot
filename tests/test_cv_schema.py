"""Tests for cv.yml schema (chat ↔ DB structured)."""

from __future__ import annotations

import unittest

from job_application.resume.cv_schema import (
    chat_answers_to_cv,
    cv_to_chat_answers,
    is_cv_structured,
    migrate_interests_from_note,
    normalize_to_cv,
)
from job_application.resume.profile_text import chat_answers_to_structured, structured_to_chat_answers


class TestCvSchema(unittest.TestCase):
    def test_chat_answers_to_cv_matches_alexey_shape(self):
        answers = {
            "name": "Alexey Grigorev",
            "headline": "AI Product Engineer — End-to-End Production LLM Systems",
            "location": "Berlin, Germany",
            "email": "alexey@datatalks.club",
            "summary": "Product-minded AI engineer with 16 years in software engineering.",
            "links": "LinkedIn | https://www.linkedin.com/in/agrigorev",
            "skill_0_group": "Applied AI / LLM",
            "skill_0_items": "RAG, agentic workflows, evaluations",
            "exp_0_company": "DataTalks.Club",
            "exp_0_title": "Founder & Product Engineer",
            "exp_0_location": "Berlin, Germany",
            "exp_0_period": "Sep 2020 – Present",
            "exp_0_bullets": "Own AI product work end-to-end for a 100k+ learner community.",
        }
        cv = chat_answers_to_cv(answers)
        self.assertTrue(is_cv_structured(cv))
        self.assertEqual(cv["basics"]["name"], "Alexey Grigorev")
        self.assertEqual(cv["skills"][0]["group"], "Applied AI / LLM")
        self.assertEqual(cv["experience"][0]["company"], "DataTalks.Club")
        self.assertEqual(cv["resume_template"], "harvard")

    def test_structured_in_db_is_cv_yml(self):
        answers = {
            "name": "Jane Doe",
            "headline": "Data Engineer",
            "email": "jane@example.com",
            "exp_0_company": "Acme",
            "exp_0_title": "Engineer",
            "exp_0_period": "2020 — Present",
            "exp_0_bullets": "Built pipelines.",
        }
        structured = chat_answers_to_structured(answers)
        self.assertTrue(is_cv_structured(structured))
        roundtrip = structured_to_chat_answers(structured)
        self.assertEqual(roundtrip["name"], "Jane Doe")
        self.assertEqual(roundtrip["exp_0_company"], "Acme")

    def test_legacy_job_keys_migrate_to_cv(self):
        answers = {
            "fullName": "Alex Johnson",
            "desiredPosition": "Data Engineer",
            "email": "alex@example.com",
            "job_0_company": "Acme",
            "job_0_roleAndDates": "Senior Engineer, 2020 — Present",
            "job_0_description": "Built ETL pipelines.",
        }
        cv = normalize_to_cv(chat_answers_to_structured(answers))
        self.assertEqual(cv["basics"]["name"], "Alex Johnson")
        self.assertEqual(cv["experience"][0]["company"], "Acme")

    def test_recognition_books_roundtrip(self):
        answers = {
            "name": "Author",
            "headline": "Engineer",
            "email": "a@example.com",
            "recognition_books": "ML Bookcamp | Manning | 2021 | https://example.com",
            "recognition_highlights": "Speaker at PyCon",
        }
        cv = chat_answers_to_cv(answers)
        self.assertEqual(cv["recognition"]["books"][0]["title"], "ML Bookcamp")
        roundtrip = cv_to_chat_answers(cv)
        self.assertIn("ML Bookcamp", roundtrip["recognition_books"])
        self.assertIn("PyCon", roundtrip["recognition_highlights"])

    def test_interests_separate_from_header_note(self):
        answers = {
            "name": "Jane Doe",
            "headline": "Engineer",
            "email": "jane@example.com",
            "note": "Open to relocation",
            "interests": "VR, board games",
        }
        cv = chat_answers_to_cv(answers)
        self.assertEqual(cv["basics"]["note"], "Open to relocation")
        self.assertEqual(cv["interests"], "VR, board games")
        roundtrip = cv_to_chat_answers(cv)
        self.assertEqual(roundtrip["note"], "Open to relocation")
        self.assertEqual(roundtrip["interests"], "VR, board games")

    def test_experience_context_roundtrip(self):
        answers = {
            "name": "Jane Doe",
            "headline": "Engineer",
            "email": "jane@example.com",
            "exp_0_company": "Self-employed",
            "exp_0_title": "Data Engineer",
            "exp_0_period": "Aug 2023 – Feb 2024",
            "exp_0_context": "Platform Modernization and Lakehouse Implementation.",
            "exp_0_bullets": "Built ETL pipelines.",
        }
        cv = chat_answers_to_cv(answers)
        self.assertEqual(cv["experience"][0]["context"], "Platform Modernization and Lakehouse Implementation.")
        roundtrip = cv_to_chat_answers(cv)
        self.assertEqual(roundtrip["exp_0_context"], "Platform Modernization and Lakehouse Implementation.")

    def test_cv_to_plain_text_includes_project_context(self):
        from job_application.resume.cv_schema import cv_to_plain_text

        cv = chat_answers_to_cv(
            {
                "name": "Jane Doe",
                "headline": "Engineer",
                "email": "jane@example.com",
                "exp_0_company": "Acme",
                "exp_0_title": "Engineer",
                "exp_0_period": "2020",
                "exp_0_context": "Lakehouse migration.",
                "exp_0_bullets": "Built pipelines.",
            }
        )
        plain = cv_to_plain_text(cv)
        self.assertIn("Project context: Lakehouse migration.", plain)
        self.assertIn("Built pipelines.", plain)

    def test_migrate_legacy_interests_from_basics_note(self):
        cv = {
            "basics": {
                "name": "Jane Doe",
                "headline": "Engineer",
                "note": "Interests: VR - games",
            },
            "chat_format": "cv_yml",
        }
        normalized = normalize_to_cv(cv)
        self.assertEqual(normalized["interests"], "VR - games")
        self.assertEqual(normalized["basics"]["note"], "")

    def test_migrate_clears_duplicate_interests_note_when_interests_exists(self):
        cv = {
            "basics": {
                "name": "Jane Doe",
                "headline": "Engineer",
                "note": "Interests: VR - games",
            },
            "interests": "VR - games",
            "chat_format": "cv_yml",
        }
        normalized = normalize_to_cv(cv)
        self.assertEqual(normalized["interests"], "VR - games")
        self.assertEqual(normalized["basics"]["note"], "")

    def test_cv_to_chat_answers_roundtrip(self):
        cv = {
            "basics": {"name": "Test User", "headline": "AI Engineer", "email": "t@example.com"},
            "experience": [{"company": "Co", "title": "Eng", "period": "2021", "bullets": ["Did work."]}],
            "resume_template": "harvard",
            "chat_format": "cv_yml",
        }
        answers = cv_to_chat_answers(cv)
        self.assertEqual(answers["name"], "Test User")
        self.assertIn("Did work.", answers["exp_0_bullets"])


if __name__ == "__main__":
    unittest.main()
