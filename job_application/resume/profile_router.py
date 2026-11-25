"""Resume profile in PostgreSQL (cabinet)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from job_application.config import APP_LLM_MODEL
from job_application.models.db import get_db
from job_application.repositories import users as db_users
from job_application.routers.deps import get_current_user
from job_application.models import User
from job_application.resume.profile_text import structured_profile_to_plain_text
from job_application.resume.profile_service import (
    attach_resume_plain_text,
    chat_answers_with_resume_plain_text,
    profile_dict_from_chat_answers,
    profile_dict_from_structured,
    save_profile_from_chat_answers,
    structured_for_render_from_profile,
    update_profile_plain_text,
)
from job_application.services import get_export_service
from job_application.shared.parsing import resume_bytes_to_plain_text
from job_application.shared.forms import ChatAnswersBody

router = APIRouter(prefix="/profile", tags=["profile"])


class ProfileUpdateBody(BaseModel):
    desired_role: str | None = None
    profile_text: str | None = None
    reparse_structured: bool = True
    model: str | None = None
    ats_substitutions: list[dict] | None = None


class ProfileImportBody(BaseModel):
    structured: dict = Field(default_factory=dict)
    profile_text: str = ""
    desired_role: str | None = None
    source: str | None = None
    chat_answers: dict | None = None


class ProfileStructuredBody(BaseModel):
    structured: dict = Field(default_factory=dict)
    profile_text: str | None = None
    source: str = "tailored"


class RenderResumeBody(BaseModel):
    structured: dict = Field(default_factory=dict)
    profile_text: str = ""
    chat_answers: dict[str, str] | None = None


def _require_structured(data: dict) -> dict:
    if not isinstance(data, dict) or not data:
        raise HTTPException(status_code=400, detail="structured must be a non-empty JSON object")
    return data


def _structured_for_render(structured: dict, profile_text: str = "") -> dict:
    data = dict(structured or {})
    plain = (profile_text or "").strip()
    if plain and not str(data.get("_resume_plain_text") or "").strip():
        data["_resume_plain_text"] = plain
    return data


def _structured_from_render_body(body: RenderResumeBody) -> dict:
    from job_application.documents.resume_normalize import _has_structured_experience_bullets
    from job_application.resume.profile_service import attach_resume_template

    structured = body.structured if isinstance(body.structured, dict) else {}
    if _has_structured_experience_bullets(structured):
        return attach_resume_template(_structured_for_render(structured, body.profile_text or ""))

    answers = body.chat_answers if isinstance(body.chat_answers, dict) else {}
    cleaned = {k: str(v).strip() for k, v in answers.items() if str(v).strip()}
    if cleaned:
        payload = profile_dict_from_chat_answers(cleaned)
        structured_out = dict(payload["structured"])
        stored = body.structured if isinstance(body.structured, dict) else {}
        structured_out["resume_template"] = "harvard"
        plain = str(
            stored.get("_resume_plain_text") or structured_out.get("_resume_plain_text") or ""
        ).strip()
        if plain:
            structured_out = attach_resume_plain_text(structured_out, plain)
        return attach_resume_template(
            _structured_for_render(structured_out, payload.get("profile_text") or body.profile_text)
        )
    return attach_resume_template(_structured_for_render(_require_structured(structured), body.profile_text))


def _structured_for_export(row) -> dict:
    return _structured_for_render(structured_for_render_from_profile(row), row.profile_text or "")


def _resume_download_filename_from_structured(structured: dict, ext: str) -> str:
    name = f"resume.{ext}"
    basics = structured.get("basics") if isinstance(structured.get("basics"), dict) else {}
    full = str(basics.get("name") or "").strip()
    if not full:
        pers = structured.get("personal") if isinstance(structured.get("personal"), dict) else {}
        full = str(pers.get("full_name") or "").strip()
        if not full:
            first = str(pers.get("first_name") or "").strip()
            last = str(pers.get("last_name") or "").strip()
            full = f"{first} {last}".strip()
    if full:
        safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in full)[:60]
        if safe:
            name = f"{safe}_resume.{ext}"
    return name


def _resume_download_filename(row, ext: str) -> str:
    structured = row.structured if isinstance(row.structured, dict) else {}
    return _resume_download_filename_from_structured(structured, ext)


@router.post("/render-resume.pdf")
def render_resume_pdf_from_json(body: RenderResumeBody, user: User = Depends(get_current_user)):
    """PDF из JSON в теле запроса — без чтения resume_profiles в PostgreSQL."""
    structured = _structured_from_render_body(body)
    try:
        pdf_bytes = get_export_service().export_pdf(structured)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to build PDF: {e}") from e
    name = _resume_download_filename_from_structured(structured, "pdf")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.get("/me/resume.pdf")
def download_my_resume_pdf(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """PDF резюме: structured (чат/БД) → cv/render.py → Chrome headless."""
    row = db_users.get_profile_for_user(db, user.id)
    if row is None or not isinstance(row.structured, dict) or not row.structured:
        raise HTTPException(status_code=404, detail="Profile not found. Create a resume via chat or PDF first.")
    try:
        pdf_bytes = get_export_service().export_pdf(_structured_for_export(row))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to build PDF: {e}") from e
    name = _resume_download_filename(row, "pdf")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.get("/me/cv.html")
def preview_my_cv_html(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Harvard cv.html from workshop preview dir (updated by render.py on profile save)."""
    from job_application.config import CV_PREVIEW_ENABLED
    from job_application.resume.cv_pdf_export import cv_preview_paths

    _ = db_users.get_profile_for_user(db, user.id)
    if not CV_PREVIEW_ENABLED:
        raise HTTPException(status_code=503, detail="CV preview disabled (CV_PREVIEW_ENABLED=0)")
    _yml_path, html_path = cv_preview_paths()
    if not html_path.is_file():
        raise HTTPException(
            status_code=404,
            detail="cv.html has not been generated yet. Save the resume first (Safe YAML → generate).",
        )
    return FileResponse(
        html_path,
        media_type="text/html; charset=utf-8",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@router.get("/me/cv-tailored-draft.html")
def preview_job_tailored_cv_html(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """HTML preview for JD-specific tailoring (cv_tailored_draft.html — not cabinet cv.html)."""
    from job_application.config import CV_PREVIEW_ENABLED
    from job_application.resume.cv_pdf_export import job_tailored_draft_preview_paths

    _ = db_users.get_profile_for_user(db, user.id)
    if not CV_PREVIEW_ENABLED:
        raise HTTPException(status_code=503, detail="CV preview disabled (CV_PREVIEW_ENABLED=0)")
    _yml_path, html_path = job_tailored_draft_preview_paths()
    if not html_path.is_file():
        raise HTTPException(
            status_code=404,
            detail="Preview has not been created yet. Run resume tailoring for the job.",
        )
    return FileResponse(
        html_path,
        media_type="text/html; charset=utf-8",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@router.get("/me/resume.yml")
def download_my_resume_yml(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Export profile as workshop-style cv.yml (Harvard schema)."""
    from job_application.resume.cv_yaml import structured_to_harvard_yaml

    row = db_users.get_profile_for_user(db, user.id)
    if row is None or not isinstance(row.structured, dict) or not row.structured:
        raise HTTPException(status_code=404, detail="Profile not found. Create a resume via chat or PDF first.")
    structured = _structured_for_export(row)
    try:
        yaml_text = structured_to_harvard_yaml(structured)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to export YAML: {e}") from e
    name = _resume_download_filename(row, "yml")
    return Response(
        content=yaml_text,
        media_type="application/x-yaml",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.post("/import-yml")
async def import_profile_yml(
    resume_yml: UploadFile | None = File(None),
    yaml_text: str | None = Form(None),
    desired_role: str | None = Form(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Import workshop-style cv.yml into the profile (sets resume_template=harvard)."""
    from job_application.resume.cv_yaml import harvard_yaml_to_structured

    text = ""
    if resume_yml is not None:
        raw = await resume_yml.read()
        if raw:
            text = raw.decode("utf-8", errors="replace").strip()
    if not text and yaml_text and yaml_text.strip():
        text = yaml_text.strip()
    if len(text) < 10:
        raise HTTPException(status_code=400, detail="YAML file or yaml_text is required (minimum 10 characters).")

    try:
        structured = harvard_yaml_to_structured(text)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse YAML: {e}") from e

    plain = structured_profile_to_plain_text(structured)
    profile = profile_dict_from_structured(
        structured,
        profile_text=plain,
        desired_role=(desired_role or "").strip() or None,
        source="yaml",
    )
    saved = db_users.upsert_profile(
        db,
        user.id,
        structured=profile["structured"],
        profile_text=profile["profile_text"],
        desired_role=profile.get("desired_role") or None,
        source=profile.get("source"),
        chat_answers=profile.get("chat_answers"),
    )
    from job_application.resume.cv_preview_files import cv_preview_paths_api, write_cv_preview_files

    write_cv_preview_files(profile["structured"])
    return {"profile": db_users.profile_to_api_dict(saved), "cv_preview": cv_preview_paths_api()}


@router.get("/me")
def get_my_profile(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db_users.get_profile_for_user(db, user.id)
    if row is None:
        return {"profile": None}
    return {"profile": db_users.profile_to_api_dict(row)}


@router.put("/me")
def update_my_profile(
    body: ProfileUpdateBody,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if body.profile_text is None and body.desired_role is None:
        raise HTTPException(status_code=400, detail="Provide desired_role and/or profile_text.")

    row = db_users.get_profile_for_user(db, user.id)
    if row is None:
        raise HTTPException(status_code=404, detail="Profile not found. Create a resume via chat or PDF first.")

    if body.profile_text is not None:
        try:
            row = update_profile_plain_text(
                db,
                user.id,
                body.profile_text,
                reparse_structured=body.reparse_structured,
                llm_model=body.model,
                ats_substitutions=body.ats_substitutions,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    if body.desired_role is not None:
        row = db_users.update_profile_fields(db, user.id, desired_role=body.desired_role)
        if row is None:
            raise HTTPException(status_code=404, detail="Profile not found. Create a resume via chat or PDF first.")

    return {"profile": db_users.profile_to_api_dict(row)}


@router.delete("/me")
def delete_my_profile(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    deleted = db_users.delete_profile_for_user(db, user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Profile not found")
    return {"ok": True}


@router.post("/preview-cv-files")
def preview_cv_files(
    body: ChatAnswersBody,
    user: User = Depends(get_current_user),
):
    """
    Regenerate local cv/cv.yml and cv/cv.html from current chat answers (no DB write).
    Use while filling the section editor to inspect workshop files on disk.
    """
    from job_application.resume.cv_preview_files import cv_preview_paths_api, write_cv_preview_files
    from job_application.resume.profile_text import chat_answers_to_structured

    answers = {k: str(v).strip() for k, v in (body.answers or {}).items() if str(v).strip()}
    if not answers:
        raise HTTPException(status_code=400, detail="answers are empty")
    structured = chat_answers_to_structured(answers)
    paths = write_cv_preview_files(structured)
    if paths is None:
        raise HTTPException(status_code=503, detail="CV preview disabled (CV_PREVIEW_ENABLED=0)")
    yml_path, html_path = paths
    return {
        "ok": True,
        **cv_preview_paths_api(),
        "bytes": {"cv_yml": yml_path.stat().st_size, "cv_html": html_path.stat().st_size},
    }


@router.post("/from-chat")
def save_profile_from_chat(
    body: ChatAnswersBody,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    answers = {k: str(v).strip() for k, v in (body.answers or {}).items() if str(v).strip()}
    missing = []
    if not (answers.get("name") or answers.get("fullName")):
        missing.append("name")
    if not answers.get("email"):
        missing.append("email")
    if not (answers.get("headline") or answers.get("desiredPosition")):
        missing.append("headline")
    if missing:
        raise HTTPException(status_code=400, detail=f"Required fields: {', '.join(missing)}")

    saved = save_profile_from_chat_answers(db, user.id, answers)
    from job_application.resume.cv_preview_files import cv_preview_paths_api

    return {"profile": db_users.profile_to_api_dict(saved), "cv_preview": cv_preview_paths_api()}


@router.post("/from-resume")
async def save_profile_from_resume(
    resume_pdf: UploadFile | None = File(None),
    resume_text: str | None = Form(None),
    model: str | None = Form(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    raw = b""
    pdf_filename: str | None = None
    if resume_pdf is not None:
        raw = await resume_pdf.read()
        pdf_filename = resume_pdf.filename

    text = (resume_text or "").strip()
    llm_model = model or APP_LLM_MODEL
    from job_application.resume.parser import DefaultResumePdfParser

    parser = DefaultResumePdfParser()
    try:
        if raw:
            text, structured, _seed = await parser.parse_bytes(
                pdf_filename, raw, model=llm_model
            )
        elif text:
            text, structured, _seed = await parser.parse_text(text, model=llm_model)
        else:
            raise ValueError("PDF/TXT file or resume_text is required (minimum 20 characters).")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        from job_application.shared.llm.errors import llm_error_message

        raise HTTPException(status_code=502, detail=f"LLM error: {llm_error_message(e)}") from e

    plain = structured_profile_to_plain_text(structured)
    profile = profile_dict_from_structured(structured, profile_text=plain, source="pdf")
    saved = db_users.upsert_profile(
        db,
        user.id,
        structured=profile["structured"],
        profile_text=profile["profile_text"],
        desired_role=profile.get("desired_role") or None,
        source=profile.get("source"),
        chat_answers=profile.get("chat_answers"),
    )
    from job_application.resume.cv_preview_files import cv_preview_paths_api, write_cv_preview_files

    write_cv_preview_files(profile["structured"])
    return {
        "profile": db_users.profile_to_api_dict(saved),
        "model": llm_model,
        "cv_preview": cv_preview_paths_api(),
    }


@router.post("/from-structured")
def save_profile_from_structured(
    body: ProfileStructuredBody,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Save cv_tailored structured YAML to cabinet (Harvard schema → PDF pipeline)."""
    from job_application.resume.cv_preview_files import cv_preview_paths_api, write_cv_preview_files

    structured = _require_structured(body.structured)
    plain = (body.profile_text or "").strip() or structured_profile_to_plain_text(structured)
    if len(plain) < 20:
        raise HTTPException(status_code=400, detail="profile_text is too short")

    profile = profile_dict_from_structured(
        structured,
        profile_text=plain,
        source=(body.source or "tailored").strip() or "tailored",
    )
    saved = db_users.upsert_profile(
        db,
        user.id,
        structured=profile["structured"],
        profile_text=profile["profile_text"],
        desired_role=profile.get("desired_role") or None,
        source=profile.get("source"),
        chat_answers=profile.get("chat_answers"),
    )
    write_cv_preview_files(profile["structured"])
    return {"profile": db_users.profile_to_api_dict(saved), "cv_preview": cv_preview_paths_api()}


@router.post("/import")
def import_profile(
    body: ProfileImportBody,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Импорт профиля из localStorage при первом входе после миграции."""
    structured = _require_structured(body.structured)
    plain = (body.profile_text or "").strip() or structured_profile_to_plain_text(structured)
    if len(plain) < 20:
        raise HTTPException(status_code=400, detail="profile_text is too short for import")

    profile = profile_dict_from_structured(
        structured,
        profile_text=plain,
        desired_role=(body.desired_role or "").strip() or None,
        source=body.source,
        chat_answers=body.chat_answers,
    )
    return {"profile": profile}
