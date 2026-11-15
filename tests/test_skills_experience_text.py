"""JobBERT resume entity text — structured SKILLS only."""

from __future__ import annotations

import unittest

from job_application.resume.profile_text import (
    categorize_skill_chips,
    chips_from_skills_text,
    expand_skill_fields_in_answers,
    extract_skills_text_for_jobbert,
    format_skills_text_for_chat,
    merge_skill_fields_from_answers,
    parse_skills_text_to_fields,
    skills_from_plain_resume_text,
    structured_skills_list,
)


class TestSkillsCategorization(unittest.TestCase):
    def test_mixed_hursh_skills_split_into_labeled_rows(self):
        mixed = (
            "Technical Skills: Python · PySpark · Pandas · Flask · SQL · Oracle · Postgres · Redis · Git · GitHub · Gitlab · JIRA\n"
            "Technologies: Asana · PyCharm · AWS Glue · Step Functions · Athena · Lambda · Snowflake · Power BI · Ray · pytest · Aurora · OpenSearch · ETL"
        )
        formatted = format_skills_text_for_chat(mixed)
        self.assertIn("Hands-on experience", formatted)
        self.assertIn("Python", formatted)
        self.assertIn("Flask", formatted)
        self.assertIn("Knowledge of", formatted)
        self.assertIn("PySpark", formatted)
        self.assertIn("SQL (DML)", formatted)
        self.assertIn("Oracle", formatted)
        self.assertIn("Git (GitHub", formatted)
        self.assertIn("GitLab", formatted)
        self.assertIn("Experience with JIRA, Asana", formatted)
        self.assertIn("Tools:", formatted)
        self.assertIn("PyCharm", formatted)
        self.assertNotIn("Technical Skills:", formatted)
        self.assertNotIn("Technologies:", formatted)

    def test_chips_from_skills_text_reads_hursh_labels(self):
        mixed = "Technical Skills: Python · Flask\nTechnologies: PyCharm · pytest"
        chips = chips_from_skills_text(mixed)
        self.assertIn("Python", chips)
        self.assertIn("PyCharm", chips)

    def test_categorize_skill_chips_groups_by_role(self):
        lines = categorize_skill_chips(["Python", "Flask", "Pandas", "JIRA", "PyCharm"])
        joined = "\n".join(lines)
        self.assertIn("Hands-on experience Python, Flask", joined)
        self.assertIn("Knowledge of Pandas", joined)
        self.assertIn("Experience with JIRA", joined)
        self.assertIn("Tools: PyCharm", joined)

    def test_user_skill_layout_parses_all_fields_including_databases_and_git(self):
        expected = """Hands-on experience Python, PySpark, Pandas, Ray, Flask
Knowledge of Agentic AI
SQL (DML), Oracle, Postgres, Redis, Snowflake, Aurora, OpenSearch, Delta Table
GitHub, Gitlab
Experience with JIRA, Asana
Tools: Apache Airflow, AWS Glue, Step Functions, Athena, Lambda, Power BI, PyTest, ETL, Databricks
Domain expertise: Finance, Logistics"""
        fields = parse_skills_text_to_fields(expected)
        self.assertIn("PySpark", fields.get("skill_handsOn", ""))
        self.assertEqual(fields.get("skill_knowledge"), "Agentic AI")
        self.assertIn("Delta Table", fields.get("skill_databases", ""))
        self.assertIn("Snowflake", fields.get("skill_databases", ""))
        self.assertIn("GitHub", fields.get("skill_git", ""))
        self.assertIn("GitLab", fields.get("skill_git", ""))
        self.assertIn("Databricks", fields.get("skill_tools", ""))
        self.assertIn("Apache Airflow", fields.get("skill_tools", ""))

    def test_single_paragraph_skills_split_into_all_fields(self):
        paragraph = (
            "Hands-on experience Python, PySpark, Pandas, Ray, Flask. "
            "SQL (DML), Oracle, Postgres, Redis, Snowflake, Aurora, OpenSearch, Delta Table. "
            "Knowledge of Agentic AI. Experience with JIRA, Asana. "
            "Tools: Apache Airflow, AWS Glue, PyTest, Power BI. "
            "Domain expertise: Finance, Logistics"
        )
        fields = parse_skills_text_to_fields(paragraph)
        self.assertIn("Python", fields.get("skill_handsOn", ""))
        self.assertIn("Agentic AI", fields.get("skill_knowledge", ""))
        self.assertIn("Snowflake", fields.get("skill_databases", ""))
        self.assertIn("JIRA", fields.get("skill_collab", ""))
        self.assertIn("Apache Airflow", fields.get("skill_tools", ""))
        self.assertIn("Finance", fields.get("skill_domain", ""))

    def test_expand_fills_missing_skill_fields_from_categorized_skills(self):
        skills = """Hands-on experience Python, Flask
Knowledge of Agentic AI
Cloud & Data: SQL (DML), Oracle, Postgres
Tools: Git, GitHub, GitLab, JIRA, Asana, PyCharm"""
        expanded = expand_skill_fields_in_answers(
            {
                "skills": skills,
                "skill_handsOn": "Python, Flask",
            }
        )
        self.assertEqual(expanded.get("skill_knowledge"), "Agentic AI")
        self.assertIn("Oracle", expanded.get("skill_databases", ""))
        self.assertIn("JIRA", expanded.get("skill_collab", ""))
        self.assertIn("PyCharm", expanded.get("skill_tools", ""))

    def test_parse_and_merge_skill_fields_for_chat_editor(self):
        formatted = format_skills_text_for_chat(
            "Technical Skills: Python · Flask · SQL · JIRA\nTechnologies: PyCharm · Pandas · Ray"
        )
        fields = parse_skills_text_to_fields(formatted)
        self.assertIn("Python", fields.get("skill_handsOn", ""))
        self.assertIn("Flask", fields.get("skill_handsOn", ""))
        self.assertIn("Pandas", fields.get("skill_knowledge", ""))
        self.assertIn("Ray", fields.get("skill_knowledge", ""))
        self.assertIn("JIRA", fields.get("skill_collab", ""))
        self.assertIn("PyCharm", fields.get("skill_tools", ""))

        merged = merge_skill_fields_from_answers(fields)
        self.assertIn("Hands-on experience Python, Flask", merged)
        self.assertNotIn("Technical Skills:", merged)

        expanded = expand_skill_fields_in_answers({"skills": formatted})
        self.assertTrue(expanded.get("skill_handsOn"))
        self.assertIn("Hands-on experience", expanded.get("skills", ""))


