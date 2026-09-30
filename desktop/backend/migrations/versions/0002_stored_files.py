"""stored files catalog

Revision ID: 0002_stored_files
Revises: 0001_baseline
Create Date: 2026-08-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_stored_files"
down_revision: str | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "stored_files",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("device_id", sa.String(length=80), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("stored_path", sa.String(length=512), nullable=False),
        sa.Column("content_type", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("device_id", "size", "sha256", name="uq_stored_files_identity"),
        sa.UniqueConstraint("stored_path", name="uq_stored_files_stored_path"),
    )
    op.create_index("ix_stored_files_device_id", "stored_files", ["device_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_stored_files_device_id", table_name="stored_files")
    op.drop_table("stored_files")
