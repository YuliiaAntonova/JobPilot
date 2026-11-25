"""CLI/shim — YAML write helpers live in job_application.resume.cv_yml_io."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from job_application.resume.cv_yml_io import (  # noqa: E402,F401
    MONTHS,
    normalize_dates,
    write_cv_yml,
)

__all__ = ["MONTHS", "normalize_dates", "write_cv_yml"]
