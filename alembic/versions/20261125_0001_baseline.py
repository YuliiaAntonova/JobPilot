"""Baseline schema + application_jobs.user_id

Revision ID: 20261125_0001
Revises:
Create Date: 2026-11-25

Creates tables if missing and ensures application_jobs.user_id exists
(replaces the manual ALTER in job_application.main._ensure_schema).
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "20261125_0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    if not insp.has_table("users"):
        op.create_table(
            "users",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("email", sa.String(length=255), nullable=False),
            sa.Column("password_hash", sa.String(length=255), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_users_email", "users", ["email"], unique=True)

    if not insp.has_table("resume_profiles"):
        op.create_table(
            "resume_profiles",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("structured", sa.JSON(), nullable=False),
            sa.Column("profile_text", sa.Text(), nullable=False),
            sa.Column("desired_role", sa.String(length=255), nullable=True),
            sa.Column("source", sa.String(length=32), nullable=True),
            sa.Column("chat_answers", sa.JSON(), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_resume_profiles_user_id", "resume_profiles", ["user_id"], unique=True)

    if not insp.has_table("application_jobs"):
        op.create_table(
            "application_jobs",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("llm_model", sa.String(length=128), nullable=True),
            sa.Column("jd_text", sa.Text(), nullable=False),
            sa.Column("outputs", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_application_jobs_user_id", "application_jobs", ["user_id"])
        op.create_index("ix_application_jobs_status", "application_jobs", ["status"])
    else:
        cols = {c["name"] for c in insp.get_columns("application_jobs")}
        if "user_id" not in cols:
            op.execute(
                sa.text(
                    "ALTER TABLE application_jobs "
                    "ADD COLUMN IF NOT EXISTS user_id VARCHAR(36) "
                    "REFERENCES users(id)"
                )
            )
            existing_indexes = {ix["name"] for ix in insp.get_indexes("application_jobs")}
            if "ix_application_jobs_user_id" not in existing_indexes:
                op.create_index("ix_application_jobs_user_id", "application_jobs", ["user_id"])


def downgrade() -> None:
    # Baseline is additive for existing DBs; do not drop production tables.
    pass
