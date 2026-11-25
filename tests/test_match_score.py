"""Тесты JobBERT skill match — без загрузки моделей."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from job_application.scoring import jobbert as jobbert_skill_match
from job_application.scoring import service as match_score
from job_application.scoring.ats import build_ats_suggestions


class TestJobbertHelpers(unittest.TestCase):
    def test_extract_requirements_section(self):
        jd = """
About the role
Lead the team.

Skills & Requirements

• Python and PySpark required
• Azure preferred

Benefits/Other Compensation
Medical and dental.
"""
        section = jobbert_skill_match.extract_requirements_section(jd)
        self.assertIn("Python", section)
        self.assertNotIn("Medical", section)

    def test_clean_technical_entities_drops_fragments(self):
        raw = [
            {"word": "##tion", "score": 0.99},
            {"word": "Python", "score": 0.95},
            {"word": "PySpark", "score": 0.92},
            {"word": "we", "score": 0.90},
        ]
        cleaned = jobbert_skill_match.clean_technical_entities(raw, min_score=0.60)
        self.assertIn("Python", cleaned)
        self.assertIn("PySpark", cleaned)
        self.assertNotIn("we", cleaned)

    def test_match_skills_exact_and_lexical(self):
        job_skills = ["Python", "PySpark", "Databricks"]
        resume_skills = ["Python", "PySpark", "Data Bricks"]
        percent, matched, missing = jobbert_skill_match.match_skills(
            job_skills,
            resume_skills,
            semantic_threshold=0.99,
        )
        self.assertEqual(len(matched), 3)
        self.assertEqual(missing, [])
        self.assertAlmostEqual(percent, 100.0)

    def test_supplement_literal_phrase_data_pipelines(self):
        from job_application.scoring.jobbert import supplement_resume_entities_with_literal_phrases

        resume = "Built data pipelines on Ray. Automated pipeline execution."
        job_skills = ["data pipelines", "Python"]
        resume_skills = ["pipeline execution", "Python"]
        out = supplement_resume_entities_with_literal_phrases(resume, job_skills, resume_skills)
        self.assertIn("data pipelines", out)
        self.assertIn("pipeline execution", out)

    def test_merge_resume_skills_picks_up_tailored_hands_on_line(self):
        from job_application.scoring.jobbert import _merge_resume_skills_for_scoring

        resume = (
            "Hands-on experience Python, PySpark, Pandas, Flask, SQL (DML), Oracle, Postgres\n"
            "Built data pipelines on Ray for continuous analytics."
        )
        base = ["Python", "SQL"]
        merged = _merge_resume_skills_for_scoring(resume, base, ["data pipelines", "PySpark"])
        lowered = {s.casefold() for s in merged}
        self.assertIn("pyspark", lowered)
        self.assertIn("data pipelines", lowered)

    @patch("job_application.scoring.jobbert.extract_job_skills_from_jd")
    def test_literal_phrase_supplement_uses_full_resume_not_skills_block(self, mock_jd):
        """UI score 11% vs notebook 16%: «data pipelines» in bullets but not in structured skills."""
        mock_jd.return_value = (
            ["SQL", "Python", "data pipelines"],
            "Strong Python, SQL, and data pipelines skills.",
        )
        structured = {"skills": ["Python", "SQL", "PySpark", "Pandas", "Flask"]}
        resume = (
            "Hands-on experience Python, Flask SQL, Pandas\n"
            "Built data pipelines on Ray for continuous analytics.\n"
            "Automated pipeline execution."
        )
        result = jobbert_skill_match.compute_jobbert_skill_match(resume, "jd", structured=structured)
        self.assertIn("data pipelines", result["resume_skills"])
        self.assertIn("data pipelines", result["matched_skills"])
        self.assertGreaterEqual(result["match_score"], 16)

    def test_expand_resume_skill_entities_splits_missing_comma(self):
        expanded = jobbert_skill_match.expand_resume_skill_entities(["Flask SQL", "Redis Git"])
        self.assertIn("Flask", expanded)
        self.assertIn("SQL", expanded)
        self.assertIn("Redis", expanded)
        self.assertIn("Git", expanded)

    def test_expand_resume_skill_entities_splits_aws_glue(self):
        expanded = jobbert_skill_match.expand_resume_skill_entities(["AWS Glue"])
        self.assertIn("AWS", expanded)
        self.assertIn("Glue", expanded)

    def test_match_skills_aws_token_in_aws_glue(self):
        percent, matched, missing = jobbert_skill_match.match_skills(
            ["AWS", "Azure", "GCP"],
            ["AWS Glue", "Lambda", "Snowflake"],
            semantic_threshold=0.99,
        )
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0]["required_skill"], "AWS")
        self.assertEqual(matched[0]["resume_skill"], "AWS Glue")
        self.assertEqual(matched[0]["match_type"], "token")
        self.assertEqual({m["required_skill"] for m in missing}, {"Azure", "GCP"})

    def test_match_skills_sql_via_split_or_token_in_flask_sql(self):
        expanded = jobbert_skill_match.expand_resume_skill_entities(["Flask SQL"])
        percent, matched, missing = jobbert_skill_match.match_skills(
            ["SQL"],
            expanded,
            semantic_threshold=0.99,
        )
        self.assertEqual(missing, [])
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0]["match_type"], "exact")
        self.assertEqual(matched[0]["resume_skill"], "SQL")
        self.assertAlmostEqual(percent, 100.0)

        percent, matched, missing = jobbert_skill_match.match_skills(
            ["SQL"],
            ["Flask SQL"],
            semantic_threshold=0.99,
        )
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0]["match_type"], "token")
        self.assertEqual(matched[0]["resume_skill"], "Flask SQL")

    def test_expand_does_not_split_power_bi(self):
        expanded = jobbert_skill_match.expand_resume_skill_entities(["Power BI"])
        self.assertEqual(expanded, ["Power BI"])

    def test_expand_compound_job_entities_splits_cloud_not_etl_slash(self):
        from job_application.scoring.jobbert import expand_compound_job_entities

        out = expand_compound_job_entities(
            ["ETL / ELT", "CI / CD", "AWS, Azure", "Git. Airflow", "GCP. quality"]
        )
        self.assertIn("ETL / ELT", out)
        self.assertIn("CI / CD", out)
        for expected in ("AWS", "Azure", "Git", "Airflow", "GCP", "quality"):
            self.assertIn(expected, out)
        self.assertNotIn("ETL", out)
        self.assertNotIn("CD", out)

    def test_refine_job_skills_drops_vague_entities(self):
        from job_application.scoring.jobbert import refine_job_skills_for_scoring

        raw = [
            "Python",
            "SQL",
            "AWS",
            "data",
            "models",
            "analytical",
            "production",
            "English",
            "ETL / ELT",
            "CI / CD",
            "Airflow",
        ]
        out = refine_job_skills_for_scoring(raw)
        self.assertEqual(
            out,
            ["Python", "SQL", "AWS", "ETL / ELT", "CI / CD", "Airflow"],
        )

    def test_scoring_score_uses_refined_jd_entities(self):
        from job_application.scoring.jobbert import compute_jobbert_skill_match
        from job_application.resume.profile_text import skills_from_plain_resume_text

        skills_line = (
            "Hands-on experience Python, PySpark, Pandas, Flask. SQL (DML), Oracle, Postgres, Redis. "
            "Git (GitHub, Gitlab). Tools: PyCharm, AWS Glue, Step Functions, Athena, Lambda, Snowflake."
        )
        resume = f"SKILLS\n\n{skills_line}"
        jd = """
