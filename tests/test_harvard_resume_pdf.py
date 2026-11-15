"""Tests for Harvard-format resume (YAML ↔ workshop HTML/PDF via Chrome)."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from job_application.documents.pdf import WorkshopCvRenderer
from job_application.resume.cv_pdf_export import (
    html_to_pdf_bytes,
    render_structured_resume_pdf_bytes,
    write_workshop_yml_and_html,
)
from job_application.resume.cv_yaml import (
    harvard_cv_to_structured,
    harvard_yaml_to_structured,
    structured_to_harvard_cv,
    structured_to_harvard_yaml,
)
from job_application.resume.profile_text import chat_answers_to_structured


def _sample_structured() -> dict:
    return chat_answers_to_structured(
        {
            "name": "Alex Johnson",
            "email": "alex@example.com",
            "phone": "+1 555 0100",
            "location": "San Francisco, CA",
            "headline": "Applied AI Engineer",
            "summary": "Data engineer with 5+ years of experience building production systems.",
            "skill_0_group": "Platform",
            "skill_0_items": "Python, SQL, Spark",
            "exp_0_company": "Acme Analytics",
            "exp_0_title": "Senior Data Engineer",
            "exp_0_period": "2020 — Present",
            "exp_0_bullets": "Built ETL pipelines and data quality checks.",
            "edu_0_school": "State University",
            "edu_0_degree": "M.S. Computer Science",
            "languages": "English — fluent",
            "certifications": "AWS Solutions Architect",
        }
    )


def _fake_chrome_pdf(html_path: Path, pdf_path: Path) -> None:
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes(b"%PDF-1.4 fake\nAlex Johnson\nAcme Analytics\n")


class TestHarvardResumeRender(unittest.TestCase):
    def test_structured_to_harvard_cv_maps_core_fields(self):
        structured = _sample_structured()
        cv = structured_to_harvard_cv(structured)

        self.assertEqual(cv["basics"]["name"], "Alex Johnson")
        self.assertEqual(cv["basics"]["email"], "alex@example.com")
        self.assertIn("Applied AI Engineer", cv["basics"]["headline"])
        self.assertTrue(cv["skills"])
        self.assertEqual(cv["experience"][0]["company"], "Acme Analytics")
        self.assertTrue(cv["experience"][0]["bullets"])

    def test_yaml_roundtrip_preserves_name_and_experience(self):
        structured = _sample_structured()
        yaml_text = structured_to_harvard_yaml(structured)
        loaded = yaml.safe_load(yaml_text)
        self.assertIsInstance(loaded, dict)
        roundtrip = harvard_cv_to_structured(loaded)
        self.assertEqual(roundtrip["basics"]["name"], "Alex Johnson")
        self.assertEqual(roundtrip["resume_template"], "harvard")
        self.assertTrue(roundtrip["experience"])
        self.assertEqual(roundtrip["experience"][0]["company"], structured["experience"][0]["company"])

    def test_harvard_yaml_to_structured_from_text(self):
        yaml_text = """
basics:
  name: Jane Doe
  headline: Data Engineer
  email: jane@example.com
  summary: Experienced engineer.
experience:
  - company: Example Corp
    title: Engineer
    period: 2021 — Present
    bullets:
      - Built pipelines.
"""
        structured = harvard_yaml_to_structured(yaml_text)
        self.assertEqual(structured["basics"]["name"], "Jane Doe")
        self.assertEqual(structured["experience"][0]["company"], "Example Corp")

    def test_render_html_contains_sections(self):
        structured = _sample_structured()
        _yml_path, html_path = write_workshop_yml_and_html(structured)
        html = html_path.read_text(encoding="utf-8")
        self.assertIn("Alex Johnson", html)
        self.assertIn("Acme Analytics", html)

    def test_experience_renders_project_context_and_present(self):
        structured = chat_answers_to_structured(
            {
                "name": "Jane Doe",
                "headline": "Engineer",
                "email": "jane@example.com",
                "exp_0_company": "Self-employed",
                "exp_0_title": "Data Engineer",
                "exp_0_period": "Aug 2023 – Feb 2024",
                "exp_0_context": "Platform Modernization and Lakehouse Implementation.",
                "exp_0_bullets": "Built ETL pipelines.",
                "exp_1_company": "Trinetix",
                "exp_1_title": "Big Data Engineer",
                "exp_1_period": "Feb 2024 – Current",
                "exp_1_bullets": "Built pipelines.",
            }
        )
        _yml_path, html_path = write_workshop_yml_and_html(structured)
        html = html_path.read_text(encoding="utf-8")
        self.assertIn("Feb 2024 – Present", html)
        self.assertNotIn("Current", html)
        self.assertIn('<span class="project-context-label">Project Context:</span>', html)
        self.assertIn("Platform Modernization and Lakehouse Implementation.", html)

    def test_interests_render_as_last_section_not_in_header(self):
        structured = chat_answers_to_structured(
            {
                "name": "Jane Doe",
                "headline": "Engineer",
                "email": "jane@example.com",
                "interests": "VR, board games",
            }
        )
        _yml_path, html_path = write_workshop_yml_and_html(structured)
        html = html_path.read_text(encoding="utf-8")
        self.assertNotIn('<p class="note">VR, board games</p>', html)
        self.assertIn("<h2>Interests</h2>", html)
        self.assertIn('<p class="interests">VR, board games</p>', html)
        self.assertGreater(html.index("VR, board games"), html.index("</header>"))

    @patch("job_application.resume.cv_pdf_export.chrome_html_to_pdf", side_effect=_fake_chrome_pdf)
    def test_render_pdf_contains_name(self, _mock_chrome):
        structured = _sample_structured()
        structured["resume_template"] = "harvard"
        pdf = render_structured_resume_pdf_bytes(structured)
        self.assertIn(b"Alex Johnson", pdf)
        self.assertIn(b"Acme Analytics", pdf)

    @patch("job_application.resume.cv_pdf_export.chrome_html_to_pdf", side_effect=_fake_chrome_pdf)
    def test_html_to_pdf_bytes_non_empty(self, _mock_chrome):
        _yml_path, html_path = write_workshop_yml_and_html(_sample_structured())
        html = html_path.read_text(encoding="utf-8")
        pdf = html_to_pdf_bytes(html)
        self.assertGreater(len(pdf), 10)
        self.assertTrue(pdf.startswith(b"%PDF"))

    @patch("job_application.resume.cv_pdf_export.chrome_html_to_pdf", side_effect=_fake_chrome_pdf)
    def test_workshop_renderer_produces_pdf(self, _mock_chrome):
        renderer = WorkshopCvRenderer()
        self.assertTrue(renderer.supports({"resume_template": "harvard"}))
        pdf = renderer.render_pdf(_sample_structured() | {"resume_template": "harvard"})
        self.assertTrue(pdf.startswith(b"%PDF"))


if __name__ == "__main__":
    unittest.main()
