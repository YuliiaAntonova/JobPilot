"""LLM ATS refinement — mocked, no API calls."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from job_application.scoring.ats_llm import format_jobbert_match_report, llm_refine_ats_suggestions


class TestFormatJobbertMatchReport(unittest.TestCase):
    def test_compact_report(self):
        matched = [
            {"required_skill": "SQL", "resume_skill": "SQL", "match_type": "exact", "similarity": 1.0},
        ]
        missing = [
            {"required_skill": "programming", "best_candidate": "Python", "similarity": 0.61},
        ]
        text = format_jobbert_match_report(matched, missing)
        self.assertIn("SQL -> SQL", text)
        self.assertIn("programming | closest: Python", text)


class TestLlmRefineAtsSuggestions(unittest.TestCase):
    @patch("job_application.shared.llm.client.complete_json_tracked")
    def test_parses_substitutions_and_filters_unknown_resume_phrase(self, mock_json):
        mock_json.return_value = (
            {
                "substitutions": [
                    {
                        "resume_phrase": "Postgres",
                        "jd_phrase": "SQL",
                        "reason": "relational DB",
                        "confidence": 0.82,
                    },
                    {
                        "resume_phrase": "InventedSkill",
                        "jd_phrase": "modeling",
                        "reason": "bad",
                        "confidence": 0.9,
                    },
                ],
                "noise": ["programming", "language"],
                "implicit_covered": [{"jd_phrase": "programming", "covered_by": "Python"}],
                "real_gaps": ["security"],
                "summary_ru": "Хорошее совпадение по стеку.",
            },
            {"total_tokens": 420},
        )

        out = llm_refine_ats_suggestions(
            matched_details=[
                {"required_skill": "Python", "resume_skill": "Python", "match_type": "exact", "similarity": 1.0}
            ],
            missing_details=[
                {"required_skill": "programming", "best_candidate": "Python", "similarity": 0.61}
            ],
            resume_skills=["Python", "Postgres", "SQL"],
        )

        self.assertEqual(out["source"], "llm_refined")
        self.assertEqual(len(out["suggestions"]), 1)
        self.assertEqual(out["suggestions"][0]["resume_phrase"], "Postgres")
        self.assertEqual(out["suggestions"][0]["jd_phrase"], "SQL")
        self.assertEqual(out["suggestions"][0]["match_type"], "llm")
        self.assertIn("programming", out["noise"])
        self.assertEqual(out["implicit_covered"][0]["covered_by"], "Python")
        self.assertIn("security", out["real_gaps"])
        self.assertIn("совпадение", out["summary_ru"])


if __name__ == "__main__":
    unittest.main()
