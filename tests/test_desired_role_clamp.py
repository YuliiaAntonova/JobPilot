"""desired_role must fit resume_profiles.desired_role (VARCHAR 255)."""

from __future__ import annotations

import unittest
from pathlib import Path

from job_application.config import DESIRED_ROLE_MAX_LEN
from job_application.resume.profile_service import profile_dict_from_chat_answers
from job_application.resume.profile_text import (
    clamp_desired_role,
    resolve_desired_role,
    structured_to_chat_answers,
)
from job_application.shared.parsing import resume_bytes_to_plain_text


class TestDesiredRoleClamp(unittest.TestCase):
    def test_clamp_truncates_long_text(self):
        long_text = "QA Engineer " * 40
        out = clamp_desired_role(long_text)
        self.assertLessEqual(len(out), DESIRED_ROLE_MAX_LEN)
        self.assertTrue(out.startswith("QA Engineer"))

    def test_andrii_pdf_uses_headline_not_summary(self):
        pdf = Path(__file__).resolve().parent.parent / "AI_AndriiSporysh_CV_QA_2026.pdf"
        if not pdf.is_file():
            self.skipTest("AI_AndriiSporysh_CV_QA_2026.pdf not in repo root")
        plain = resume_bytes_to_plain_text(pdf.name, pdf.read_bytes())
        summary = "QA Engineer with 10+ years of experience in software testing. " * 20
        structured = {
            "personal": {"full_name": "Andrii Sporysh", "email": "sporishas@gmail.com"},
            "summary": summary,
            "_resume_plain_text": plain,
        }
        role = resolve_desired_role(structured, plain_text=plain)
        self.assertLessEqual(len(role), DESIRED_ROLE_MAX_LEN)
        self.assertIn("QA", role.upper())
        self.assertNotIn("10+ years", role)

        answers = structured_to_chat_answers(structured)
        self.assertLessEqual(len(answers["desiredPosition"]), DESIRED_ROLE_MAX_LEN)
        self.assertIn("QA", answers["desiredPosition"].upper())

    def test_chat_save_payload_respects_limit(self):
        long_summary = "Senior QA Engineer specializing in manual and automation testing. " * 15
        answers = {
            "fullName": "Andrii Sporysh",
            "email": "sporishas@gmail.com",
            "desiredPosition": long_summary,
        }
        payload = profile_dict_from_chat_answers(answers)
        self.assertLessEqual(len(payload["desired_role"]), DESIRED_ROLE_MAX_LEN)


if __name__ == "__main__":
    unittest.main()
