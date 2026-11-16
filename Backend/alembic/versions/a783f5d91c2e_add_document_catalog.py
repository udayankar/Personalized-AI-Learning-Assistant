"""add per-user document catalog

Revision ID: a783f5d91c2e
Revises: c2b9d8417e6a
Create Date: 2026-11-16
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a783f5d91c2e"
down_revision: Union[str, None] = "c2b9d8417e6a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(length=120), nullable=False),
        sa.Column("storage_filename", sa.String(length=255), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column(
            "uploaded_at", sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('PROCESSING', 'READY', 'FAILED', 'DELETING')",
            name="ck_documents_status",
        ),
        sa.CheckConstraint("file_size_bytes >= 0", name="ck_documents_file_size_nonnegative"),
        sa.CheckConstraint(
            "page_count IS NULL OR page_count >= 0",
            name="ck_documents_page_count_nonnegative",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.ID"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "storage_filename", name="uq_documents_user_storage_filename"
        ),
    )
    op.create_index("ix_documents_user_status", "documents", ["user_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_documents_user_status", table_name="documents")
    op.drop_table("documents")