class TestStructuredSkillsList(unittest.TestCase):
    def test_llm_json_shape(self):
        data = {
            "skills": ["Python", "PySpark", "SQL"],
            "skills_text": "Flask, Oracle, Postgres",
            "education": [{"school": "Donetsk National Technical University"}],
        }
        skills = structured_skills_list(data)
        self.assertIn("Python", skills)
        self.assertIn("Flask", skills)
        self.assertNotIn("Donetsk", skills)

    def test_technical_skills_camel_case(self):
        data = {"technicalSkills": ["Python", "SQL"], "technologies": ["AWS Glue", "Ray"]}
        skills = structured_skills_list(data)
        self.assertIn("Python", skills)
        self.assertIn("AWS Glue", skills)


class TestExtractSkillsFromPlainText(unittest.TestCase):
    def test_yuliia_pdf_skills_before_skills_header(self):
        """PDF extract order: Hands-on / Tools rows may appear before the SKILLS heading."""
        resume = """
Built data pipelines on Ray for continuous analytics.

Hands-on experience Python, PySpark, Pandas, Flask
SQL (DML), Oracle, Postgres, Redis
Git (GitHub, Gitlab)
Experience with JIRA, Asana
Tools: PyCharm, AWS Glue, Step Functions
Domain expertise: Finance, Logistics

SKILLS
OBJECTIVE
Data Engineer role
EXPERIENCE
Built ETL pipelines.
""".strip()
        from job_application.resume.profile_text import parse_skills_text_to_fields

        answers = parse_skills_text_to_fields(resume)
        self.assertIn("Python", answers.get("skill_handsOn", ""))
        self.assertIn("PySpark", answers.get("skill_handsOn", ""))
        self.assertIn("Oracle", answers.get("skill_databases", ""))
        self.assertIn("GitHub", answers.get("skill_git", ""))
        self.assertIn("JIRA", answers.get("skill_collab", ""))
        self.assertIn("PyCharm", answers.get("skill_tools", ""))


class TestExtractSkillsTextForJobbert(unittest.TestCase):
    def test_prefers_structured_over_plain_text(self):
        resume = """
EDUCATION
Master's degree in Economics
Donetsk National Technical University

EXPERIENCE
Built data pipelines on Ray.
""".strip()
        structured = {"skills": ["Python", "SQL", "data pipelines"]}

        text, source = extract_skills_text_for_jobbert(resume, structured)
        self.assertEqual(source, "structured_profile")
        self.assertIn("Python", text)
        self.assertNotIn("Economics", text)
        self.assertNotIn("Built data pipelines", text)

    def test_yuliia_skills_paragraph_parsed_into_chips(self):
        resume = """
SKILLS

Hands-on experience Python, PySpark, Pandas, Flask. SQL (DML), Oracle, Postgres, Redis. Git (GitHub, Gitlab). Experience with JIRA, Asana. Tools: PyCharm, AWS Glue, Step Functions, Athena, Lambda, Snowflake, Power BI. Domain expertise: Finance, Logistics, Manufacturing.
""".strip()
        skills = skills_from_plain_resume_text(resume)
        for expected in (
            "Python",
            "PySpark",
            "AWS Glue",
            "SQL",
            "Git",
            "GitHub",
            "Snowflake",
            "Power BI",
        ):
            self.assertIn(expected, skills, msg=f"missing {expected}: {skills}")

    def test_plain_text_skills_section_without_education(self):
        resume = """
EDUCATION
Master's degree in Economics

SKILLS
Hands-on experience Python, PySpark, Pandas, Flask
SQL (DML), Oracle, Postgres, Redis

EXPERIENCE
Built data pipelines on Ray for continuous analytics.
""".strip()

        text, source = extract_skills_text_for_jobbert(resume)
        self.assertEqual(source, "skills_section")
        self.assertIn("Python", text)
        self.assertNotIn("Economics", text)
        self.assertNotIn("Built data pipelines", text)


if __name__ == "__main__":
    unittest.main()
