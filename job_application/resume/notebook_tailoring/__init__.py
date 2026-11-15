"""Resume tailoring pipeline from Untitled.ipynb (parse → score → tailor → cover letter)."""

from job_application.resume.notebook_tailoring.pipeline import (
    generate_cover_letter,
    get_skill_match_score,
    tailor_resume,
)
from job_application.resume.notebook_tailoring.cv_bridge import (
    apply_notebook_resume_to_cv,
    resume_plain_text_for_tailoring,
)

__all__ = [
    "apply_notebook_resume_to_cv",
    "generate_cover_letter",
    "get_skill_match_score",
    "resume_plain_text_for_tailoring",
    "tailor_resume",
]
