from sqlalchemy import (
    BigInteger, String, func, TIMESTAMP, ForeignKey, ForeignKeyConstraint, JSON, Index, UniqueConstraint, CheckConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
import uuid
from .base import Base
from pgvector.sqlalchemy import VECTOR

class User(Base):
    __tablename__ = "users"
    ID : Mapped[int] = mapped_column(primary_key=True, index=True)
    Name : Mapped[str] = mapped_column(String(100), nullable=False)
    Email : Mapped[str] = mapped_column(String(255) , unique=True , index=True , nullable=False)
    Password : Mapped[str] = mapped_column(String(255) , nullable=False)
    Created_at : Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True),nullable=False,server_default=func.now())


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("user_id", "storage_filename", name="uq_documents_user_storage_filename"),
        CheckConstraint(
            "status IN ('PROCESSING', 'READY', 'FAILED', 'DELETING')",
            name="ck_documents_status",
        ),
        CheckConstraint("file_size_bytes >= 0", name="ck_documents_file_size_nonnegative"),
        CheckConstraint("page_count IS NULL OR page_count >= 0", name="ck_documents_page_count_nonnegative"),
        Index("ix_documents_user_status", "user_id", "status"),
        UniqueConstraint("id", "user_id", name="uq_documents_id_user_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.ID", ondelete="CASCADE"), nullable=False
    )
    filename: Mapped[str] = mapped_column(String(120), nullable=False)
    storage_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    page_count: Mapped[int | None] = mapped_column(nullable=True)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    chunks: Mapped[list["DocumentChunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", passive_deletes=True
    )


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_document_chunks_position"),
        ForeignKeyConstraint(
            ["document_id", "user_id"], ["documents.id", "documents.user_id"],
            ondelete="CASCADE", name="fk_document_chunks_owned_document",
        ),
        CheckConstraint("chunk_index >= 0", name="ck_document_chunks_index_nonnegative"),
        CheckConstraint("embedding_dimensions = 768", name="ck_document_chunks_dimensions"),
        Index("ix_document_chunks_user_document", "user_id", "document_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(nullable=False)
    document_id: Mapped[str] = mapped_column(String(36), nullable=False)
    chunk_index: Mapped[int] = mapped_column(nullable=False)
    text: Mapped[str] = mapped_column(String, nullable=False)
    page_number: Mapped[int | None] = mapped_column(nullable=True)
    embedding: Mapped[list[float]] = mapped_column(VECTOR(768), nullable=False)
    embedding_provider: Mapped[str] = mapped_column(String(32), nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(128), nullable=False)
    embedding_dimensions: Mapped[int] = mapped_column(nullable=False)
    embedding_task_type: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    document: Mapped[Document] = relationship(back_populates="chunks")


class AnswerCache(Base):
    __tablename__ = "answer_cache"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "normalized_query_hash", "context_fingerprint", "pipeline_version",
            name="uq_answer_cache_exact_context",
        ),
        CheckConstraint(
            "answer_mode IN ('DOCUMENT_SUPPORTED', 'INSUFFICIENT_CONFIDENCE')",
            name="ck_answer_cache_answer_mode",
        ),
        CheckConstraint("gemini_calls >= 0", name="ck_answer_cache_gemini_calls"),
        Index("ix_answer_cache_expires_at", "expires_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.ID", ondelete="CASCADE"), nullable=False, index=True
    )
    normalized_query_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    answer: Mapped[str] = mapped_column(String, nullable=False)
    answer_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    message: Mapped[str | None] = mapped_column(String, nullable=True)
    reliability: Mapped[str] = mapped_column(String(16), nullable=False)
    conflict_status: Mapped[str] = mapped_column(String(16), nullable=False)
    fallback_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    claims: Mapped[list] = mapped_column(JSON, nullable=False)
    sources: Mapped[list] = mapped_column(JSON, nullable=False)
    context_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    pipeline_version: Mapped[str] = mapped_column(String(128), nullable=False)
    gemini_calls: Mapped[int] = mapped_column(nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
