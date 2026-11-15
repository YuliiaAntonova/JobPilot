"""OpenAI env helpers for L7 crew + markdown_to_cv_json."""

from __future__ import annotations

import os

from dotenv import find_dotenv, load_dotenv

from job_application.config import REPO_ROOT


def load_env() -> None:
    """Prefer slim repo .env, then cwd / find_dotenv."""
    slim_env = REPO_ROOT / ".env"
    if slim_env.is_file():
        load_dotenv(slim_env, override=False)
    else:
        load_dotenv(find_dotenv(), override=False)


def get_openai_api_key() -> str | None:
    load_env()
    return os.getenv("OPENAI_API_KEY") or None


def get_openai_model_name(default: str = "gpt-4o-mini") -> str:
    load_env()
    return (os.getenv("OPENAI_MODEL_NAME") or default).strip() or default
