"""Add pgvector-backed document chunks.

Revision ID: e29c04a1bb32
Revises: d54b8d9e5a1c
"""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import VECTOR

revision = "e29c04a1bb32"
down_revision = "d54b8d9e5a1c"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    postgres = bind.dialect.name == "postgresql"
    if postgres:
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    with op.batch_alter_table("documents") as batch:
        batch.create_unique_constraint("uq_documents_id_user_id", ["id", "user_id"])
    op.create_table(
        "document_chunks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("embedding", VECTOR(768) if postgres else sa.JSON(), nullable=False),
        sa.Column("embedding_provider", sa.String(length=32), nullable=False),
        sa.Column("embedding_model", sa.String(length=128), nullable=False),
        sa.Column("embedding_dimensions", sa.Integer(), nullable=False),
        sa.Column("embedding_task_type", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id", "user_id"], ["documents.id", "documents.user_id"],
            name="fk_document_chunks_owned_document", ondelete="CASCADE",
        ),
        sa.UniqueConstraint("document_id", "chunk_index", name="uq_document_chunks_position"),
        sa.CheckConstraint("chunk_index >= 0", name="ck_document_chunks_index_nonnegative"),
        sa.CheckConstraint("embedding_dimensions = 768", name="ck_document_chunks_dimensions"),
    )
    op.create_index("ix_document_chunks_user_document", "document_chunks", ["user_id", "document_id"])


def downgrade():
    op.drop_index("ix_document_chunks_user_document", table_name="document_chunks")
    op.drop_table("document_chunks")
    with op.batch_alter_table("documents") as batch:
        batch.drop_constraint("uq_documents_id_user_id", type_="unique")
    # Keep the shared extension installed; other application tables may use it.
