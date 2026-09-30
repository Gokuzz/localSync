"""add upload sessions

Revision ID: 0003_upload_sessions
Revises: 0002_stored_files
Create Date: 2026-08-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_upload_sessions"
down_revision: str | None = "0002_stored_files"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "upload_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("device_id", sa.String(length=80), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("expected_size", sa.Integer(), nullable=False),
        sa.Column("expected_sha256", sa.String(length=64), nullable=False),
        sa.Column("content_type", sa.String(length=255), nullable=True),
        sa.Column("temp_relative_path", sa.String(length=255), nullable=False),
        sa.Column("bytes_received", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("completed_file_id", sa.String(length=36), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["completed_file_id"], ["stored_files.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("temp_relative_path"),
    )
    op.create_index(
        "ix_upload_sessions_recovery",
        "upload_sessions",
        ["device_id", "expected_size", "expected_sha256", "status"],
        unique=False,
    )
    op.create_index("ix_upload_sessions_status", "upload_sessions", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_upload_sessions_status", table_name="upload_sessions")
    op.drop_index("ix_upload_sessions_recovery", table_name="upload_sessions")
    op.drop_table("upload_sessions")
