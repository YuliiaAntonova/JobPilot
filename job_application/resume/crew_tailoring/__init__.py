"""L7 CrewAI resume tailoring (from crew_job/L7_job_application_crew.ipynb)."""

from job_application.resume.crew_tailoring.adapter import build_crew_kickoff_inputs
from job_application.resume.crew_tailoring.crew import build_job_application_crew
from job_application.resume.crew_tailoring.runner import run_crew_tailoring

__all__ = [
    "build_crew_kickoff_inputs",
    "build_job_application_crew",
    "run_crew_tailoring",
]