Skills & Requirements
Experience with ETL / ELT processes and databases, APIs, data models, analytical tables, warehouse structures.
Strong Python, SQL, Git. Airflow, data Engineering in production pipeline and modeling.
Experience with AWS, Azure, or GCP. quality monitoring, testing, CI / CD. English required.
Benefits/Other Compensation
"""
        structured = {"skills": skills_from_plain_resume_text(resume)}
        result = compute_jobbert_skill_match(resume, jd, structured=structured)
        self.assertGreaterEqual(result["match_score"], 30)
        self.assertLess(len(result["required_skills"]), 20)
        for noisy in ("data", "models", "English", "production", "monitoring"):
            self.assertNotIn(noisy, result["required_skills"])
        self.assertIn("AWS", result["matched_skills"])

    @patch("job_application.scoring.service.extract_job_skills_from_jd", return_value=([], ""))
    def test_no_profile_skills_fallback(self, _mock_extract):
        structured = {
            "skills": ["python", "dall-e", "gpt-4", "langchain"],
            "skills_text": "Python, DALL-E, GPT-4, LangChain",
        }
        skills, source = match_score.resolve_required_skills(
            "Join our team today. Great culture and competitive benefits.",
            structured,
        )
        self.assertEqual(source, "none")
        self.assertEqual(skills, [])

    @patch("job_application.scoring.service.extract_job_skills_from_jd")
    def test_resolve_required_skills_uses_jobbert(self, mock_extract):
        mock_extract.return_value = (["Python", "LangChain"], "req text")
        skills, source = match_score.resolve_required_skills("some jd", None)
        self.assertEqual(source, "jobbert_requirements_section")
        self.assertEqual(skills, ["Python", "LangChain"])

    @patch("job_application.scoring.service.compute_jobbert_skill_match")
    def test_compute_hybrid_passes_structured_profile(self, mock_compute):
        mock_compute.return_value = {
            "match_score": 50,
            "comparison_summary": "JobBERT skill match 50%",
            "resume_entities_source": "structured_profile",
        }
        structured = {"skills": ["Python", "SQL"]}
        match_score.compute_hybrid_match_score("resume", "jd", structured=structured)
        mock_compute.assert_called_once_with("resume", "jd", structured=structured)

    @patch("job_application.scoring.service.compute_jobbert_skill_match")
    def test_compute_hybrid_match_score_wrapper(self, mock_compute):
        mock_compute.return_value = {
            "match_score": 67,
            "comparison_summary": "JobBERT skill match 67%",
            "scoring_method": "jobbert_knowledge",
            "skills_source": "jobbert_requirements_section",
            "skills_available": True,
            "matched_skills": ["Python"],
            "unmatched_skills": ["Azure"],
            "skill_score": 0.67,
        }
        result = match_score.compute_hybrid_match_score("resume text here", "jd text here")
        self.assertEqual(result["match_score"], 67)
        self.assertEqual(result["match_rank_label"], "Good match")
        self.assertEqual(result["scoring_method"], "jobbert_knowledge")

    def test_build_ats_suggestions_entity_pairs_not_full_jd_sentences(self):
        matched = [
            {
                "required_skill": "PySpark",
                "resume_skill": "Spark",
                "similarity": 0.85,
                "match_type": "semantic",
            },
            {
                "required_skill": "SQL",
                "resume_skill": "Postgres",
                "similarity": 0.82,
                "match_type": "semantic",
            },
        ]
        missing = [
            {
                "required_skill": "Airflow",
                "best_candidate": "Prefect",
                "similarity": 0.62,
                "match_type": "missing",
            },
            {
                "required_skill": "platforms",
                "best_candidate": "Aurora",
                "similarity": 0.40,
                "match_type": "missing",
            },
        ]
        resume = "- Built ETL with Spark and Prefect\n- Hands-on experience Python, Postgres"
        req = (
            "Solid SQL skills and hands-on experience with at least one programming language "
            "(Python, R, etc.)\nStrong Python, PySpark, and SQL skills."
        )
        ats = build_ats_suggestions(resume, req, matched, missing)
        self.assertEqual(len(ats["suggestions"]), 2)
        pairs = {(s["resume_phrase"], s["jd_phrase"]) for s in ats["suggestions"]}
        self.assertIn(("Spark", "PySpark"), pairs)
        self.assertIn(("Postgres", "SQL"), pairs)
        self.assertNotIn("Solid SQL skills", " ".join(s["jd_phrase"] for s in ats["suggestions"]))
        self.assertNotIn("Airflow", [s["jd_phrase"] for s in ats["suggestions"]])

    @patch("job_application.scoring.service.llm_refine_ats_suggestions")
    @patch("job_application.scoring.service.compute_jobbert_skill_match")
    def test_compute_hybrid_includes_llm_ats_when_requested(self, mock_compute, mock_llm_ats):
        mock_compute.return_value = {
            "match_score": 50,
            "comparison_summary": "JobBERT skill match 50%",
            "scoring_method": "jobbert_knowledge",
            "requirements_text": "- Python required",
            "resume_entities_text": "SKILLS\n\nPython, Postgres",
            "resume_skills": ["Python", "Postgres"],
            "matched_details": [
                {
                    "required_skill": "Python",
                    "resume_skill": "Python",
                    "similarity": 1.0,
                    "match_type": "exact",
                }
            ],
            "missing_details": [
                {
                    "required_skill": "SQL",
                    "best_candidate": "Postgres",
                    "similarity": 0.62,
                    "match_type": "missing",
                }
            ],
        }
        mock_llm_ats.return_value = {
            "source": "llm_refined",
            "suggestions": [
                {
                    "resume_phrase": "Postgres",
                    "jd_phrase": "SQL",
                    "match_type": "llm",
                    "similarity": 0.8,
                    "reason": "relational DB",
                }
            ],
            "summary_ru": "OK",
        }
        result = match_score.compute_hybrid_match_score(
            "Python developer",
            "Python required",
            include_ats=True,
            include_ats_llm=True,
        )
        self.assertIn("ats", result)
        self.assertEqual(result["ats"]["source"], "llm_refined")
        mock_llm_ats.assert_called_once()

    @patch("job_application.scoring.service.compute_jobbert_skill_match")
    def test_compute_hybrid_includes_ats_when_requested(self, mock_compute):
        mock_compute.return_value = {
            "match_score": 50,
            "comparison_summary": "JobBERT skill match 50%",
            "scoring_method": "jobbert_knowledge",
            "requirements_text": "- Python required",
            "matched_details": [
                {
                    "required_skill": "Python",
                    "resume_skill": "Python 3",
                    "similarity": 0.9,
                    "match_type": "semantic",
                }
            ],
            "missing_details": [],
        }
        result = match_score.compute_hybrid_match_score(
            "Python 3 developer",
            "Python required",
            include_ats=True,
        )
        self.assertIn("ats", result)
        self.assertGreaterEqual(len(result["ats"]["suggestions"]), 1)


if __name__ == "__main__":
    unittest.main()
