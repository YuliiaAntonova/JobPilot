"""Backward-compatible re-export — prefer job_application.resume.template_extractor."""

from job_application.resume.template_extractor import (  # noqa: F401
    extract_fields,
    get_field_names,
    get_target_fields,
    validate_shape,
)

__all__ = ["extract_fields", "get_field_names", "get_target_fields", "validate_shape"]
