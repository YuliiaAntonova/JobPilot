"""Service layer — composition helpers (facade over domain packages)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from job_application.application.export_service import ExportService
    from job_application.application.job_service import JobService

_export: "ExportService | None" = None


def get_job_service(db: "Session") -> "JobService":
    from job_application.application.job_service import JobService

    return JobService(db)


def get_export_service() -> "ExportService":
    global _export
    if _export is None:
        from job_application.application.export_service import ExportService

        _export = ExportService()
    return _export
