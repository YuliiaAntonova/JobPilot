"""Tests for cv.yml PDF/text parsing helpers."""

from __future__ import annotations

import unittest

from job_application.resume.cv_yml_io import (
    _parse_yaml_response,
    clean_yaml_output,
    enrich_cv_basics_from_plain,
    normalize_dates,
    split_experience_sections,
)


class TestCvYmlIo(unittest.TestCase):
    def test_clean_yaml_output_strips_fences(self):
        raw = "```yaml\nbasics:\n  name: Test\n```"
        self.assertIn("name: Test", clean_yaml_output(raw))
        self.assertNotIn("```", clean_yaml_output(raw))

    def test_clean_yaml_output_strips_preamble_before_basics(self):
        raw = (
            "Here is the converted resume\n"
            "in YAML format:\n\n"
            "basics:\n"
            "  name: Test User\n"
            "  headline: Engineer\n"
            "skills: []\n"
        )
        cleaned = clean_yaml_output(raw)
        self.assertTrue(cleaned.startswith("basics:"))
        self.assertNotIn("Here is the converted", cleaned)

    def test_parse_yaml_response_recovers_preamble_and_colon_in_headline(self):
        raw = (
            "Sure — YAML below:\n\n"
            "basics:\n"
            "  name: Ada Lovelace\n"
            "  headline: Mathematician: Analyst\n"
            "  summary: Pioneer\n"
            "skills: []\n"
            "experience: []\n"
        )
        data = _parse_yaml_response(raw)
        self.assertEqual(data["basics"]["name"], "Ada Lovelace")
        self.assertIn("Mathematician", data["basics"]["headline"])

    def test_normalize_dates_shortens_months(self):
        cv = {
            "experience": [{"period": "January 2020 — December 2021", "company": "Co"}],
            "experience_earlier": [{"period": "2015 to 2017", "company": "Old"}],
        }
        out = normalize_dates(cv)
        self.assertIn("Jan", out["experience"][0]["period"])
        self.assertEqual(out["experience_earlier"][0]["period"], "2015 – 2017")

    def test_normalize_dates_replaces_current_with_present(self):
        cv = {"experience": [{"period": "Feb 2024 – Current", "company": "Co"}]}
        out = normalize_dates(cv)
        self.assertEqual(out["experience"][0]["period"], "Feb 2024 – Present")

    def test_split_experience_keeps_three_most_recent(self):
        cv = {
            "experience": [
                {"company": "Trinetix", "title": "Big Data Engineer", "period": "Feb 2024 – Present", "bullets": ["a"]},
                {"company": "Self-employed", "title": "Data Engineer", "period": "Aug 2023 – Feb 2024", "bullets": ["b"]},
            ],
            "experience_earlier": [
                {"company": "HR Forecast", "role": "Data Engineer", "period": "2022 – 2023", "stack": ["Ray"]},
                {"company": "Auchan Retail", "role": "Python Developer", "period": "2021 – 2022", "stack": ["Python"]},
            ],
        }
        out = split_experience_sections(cv)
        self.assertEqual(len(out["experience"]), 3)
        self.assertEqual(out["experience"][2]["company"], "HR Forecast")
        self.assertEqual(len(out["experience_earlier"]), 1)
        self.assertEqual(out["experience_earlier"][0]["company"], "Auchan Retail")

    def test_enrich_cv_basics_from_plain_fills_missing_contact(self):
        cv = {"basics": {"name": "Yuliia Antonova", "location": "", "email": "", "phone": ""}}
        plain = (
            "YULIIA ANTONOVA\n"
            "Lengerich, Germany\n"
            "yuliia.antonova1@gmail.com | +491759415902\n"
            "SUMMARY\n"
            "Senior Data Engineer"
        )
        out = enrich_cv_basics_from_plain(cv, plain)
        self.assertEqual(out["basics"]["email"], "yuliia.antonova1@gmail.com")
        self.assertIn("491759415902", out["basics"]["phone"])
        self.assertEqual(out["basics"]["location"], "Lengerich, Germany")


if __name__ == "__main__":
    unittest.main()
