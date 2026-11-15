"""Маппинг опыта из structured JSON (cv.yml) в ответы чата."""

from __future__ import annotations

import unittest

from job_application.resume.profile_text import structured_to_chat_answers


class TestProfileExperienceMapping(unittest.TestCase):
    def test_standard_experience_array(self):
        seed = structured_to_chat_answers(
            {
                "personal": {"full_name": "Anna"},
                "experience": [
                    {
                        "title": "Data Engineer",
                        "company": "HRForecast",
                        "dates": "Feb 2022 — July 2023",
                        "highlights": ["Built ETL on Ray"],
                        "technologies": ["Ray"],
                    }
                ],
            }
        )
        self.assertEqual(seed["exp_0_company"], "HR Forecast")
        self.assertIn("ETL", seed["exp_0_bullets"])
        self.assertIn("Data Engineer", seed["exp_0_title"])

    def test_experiences_key_and_description_field(self):
        seed = structured_to_chat_answers(
            {
                "experiences": [
                    {
                        "company_name": "ACME",
                        "job_title": "Data Engineer",
                        "dates": "2020 — 2021",
                        "description": "строила ETL на Ray, писала pytest",
                    }
                ]
            }
        )
        self.assertEqual(seed["exp_0_company"], "ACME")
        self.assertIn("ETL", seed["exp_0_bullets"])

    def test_title_at_company_pattern(self):
        seed = structured_to_chat_answers(
            {
                "experience": [
                    {
                        "title": "Data Engineer at HRForecast",
                        "dates": "2022 — 2023",
                        "responsibilities": ["Автоматизация пайплайнов"],
                    }
                ]
            }
        )
        self.assertIn("HR Forecast", seed["exp_0_company"])
        self.assertIn("Автоматизация", seed["exp_0_bullets"])

    def test_bad_llm_array_falls_back_to_experience_text(self):
        text = (
            "Big Data Engineer | Trinetix | February 2024 - Current\n"
            "- Manage data flow through all layers: Ingestion -> Raw -> Derived -> Datamart.\n"
            "- Work with Step Functions to orchestrate Glue Jobs and automate daily pipelines.\n"
            "Data Engineer | Self-employed | August 2023 - February 2024\n"
            "- Implemented and managed ETL processes for data integration.\n"
            "Data Engineer | HR Forecast | February 2022 - July 2023\n"
            "- Built data pipelines on Ray for continuous analytics of parsed data."
        )
        seed = structured_to_chat_answers(
            {
                "experience": [
                    {
                        "company": "HRForecast",
                        "title": "DataEngineer.Selfemployed",
                        "highlights": [
                            "Manage data flow through all layers: Ingestion -> Raw -> Derived -> Datamart.",
                            "Work with Step Functions to orchestrate Glue Jobs and automate daily pipelines.",
                        ],
                    }
                ],
                "experience_text": text,
            }
        )
        self.assertEqual(seed["exp_0_company"], "Trinetix")
        self.assertIn("Big Data Engineer", seed["exp_0_title"])
        self.assertIn("Step Functions", seed["exp_0_bullets"])
        self.assertNotIn("Ray", seed["exp_0_bullets"])

        seed_hr = structured_to_chat_answers({"experience_text": text})
        self.assertIn("exp_2_company", seed_hr)
        self.assertIn("HR Forecast", seed_hr["exp_2_company"])

    def test_pdf_dot_format_jobs_sorted_by_recency(self):
        from job_application.resume.profile_text import _extract_jobs_from_resume_plain_text

        text = (
            "Built data pipelines on Ray for continuous analytics of parsed data.\n"
            "Implemented and managed ETL processes for data integration.\n"
            "Manage data flow through all layers: Ingestion → Raw → Derived → Datamart.\n"
            "EDUCATION\n"
            "Big Data Engineer. Trinetix. February 2024 - Current\n"
            "DataEngineer. HRForecast.February 2022-July2023\n"
            "DataEngineer.Selfemployed. August2023-February2024\n"
        )
        jobs = _extract_jobs_from_resume_plain_text(text)
        self.assertEqual(jobs[0]["company"], "Trinetix")
        self.assertEqual(jobs[1]["company"], "Self-employed")
        self.assertEqual(jobs[2]["company"], "HR Forecast")

        seed = structured_to_chat_answers({"_resume_plain_text": text, "personal": {"full_name": "Y"}})
        self.assertEqual(seed["exp_1_company"], "Self-employed")
        self.assertIn("August 2023", seed["exp_1_period"])
        self.assertIn("HR Forecast", seed["exp_2_company"])
        self.assertIn("Ray", seed["exp_2_bullets"])

    def test_pdf_plain_text_beats_empty_llm_experience(self):
        from pathlib import Path
        from job_application.shared.parsing import extract_pdf_text

        pdf = Path("yuliia_data_.pdf")
        if not pdf.exists():
            self.skipTest("yuliia_data_.pdf not in repo")
        text = extract_pdf_text(pdf)
        seed = structured_to_chat_answers(
            {
                "_resume_plain_text": text,
                "personal": {"full_name": "Yuliia Antonova", "email": "y@e.c"},
                "experience": [
                    {"company": "Trinetix", "title": "Big Data Engineer", "dates": "2024 - Current"},
                    {"company": "HR Forecast", "title": "Data Engineer", "dates": "2022-2023"},
                ],
            }
        )
        self.assertEqual(seed["exp_0_company"], "Trinetix")
        self.assertIn("Step Functions", seed["exp_0_bullets"])
        self.assertEqual(seed["exp_1_company"], "Self-employed")
        self.assertIn("ETL", seed["exp_1_bullets"])
        self.assertIn("HR Forecast", seed["exp_2_company"])
        self.assertIn("Ray", seed["exp_2_bullets"])
        self.assertNotIn("PySpark", seed.get("exp_0_bullets", ""))
        self.assertEqual(seed["exp_3_company"], "Auchan Retail")
        self.assertIn("Python Developer", seed["exp_3_title"])
        self.assertIn("logistics platform", seed["exp_3_bullets"].lower())
        self.assertIn("Python scripts", seed["exp_3_bullets"])
        self.assertEqual(seed["exp_4_company"], 'Coal company "Krasnolimanskaya"')
        self.assertIn("Business Analyst", seed["exp_4_title"])
        self.assertIn("2007", seed["exp_4_period"])

        self.assertTrue(
            seed.get("certifications")
            or seed.get("edu_0_school")
            or seed.get("languages")
            or len([k for k in seed if k.startswith("exp_")]) >= 3
        )

    def test_hursh_desai_paren_company_resume(self):
        from pathlib import Path
        from job_application.shared.parsing import extract_pdf_text

        pdf = Path("Hursh Desai - Resume.pdf")
        if not pdf.exists():
            self.skipTest("Hursh Desai - Resume.pdf not in repo")
        text = extract_pdf_text(pdf)
        seed = structured_to_chat_answers(
            {"_resume_plain_text": text, "personal": {"full_name": "Hursh Desai"}}
        )
        self.assertEqual(seed.get("phone"), "+1 (669) 236-9023")
        self.assertEqual(seed.get("email"), "hurshdesai8@gmail.com")
        self.assertIn("hursh-desai.github.io", seed.get("links") or "")
        self.assertEqual(seed["exp_0_company"], "Valtech")
        self.assertIn("Data Engineer", seed["exp_0_title"])
        self.assertIn("DALL-E", seed["exp_0_bullets"])
        self.assertEqual(seed["exp_1_company"], "Kin+Carta")
        self.assertIn("Databricks", seed["exp_1_bullets"])
        self.assertNotIn("@", seed["exp_0_company"])

        self.assertGreaterEqual(len([k for k in seed if k.startswith("exp_") and k.endswith("_company")]), 2)

    def test_llm_extra_experience_does_not_create_phantom_job_slot(self):
        from job_application.resume.profile_service import profile_dict_from_structured

        profile = profile_dict_from_structured(
            {
                "personal": {"full_name": "Anna"},
                "experience": [
                    {"company": "ACME", "title": "Engineer", "dates": "2024", "description": "Real job"},
                    {"title": "Ghost", "dates": "2020", "description": "LLM-only phantom"},
                ],
            },
            source="pdf",
        )
        seed = profile["chat_answers"]
        companies = sorted(k for k in seed if k.endswith("_company"))
        self.assertEqual(companies, ["exp_0_company"])
        self.assertNotIn("exp_1_bullets", seed)
        self.assertEqual(len(profile["structured"]["experience"]), 1)


if __name__ == "__main__":
    unittest.main()
