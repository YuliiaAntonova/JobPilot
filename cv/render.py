# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""CLI shim — implementation lives in job_application.resume.pdf.render."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from job_application.resume.pdf.render import (  # noqa: E402,F401
    build_html,
    main,
    render_cv_yml_to_html,
    resolve_paths,
)

if __name__ == "__main__":
    raise SystemExit(main())
