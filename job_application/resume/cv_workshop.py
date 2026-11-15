"""Import workshop scripts from cv/ (render.py, pdf_to_yml_llm.py)."""

from __future__ import annotations

import importlib.util
import sys
from functools import lru_cache
from pathlib import Path
from types import ModuleType

from job_application.config import REPO_ROOT


def _load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load workshop module: {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@lru_cache(maxsize=1)
def pdf_to_yml_module() -> ModuleType:
    return _load_module("cv_workshop_pdf_to_yml", REPO_ROOT / "cv" / "pdf_to_yml_llm.py")


@lru_cache(maxsize=1)
def render_module() -> ModuleType:
    return _load_module("cv_workshop_render", REPO_ROOT / "cv" / "render.py")
