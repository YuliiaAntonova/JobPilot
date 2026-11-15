"""Phrase-level ATS — notebook parity."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from job_application.scoring.ats import (
    filter_confident_ats_suggestions,
    is_boosted_phrase_substitution,
    merge_ats_suggestions,
)
from job_application.scoring.ats_phrase import (
    _pick_phrase_semantic_hit,
    extract_jd_phrase_targets,
    extract_resume_phrase_targets,
    resume_text_for_phrase_ats,
)


class TestAtsPhraseHelpers(unittest.TestCase):
    def test_filter_confident_skips_weak_phrase_pairs(self):
        items = [
            {"resume_phrase": "pipeline execution", "jd_phrase": "data pipelines", "match_type": "phrase_semantic", "similarity": 0.75},
            {"resume_phrase": "data storage and querying", "jd_phrase": "data platforms", "match_type": "phrase_semantic", "similarity": 0.57},
            {"resume_phrase": "Postgres", "jd_phrase": "SQL", "match_type": "near_miss", "similarity": 0.72},
        ]
        confident = filter_confident_ats_suggestions(items, min_phrase_sim=0.65)
        pairs = {(s["resume_phrase"], s["jd_phrase"]) for s in confident}
        self.assertIn(("pipeline execution", "data pipelines"), pairs)
        self.assertIn(("Postgres", "SQL"), pairs)
        self.assertIn(("data storage and querying", "data platforms"), pairs)
        boosted = next(s for s in confident if s["resume_phrase"] == "data storage and querying")
        self.assertEqual(boosted.get("phrase_confidence"), "lexical_boost")

    def test_platform_storage_boost_requires_discovery_threshold(self):
        self.assertTrue(
            is_boosted_phrase_substitution(
                "data storage and querying.",
                "data platforms",
                0.57,
                discovery_threshold=0.55,
            )
        )
        self.assertFalse(
            is_boosted_phrase_substitution(
                "data storage and querying.",
                "data platforms",
                0.52,
                discovery_threshold=0.55,
            )
        )
        self.assertFalse(
            is_boosted_phrase_substitution(
                "unrelated phrase here",
                "data platforms",
                0.57,
                discovery_threshold=0.55,
            )
        )

    def test_merge_prefers_phrase_over_entity(self):
        phrase = [
            {"resume_phrase": "Automated pipeline execution", "jd_phrase": "data pipelines", "match_type": "phrase_semantic", "similarity": 0.75},
        ]
        entity = [
            {"resume_phrase": "pipeline execution", "jd_phrase": "data pipelines", "match_type": "near_miss", "similarity": 0.73},
        ]
        merged = merge_ats_suggestions(phrase, entity)
        self.assertEqual(len(merged), 2)
        self.assertEqual(merged[0]["match_type"], "phrase_semantic")

    def test_extract_jd_phrase_targets_from_requirements(self):
        req = (
            "Strong Python, PySpark, and SQL skills.\n"
            "Experience with modern data pipelines and data modeling."
        )
        missing = [{"required_skill": "data pipelines"}, {"required_skill": "data modeling"}]
        targets = extract_jd_phrase_targets(req, missing, [])
        lowered = {t.casefold() for t in targets}
        self.assertIn("data pipelines", lowered)
        self.assertIn("data modeling", lowered)

    def test_extract_resume_phrase_targets_literal_only(self):
        resume = (
            "Hands-on experience Python, Flask SQL, Pandas\n"
            "Automated pipeline execution.\n"
            "Datamart pipelines for data processing"
        )
        targets = extract_resume_phrase_targets(resume, resume_skills=["data pipelines"])
        lowered = {t.casefold() for t in targets}
        self.assertIn("automated pipeline execution.", lowered)
        self.assertIn("datamart pipelines for data processing", lowered)
        self.assertNotIn("models and", lowered)


class TestPhraseHitSelection(unittest.TestCase):
    def test_falls_back_when_best_hit_is_exact_jd_phrase(self):
        resume_phrases = ["data pipelines", "Automated pipeline execution."]
        hit_list = [
            {"corpus_id": 0, "score": 1.0},
            {"corpus_id": 1, "score": 0.75},
        ]
        hit, score, phrase = _pick_phrase_semantic_hit(
            "data pipelines",
            hit_list,
            resume_phrases,
            phrase_threshold=0.55,
        )
        self.assertEqual(phrase, "Automated pipeline execution.")
        self.assertAlmostEqual(score, 0.75)

    def test_resume_text_for_phrase_ats_merges_pdf_plain(self):
        structured = {
            "_resume_plain_text": "Automated pipeline execution.\nDatamart pipelines for data processing.",
            "skills": ["Python"],
        }
        merged = resume_text_for_phrase_ats("SKILLS\n\nPython, SQL", structured)
        self.assertIn("Automated pipeline execution.", merged)
        self.assertIn("Datamart pipelines", merged)


class TestComputeHybridPhraseAts(unittest.TestCase):
    @patch("job_application.scoring.service.build_phrase_ats_suggestions")
    @patch("job_application.scoring.service.compute_jobbert_skill_match")
    def test_compute_hybrid_merges_phrase_and_entity(self, mock_compute, mock_phrase):
        mock_compute.return_value = {
            "match_score": 16,
            "comparison_summary": "JobBERT skill match 16%",
            "scoring_method": "jobbert_knowledge",
            "requirements_text": "modern data pipelines required",
            "resume_entities_text": "SKILLS\n\nPython",
            "resume_skills": ["Python", "pipeline execution"],
            "required_skills": ["data pipelines"],
            "matched_details": [],
            "missing_details": [
                {
                    "required_skill": "data pipelines",
                    "best_candidate": "pipeline execution",
                    "similarity": 0.73,
                    "match_type": "missing",
                }
            ],
        }
        mock_phrase.return_value = [
            {
                "resume_phrase": "Automated pipeline execution",
                "jd_phrase": "data pipelines",
                "match_type": "phrase_semantic",
                "similarity": 0.75,
            },
            {
                "resume_phrase": "data storage and querying",
                "jd_phrase": "data platforms",
                "match_type": "phrase_semantic",
                "similarity": 0.57,
            },
        ]
        from job_application.scoring import service as match_score

        result = match_score.compute_hybrid_match_score(
            "Automated pipeline execution.\nPython developer",
            "modern data pipelines required",
            include_ats=True,
        )
        ats = result["ats"]
        self.assertEqual(len(ats["phrase_suggestions"]), 2)
        self.assertGreaterEqual(len(ats["confident_suggestions"]), 2)
        pair_types = {s["match_type"] for s in ats["confident_suggestions"]}
        self.assertIn("phrase_semantic", pair_types)
        self.assertIn("near_miss", pair_types)
        self.assertIn("data pipelines", ats["preview_text"])


if __name__ == "__main__":
    unittest.main()
