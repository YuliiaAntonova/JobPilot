"""L7 CrewAI resume tailoring (from crew_job/L7_job_application_crew.ipynb).

Imports are lazy so resume PDF parse / RAG prepare does not load CrewAI.
"""

from __future__ import annotations

__all__ = [
    "build_crew_kickoff_inputs",
    "build_job_application_crew",
    "run_crew_tailoring",
]


def __getattr__(name: str):
    if name == "build_crew_kickoff_inputs":
        from job_application.resume.crew_tailoring.adapter import build_crew_kickoff_inputs

        return build_crew_kickoff_inputs
    if name == "build_job_application_crew":
        from job_application.resume.crew_tailoring.crew import build_job_application_crew

        return build_job_application_crew
    if name == "run_crew_tailoring":
        from job_application.resume.crew_tailoring.runner import run_crew_tailoring

        return run_crew_tailoring
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
