"""ATS suggestions — notebook entity match only."""

from __future__ import annotations

import unittest

from job_application.scoring.ats import apply_ats_entity_substitutions, build_ats_suggestions


class TestAtsSuggestions(unittest.TestCase):
    def test_entity_pairs_only(self):
        matched = [
            {
                "required_skill": "SQL",
                "resume_skill": "Flask SQL",
                "similarity": 0.95,
                "match_type": "token",
            },
            {
                "required_skill": "PySpark",
                "resume_skill": "Spark",
                "similarity": 0.85,
                "match_type": "semantic",
            },
        ]
        missing = [
            {
                "required_skill": "data pipelines",
                "best_candidate": "pipeline execution",
                "similarity": 0.73,
                "match_type": "missing",
            },
            {
                "required_skill": "modeling",
                "best_candidate": "Automated",
                "similarity": 0.38,
                "match_type": "missing",
            },
        ]
        ats = build_ats_suggestions("resume", "jd", matched, missing)
        pairs = {(s["resume_phrase"], s["jd_phrase"]) for s in ats["suggestions"]}
        self.assertIn(("Flask SQL", "SQL"), pairs)
        self.assertIn(("pipeline execution", "data pipelines"), pairs)
        self.assertNotIn(("Automated", "modeling"), pairs)
        for item in ats["suggestions"]:
            self.assertNotIn("Solid SQL skills", item["jd_phrase"])

    def test_apply_substitutions_to_structured_highlights(self):
        from job_application.scoring.ats import apply_substitutions_to_structured

        structured = {
            "experience": [
                {
                    "highlights": [
                        "Developed and implemented data models and schemas optimised for analytics",
                        "Work with Aurora and OpenSearch for data storage and querying.",
                    ]
                }
            ]
        }
        suggestions = [
            {
                "resume_phrase": "data models",
                "jd_phrase": "Data Modeling",
                "match_type": "phrase_semantic",
                "similarity": 0.8,
            },
            {
                "resume_phrase": "data storage and querying",
                "jd_phrase": "Data Platforms",
                "match_type": "phrase_semantic",
                "similarity": 0.7,
            },
        ]
        out = apply_substitutions_to_structured(structured, suggestions)
        self.assertIn("Data Modeling", out["experience"][0]["highlights"][0])
        self.assertIn("Data Platforms", out["experience"][0]["highlights"][1])

    def test_safe_orchestration_substitution_keeps_glue_context(self):
        from job_application.scoring.ats import apply_ats_entity_substitutions

        before = "Work with Step Functions to orchestrate Glue Jobs and automate daily pipelines."
        for pair in (
            {
                "resume_phrase": "orchestrate Glue Jobs and automate",
                "jd_phrase": "orchestration tools",
            },
            {
                "resume_phrase": "orchestrate Glue Jobs and automate daily pipelines",
                "jd_phrase": "orchestration tools daily pipelines",
            },
        ):
            suggestions = [{**pair, "match_type": "phrase_semantic", "similarity": 0.61}]
            after = apply_ats_entity_substitutions(before, suggestions)
            self.assertIn("orchestration tools", after.casefold())
            self.assertIn("Glue Jobs", after)
            self.assertNotIn("orchestrate Glue Jobs", after)
            self.assertNotIn("orchestration tools daily pipelines", after.casefold())

    def test_no_double_modern_prefix_on_data_pipelines(self):
        from job_application.scoring.ats import apply_ats_entity_substitutions

        suggestions = [
            {
                "resume_phrase": "data pipelines",
                "jd_phrase": "modern data pipelines",
                "match_type": "phrase_semantic",
                "similarity": 0.92,
            }
        ]
        before = "Build and maintain modern data pipelines for analytics."
        after = apply_ats_entity_substitutions(before, suggestions)
        self.assertEqual(after, before)

    def test_apply_phrase_with_trailing_period(self):
        from job_application.scoring.ats import apply_ats_entity_substitutions

        suggestions = [
            {
                "resume_phrase": "data storage and querying.",
                "jd_phrase": "data platforms",
                "match_type": "phrase_semantic",
            }
        ]
        before = "Work with OpenSearch for data storage and querying."
        after = apply_ats_entity_substitutions(before, suggestions)
        self.assertIn("data platforms", after)
        self.assertNotIn("storage and querying", after)

    def test_apply_substitutions_highlights_target_entities(self):
        suggestions = [{"resume_phrase": "Flask SQL", "jd_phrase": "SQL", "match_type": "token"}]
        before = "Hands-on experience Python, Flask SQL, Pandas"
        after = apply_ats_entity_substitutions(before, suggestions)
        self.assertIn("SQL", after)
        self.assertNotIn("Flask SQL", after)

    def test_postgres_replaces_all_occurrences_without_duplicates(self):
        from job_application.scoring.ats import apply_ats_entity_substitutions

        before = (
            "Technical Skills: Python · PySpark · Pandas · Flask · SQL · Oracle · Postgres · Redis · Git\n"
            "Technologies: AWS Glue · Step Functions · Athena · Aurora · OpenSearch · Postgres · Redis"
        )
        suggestions = [
            {"resume_phrase": "Postgres", "jd_phrase": "PostgreSQL", "match_type": "token", "similarity": 0.9},
        ]
        after = apply_ats_entity_substitutions(before, suggestions)
        self.assertNotIn("Postgres", after)
        self.assertIn("PostgreSQL · Redis", after)
        self.assertEqual(after.count("PostgreSQL"), 2)
        self.assertNotIn("PostgreSQL Redis", after)

    def test_postgres_removed_when_postgresql_already_on_line(self):
        from job_application.scoring.ats import apply_ats_entity_substitutions

        before = "Technologies: Aurora · PostgreSQL · Postgres · Redis"
        suggestions = [
            {"resume_phrase": "Postgres", "jd_phrase": "PostgreSQL", "match_type": "token", "similarity": 0.9},
        ]
        after = apply_ats_entity_substitutions(before, suggestions)
        self.assertNotIn("Postgres", after)
        self.assertEqual(after.count("PostgreSQL"), 1)
        self.assertIn("PostgreSQL · Redis", after)

    def test_apply_token_match_when_entity_split_across_lines(self):
        suggestions = [
            {"resume_phrase": "Flask SQL", "jd_phrase": "SQL", "match_type": "token"},
            {"resume_phrase": "pipeline execution", "jd_phrase": "data pipelines", "match_type": "near_miss"},
        ]
        before = (
            "Hands-on experience Python, PySpark, Pandas, Flask\n"
            "SQL (DML), Oracle, Postgres, Redis\n"
            "Automated pipeline execution."
        )
        after = apply_ats_entity_substitutions(before, suggestions)
        self.assertIn("SQL (DML)", after)
        self.assertNotIn("Flask", after)
        self.assertIn("data pipelines", after)
        self.assertNotIn("pipeline execution", after)


if __name__ == "__main__":
    unittest.main()
