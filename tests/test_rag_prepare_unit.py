"""Unit tests for RAG prepare helpers (no network)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from job_application.resume.parser import _cv_to_structured
from job_application.resume.template_extractor import extract_fields, validate_shape
from job_application.resume.rag_prepare.workflow import _strip_json_fence


class TestRagPrepareUnit(unittest.TestCase):
    def test_strip_json_fence(self):
        raw = '```json\n{"basics": {"name": "Ada"}}\n```'
        self.assertEqual(json.loads(_strip_json_fence(raw))["basics"]["name"], "Ada")

    def test_validate_shape_accepts_expanded_lists(self):
        shape = extract_fields(
            {
                "basics": {"name": None, "email": None},
                "skills": [{"group": None, "items": []}],
            }
        )
        filled = {
            "basics": {"name": "Ada", "email": "a@b.c"},
            "skills": [{"group": "Lang", "items": ["Python"]}],
        }
        validate_shape(filled, shape)

    def test_cv_to_structured_maps_selected_projects(self):
        filled = {
            "basics": {
                "name": "Ada Lovelace",
                "headline": "Engineer",
                "location": "London",
                "email": "ada@example.com",
                "phone": "",
                "summary": "Pioneer",
                "note": None,
                "links": [],
            },
            "skills": [],
            "experience": [],
            "experience_earlier": [],
            "selected_projects": [{"name": "Analytical Engine", "url": None, "bullets": ["notes"]}],
            "education": [],
            "certifications": [],
            "languages": [],
        }
        structured = _cv_to_structured(filled, plain_text="Ada Lovelace\nada@example.com")
        self.assertEqual(structured["basics"]["name"], "Ada Lovelace")
        self.assertEqual(structured["projects"][0]["name"], "Analytical Engine")
        self.assertEqual(structured["chat_format"], "cv_yml")

    def test_fill_cv_from_text_mocked(self):
        from job_application.resume.rag_prepare.workflow import fill_cv_from_text

        target = {
            "basics": {"name": None, "email": None},
            "skills": [],
        }

        async def _fake_run(**kwargs):
            del kwargs
            from llama_index.core.workflow import StopEvent

            return StopEvent(
                result={
                    "filled": {"basics": {"name": "Ada", "email": "a@b.c"}, "skills": []},
                    "plain_text": "Ada a@b.c",
                }
            )

        with tempfile.TemporaryDirectory() as tmp:
            template = Path(tmp) / "cv.json"
            template.write_text(json.dumps(target), encoding="utf-8")
            storage = Path(tmp) / "storage"

            with patch(
                "job_application.resume.rag_prepare.workflow.RAGWorkflow.run",
                new=MagicMock(side_effect=_fake_run),
            ):
                import asyncio

                filled, plain, usage = asyncio.run(
                    fill_cv_from_text(
                        "Ada Lovelace ada@example.com engineer",
                        template_file=template,
                        storage_dir=storage,
                    )
                )
        self.assertEqual(filled["basics"]["name"], "Ada")
        self.assertIn("Ada", plain)
        self.assertIn("llm_calls", usage)


if __name__ == "__main__":
    unittest.main()
