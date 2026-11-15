"""add exact answer cache

Revision ID: c2b9d8417e6a
Revises: fa11c95537c7
Create Date: 2026-11-15
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c2b9d8417e6a"
down_revision: Union[str, None] = "fa11c95537c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "answer_cache",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("normalized_query_hash", sa.String(length=64), nullable=False),
        sa.Column("answer", sa.String(), nullable=False),
        sa.Column("answer_mode", sa.String(length=32), nullable=False),
        sa.Column("message", sa.String(), nullable=True),
        sa.Column("reliability", sa.String(length=16), nullable=False),
        sa.Column("conflict_status", sa.String(length=16), nullable=False),
        sa.Column("fallback_reason", sa.String(length=64), nullable=True),
        sa.Column("claims", sa.JSON(), nullable=False),
        sa.Column("sources", sa.JSON(), nullable=False),
        sa.Column("context_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("pipeline_version", sa.String(length=128), nullable=False),
        sa.Column("gemini_calls", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.CheckConstraint(
            "answer_mode IN ('DOCUMENT_SUPPORTED', 'GENERAL_KNOWLEDGE')",
            name="ck_answer_cache_answer_mode",
        ),
        sa.CheckConstraint("gemini_calls >= 0", name="ck_answer_cache_gemini_calls"),
        sa.ForeignKeyConstraint(["user_id"], ["users.ID"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "normalized_query_hash", "context_fingerprint", "pipeline_version",
            name="uq_answer_cache_exact_context",
        ),
    )
    op.create_index("ix_answer_cache_user_id", "answer_cache", ["user_id"])
    op.create_index("ix_answer_cache_expires_at", "answer_cache", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_answer_cache_expires_at", table_name="answer_cache")
    op.drop_index("ix_answer_cache_user_id", table_name="answer_cache")
    op.drop_table("answer_cache")
