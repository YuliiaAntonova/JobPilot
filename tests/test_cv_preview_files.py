"""Tests for local cv.yml / cv.html preview writer."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from job_application.resume.cv_preview_files import write_cv_preview_files


class TestCvPreviewFiles(unittest.TestCase):
    def test_writes_yml_and_html(self):
        structured = {
            "basics": {
                "name": "Jane Doe",
                "headline": "Data Engineer",
                "email": "jane@example.com",
                "summary": "Builds pipelines.",
            },
            "experience": [
                {
                    "company": "Acme",
                    "title": "Engineer",
                    "period": "2020 – Present",
                    "bullets": ["Built ETL."],
                }
            ],
            "resume_template": "harvard",
            "chat_format": "cv_yml",
        }
        with tempfile.TemporaryDirectory() as tmp:
            preview_dir = Path(tmp)
            with patch("job_application.resume.cv_pdf_export.CV_PREVIEW_DIR", preview_dir):
                with patch("job_application.resume.cv_preview_files.CV_PREVIEW_ENABLED", True):
                    paths = write_cv_preview_files(structured)
            self.assertIsNotNone(paths)
            yml_path, html_path = paths
            self.assertTrue(yml_path.exists())
            self.assertTrue(html_path.exists())
            self.assertIn("Jane Doe", yml_path.read_text(encoding="utf-8"))
            self.assertIn("Jane Doe", html_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
