"""document-only answer cache modes

Revision ID: d54b8d9e5a1c
Revises: a783f5d91c2e
Create Date: 2026-11-16
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d54b8d9e5a1c"
down_revision: Union[str, None] = "a783f5d91c2e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Old general-knowledge entries must never be served by the document-only API.
    op.execute(sa.text("DELETE FROM answer_cache WHERE answer_mode = 'GENERAL_KNOWLEDGE'"))
    with op.batch_alter_table("answer_cache") as batch_op:
        batch_op.drop_constraint("ck_answer_cache_answer_mode", type_="check")
        batch_op.create_check_constraint(
            "ck_answer_cache_answer_mode",
            "answer_mode IN ('DOCUMENT_SUPPORTED', 'INSUFFICIENT_CONFIDENCE')",
        )


def downgrade() -> None:
    # No-information cache rows do not satisfy the prior cache-mode constraint.
    op.execute(sa.text("DELETE FROM answer_cache WHERE answer_mode = 'INSUFFICIENT_CONFIDENCE'"))
    with op.batch_alter_table("answer_cache") as batch_op:
        batch_op.drop_constraint("ck_answer_cache_answer_mode", type_="check")
        batch_op.create_check_constraint(
            "ck_answer_cache_answer_mode",
            "answer_mode IN ('DOCUMENT_SUPPORTED', 'GENERAL_KNOWLEDGE')",
        )
