"""Текст резюме для JobBERT — parsed profile для API."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from job_application.config import RESUME_TEXT_MIN_CHARS
from job_application.resume.profile_service import resolve_resume_text_for_jobbert_scoring


class TestJobbertResumeTextApi(unittest.TestCase):
    def test_uses_parsed_profile_from_db(self):
        prof = MagicMock()
        prof.chat_answers = {"fullName": "Test User", "email": "t@e.c", "mainTechStack": "Python, PySpark"}
        prof.structured = {}
        prof.profile_text = "formatted"

        db = MagicMock()
        db_users = MagicMock()
        db_users.get_profile_for_user.return_value = prof

        import job_application.resume.profile_service as ps

        old = ps.db_users
        ps.db_users = db_users
        try:
            user = MagicMock()
            user.id = "u1"
            text, _, source = resolve_resume_text_for_jobbert_scoring(db, user, None)
        finally:
            ps.db_users = old

        self.assertIn(source, {"profile_parsed", "profile_rebuild", "pdf_plain", "profile_text"})
        self.assertGreaterEqual(len(text or ""), RESUME_TEXT_MIN_CHARS)
        self.assertIn("Python", text or "")

    def test_form_resume_text_when_not_logged_in(self):
        text, _, source = resolve_resume_text_for_jobbert_scoring(
            db=MagicMock(),
            user=None,
            resume_text="Parsed resume profile text " * 10,
        )
        self.assertEqual(source, "profile_parsed")
        self.assertIn("Parsed resume", text or "")

    def test_explicit_resume_text_overrides_cabinet_profile(self):
        prof = MagicMock()
        prof.chat_answers = {"fullName": "Test User", "email": "t@e.c", "mainTechStack": "Python, PySpark"}
        prof.structured = {"_resume_plain_text": "Old cabinet resume text " * 10}
        prof.profile_text = "Old cabinet resume text " * 10

        db = MagicMock()
        db_users = MagicMock()
        db_users.get_profile_for_user.return_value = prof

        import job_application.resume.profile_service as ps

        old = ps.db_users
        ps.db_users = db_users
        try:
            user = MagicMock()
            user.id = "u1"
            tailored = "Tailored resume with Spark and Airflow keywords " * 8
            text, _, source = resolve_resume_text_for_jobbert_scoring(db, user, tailored)
        finally:
            ps.db_users = old

        self.assertEqual(source, "profile_parsed")
        self.assertIn("Tailored resume", text or "")
        self.assertNotIn("Old cabinet", text or "")


if __name__ == "__main__":
    unittest.main()
