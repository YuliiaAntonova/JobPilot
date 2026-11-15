"""Impact / achievements (job_*_result) persist and render in PDF export."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from job_application.documents.resume_normalize import normalize_structured_for_render
from job_application.resume.profile_service import (
    profile_dict_from_chat_answers,
    structured_for_render_from_profile,
)
from job_application.resume.profile_text import (
    _extract_contact_from_plain_text,
    _job_highlights,
    _seed_personal_links_from_plain,
    chat_answers_to_structured,
    structured_to_chat_answers,
)
from job_application.models import ResumeProfile


class TestProfileImpactSave(unittest.TestCase):
    def test_custom_summary_and_links_persist_on_save(self):
        answers = {
            "fullName": "Yuliia Antonova",
            "email": "y@example.com",
            "desiredPosition": "Data Engineer",
            "summary": "Big Data Engineer with 5+ years building ETL pipelines on AWS.",
            "links": "https://github.com/yuliia-new\nhttps://linkedin.com/in/yuliia",
        }
        payload = profile_dict_from_chat_answers(answers)
        basics = payload["structured"]["basics"]
        self.assertEqual(
            basics["summary"],
            "Big Data Engineer with 5+ years building ETL pipelines on AWS.",
        )
        link_urls = " ".join(str(l.get("url") or "") for l in basics.get("links") or [])
        self.assertIn("github.com/yuliia-new", link_urls)
        self.assertIn("github.com/yuliia-new", payload["chat_answers"]["links"])

    def test_summary_and_portfolio_links_roundtrip_from_structured(self):
        structured = {
            "basics": {
                "name": "Jane Doe",
                "summary": "Senior engineer focused on data platforms.",
                "links": [
                    {"label": "GitHub", "text": "https://github.com/jane-new", "url": "https://github.com/jane-new"},
                    {"label": "LinkedIn", "text": "https://linkedin.com/in/jane", "url": "https://linkedin.com/in/jane"},
                ],
            },
            "experience": [],
        }
        answers = structured_to_chat_answers(structured)
        self.assertEqual(answers["summary"], "Senior engineer focused on data platforms.")
        self.assertIn("github.com/jane-new", answers["links"])
        self.assertIn("linkedin.com/in/jane", answers["links"])
        rebuilt = chat_answers_to_structured(answers)
        self.assertEqual(rebuilt["basics"]["summary"], "Senior engineer focused on data platforms.")
        urls = " ".join(str(l.get("url") or "") for l in rebuilt["basics"].get("links") or [])
        self.assertIn("github.com/jane-new", urls)
        self.assertIn("linkedin.com/in/jane", urls)

    def test_pdf_seed_adds_linkedin_when_portfolio_has_only_github(self):
        plain = (
            "Yuliia Antonova\n"
            "y@example.com | linkedin.com/in/yuliya25 | github.com/yuliia\n"
            "OBJECTIVE\nData Engineer\n"
        )
        structured = _seed_personal_links_from_plain(
            {
                "_resume_plain_text": plain,
                "personal": {
                    "full_name": "Yuliia Antonova",
                    "github": "github.com/yuliia",
                    "portfolio": "github.com/yuliia",
                },
            }
        )
        answers = structured_to_chat_answers(structured)
        self.assertIn("linkedin.com/in/yuliya25", answers["links"])
        self.assertIn("github.com/yuliia", answers["links"])

    def test_extract_contact_finds_both_urls_on_one_line(self):
        contact = _extract_contact_from_plain_text(
            "email@test.com | linkedin.com/in/jane | github.com/jane-dev"
        )
        self.assertIn("linkedin.com/in/jane", contact["linkedin"])
        self.assertIn("github.com/jane-dev", contact["github"])

    def test_extract_contact_finds_email_phone_and_location_in_header(self):
        contact = _extract_contact_from_plain_text(
            "YULIIA ANTONOVA\n"
            "Lengerich, Germany\n"
            "yuliia.antonova1@gmail.com +491759415902\n"
            "SUMMARY\n"
            "Senior Data Engineer"
        )
        self.assertEqual(contact["email"], "yuliia.antonova1@gmail.com")
        self.assertIn("491759415902", contact["phone"])
        self.assertEqual(contact["location"], "Lengerich, Germany")

    def test_links_field_is_source_of_truth_not_stale_personal_fields(self):
        answers = {
            "fullName": "Jane Doe",
            "email": "j@example.com",
            "links": "https://github.com/jane-new",
        }
        rebuilt = chat_answers_to_structured(answers)
        urls = " ".join(str(l.get("url") or "") for l in rebuilt["basics"].get("links") or [])
        self.assertIn("github.com/jane-new", urls)
        self.assertNotIn("linkedin.com", urls)

    def test_portfolio_in_structured_does_not_merge_stale_linkedin_field(self):
        structured = {
            "basics": {
                "name": "Jane Doe",
                "links": [
                    {"label": "GitHub", "text": "https://github.com/jane-new", "url": "https://github.com/jane-new"},
                    {"label": "LinkedIn", "text": "https://linkedin.com/in/jane", "url": "https://linkedin.com/in/jane"},
                ],
            },
            "experience": [],
        }
        answers = structured_to_chat_answers(structured)
        self.assertNotIn("github.com/stale", answers["links"])
        self.assertNotIn("linkedin.com/in/stale", answers["links"])
        self.assertIn("github.com/jane-new", answers["links"])
        self.assertIn("linkedin.com/in/jane", answers["links"])

    def test_chat_answers_result_maps_to_bullets(self):
        answers = {
            "fullName": "Yuliia Antonova",
            "email": "y@example.com",
            "job_0_company": "Trinetix",
            "job_0_roleAndDates": "Big Data Engineer, Feb 2024 - Current",
            "job_0_description": "Built ETL pipelines with AWS Glue.",
            "job_0_result": "Reduced daily pipeline runtime by 40%.",
        }
        payload = profile_dict_from_chat_answers(answers)
        job = payload["structured"]["experience"][0]
        self.assertIn("Reduced daily pipeline runtime by 40%.", job["bullets"])
        self.assertEqual(payload["chat_answers"]["job_0_result"], "Reduced daily pipeline runtime by 40%.")

    def test_structured_for_render_from_profile_prefers_chat_answers(self):
        answers = {
            "fullName": "Yuliia Antonova",
            "email": "y@example.com",
            "job_0_company": "Trinetix",
            "job_0_roleAndDates": "Big Data Engineer, Feb 2024 - Current",
            "job_0_description": "Built ETL pipelines with AWS Glue.",
            "job_0_result": "Reduced daily pipeline runtime by 40%.",
        }
        profile = ResumeProfile(
            id="p1",
            user_id="u1",
            structured={"experience": [{"company": "Trinetix", "bullets": []}]},
            profile_text="",
            chat_answers=answers,
        )
        rendered = structured_for_render_from_profile(profile)
        bullets = _job_highlights(rendered["experience"][0])
        self.assertIn("Reduced daily pipeline runtime by 40%.", bullets)

    def test_pdf_bullets_include_impact_after_normalize(self):
        answers = {
            "fullName": "Yuliia Antonova",
            "email": "y@example.com",
            "job_0_company": "Trinetix",
            "job_0_roleAndDates": "Big Data Engineer, Feb 2024 - Current",
            "job_0_description": "Built ETL pipelines with AWS Glue.",
            "job_0_result": "Reduced daily pipeline runtime by 40%.",
        }
        structured = profile_dict_from_chat_answers(answers)["structured"]
        structured["_resume_plain_text"] = "YULIIA ANTONOVA\nEXPERIENCE\nOld PDF text without impact."
        norm = normalize_structured_for_render(structured)
        bullets = _job_highlights(norm["experience"][0])
        self.assertIn("Reduced daily pipeline runtime by 40%.", bullets)
        self.assertIn("Built ETL pipelines with AWS Glue.", bullets)

    @patch("job_application.resume.cv_pdf_export.chrome_html_to_pdf")
    def test_pdf_renders_four_bullets_with_impact(self, mock_chrome):
        def _fake_chrome(html_path: Path, pdf_path: Path) -> None:
            pdf_path.parent.mkdir(parents=True, exist_ok=True)
            pdf_path.write_bytes(
                b"%PDF-1.4 fake\nIncreased ETL throughput by 40%.\nOpenSearch\nthrough all layers\n"
            )

        mock_chrome.side_effect = _fake_chrome

        structured = profile_dict_from_chat_answers(
            {
                "name": "Yuliia Antonova",
                "email": "y@example.com",
                "exp_0_company": "Trinetix",
                "exp_0_title": "Big Data Engineer",
                "exp_0_period": "Feb 2024 - Current",
                "exp_0_bullets": (
                    "Manage data flow through all layers: Ingestion → Raw → Derived → Datamart.\n"
                    "Work with Step Functions to orchestrate Glue Jobs and automate daily pipelines.\n"
                    "Work with Aurora (AppData/OLTP) and OpenSearch for data storage and querying.\n"
                    "Increased ETL throughput by 40%."
                ),
            }
        )["structured"]
        structured["_resume_plain_text"] = "YULIIA ANTONOVA\nEXPERIENCE\nTrinetix"
        norm = normalize_structured_for_render(structured)
        bullets = _job_highlights(norm["experience"][0])
        self.assertEqual(len(bullets), 4)
        self.assertIn("Increased ETL throughput by 40%.", bullets)
        self.assertIn("OpenSearch", " ".join(bullets))

        from job_application.resume.cv_pdf_export import render_structured_resume_pdf_bytes, write_workshop_yml_and_html

        _yml_path, html_path = write_workshop_yml_and_html(norm)
        html = html_path.read_text(encoding="utf-8")
        self.assertIn("Increased ETL throughput by 40%.", html)
        self.assertIn("OpenSearch", html)

        pdf = render_structured_resume_pdf_bytes(structured)
        text = pdf.decode("utf-8", errors="replace")
        self.assertIn("Increased ETL throughput by 40%.", text)
        self.assertIn("OpenSearch", text)
        self.assertIn("through all layers", text.lower())

    def test_pdf_plain_text_keeps_chat_impact_on_normalize(self):
        structured = profile_dict_from_chat_answers(
            {
                "fullName": "Yuliia Antonova",
                "email": "y@example.com",
                "job_0_company": "Trinetix",
                "job_0_roleAndDates": "Big Data Engineer, Feb 2024 - Current",
                "job_0_description": "Manage data flow through all layers.",
                "job_0_result": "Reduced daily pipeline runtime by 40%.",
            }
        )["structured"]
        structured["_resume_plain_text"] = (
            "Big Data Engineer. Trinetix. February 2024 - Current\n"
            "Manage data flow through all layers: Ingestion -> Raw -> Derived -> Datamart.\n"
        )
        norm = normalize_structured_for_render(structured)
        bullets = _job_highlights(norm["experience"][0])
        self.assertIn("Reduced daily pipeline runtime by 40%.", bullets)


if __name__ == "__main__":
    unittest.main()
