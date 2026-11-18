"""PostgreSQL/pgvector retrieval for authenticated document chunks."""
import math

from sqlalchemy import select

from App.database import SessionLocal
from App.models import Document, DocumentChunk
from .relevance import Get_calibrated_relevance_threshold, Make_retrieval_result  # calibration is offline only
from .embedder import get_embedding_configuration


class IncompatibleVectorStoreError(ValueError):
    """Stored vectors do not use the active embedding configuration."""


def validate_chunk_embedding(embedding, dimensions: int = 768) -> list[float]:
    values = [float(value) for value in embedding]
    if len(values) != dimensions or not all(math.isfinite(value) for value in values):
        raise ValueError("Embedding must contain the configured number of finite dimensions")
    norm = math.sqrt(sum(value * value for value in values))
    if not math.isclose(norm, 1.0, rel_tol=1e-4, abs_tol=1e-4):
        raise ValueError("Embedding must be L2-normalized")
    return values


def Insert_document_chunks(session, document: Document, chunks: list[dict], embeddings) -> None:
    config = get_embedding_configuration()
    if len(chunks) != len(embeddings):
        raise ValueError("Each document chunk must have one embedding")
    rows = []
    for index, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
        vector = validate_chunk_embedding(embedding, config.dimensions)
        rows.append(DocumentChunk(
            user_id=document.user_id,
            document_id=document.id,
            chunk_index=index,
            text=chunk["text"],
            page_number=chunk.get("page"),
            embedding=vector,
            embedding_provider=config.provider,
            embedding_model=config.model,
            embedding_dimensions=config.dimensions,
            embedding_task_type=config.document_task_type,
        ))
    session.add_all(rows)


def Retrieve(query, embedder, user_id: int, k=5, allowed_document_ids=None):
    if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0:
        raise ValueError("A valid authenticated user ID is required")
    # No distance cutoff: always pass nearest retrieved passages to grounding.
    threshold = 2.0
    if k <= 0:
        return Make_retrieval_result(query, user_id, [], threshold)
    if allowed_document_ids is not None and not allowed_document_ids:
        return Make_retrieval_result(query, user_id, [], threshold)
    config = get_embedding_configuration()
    with SessionLocal() as session:
        base = select(DocumentChunk.id).join(
            Document, Document.id == DocumentChunk.document_id
        ).where(DocumentChunk.user_id == user_id, Document.user_id == user_id,
                Document.status == "READY")
        mismatch = session.scalar(base.where(
                   (DocumentChunk.embedding_provider != config.provider)
                   | (DocumentChunk.embedding_model != config.model)
                   | (DocumentChunk.embedding_dimensions != config.dimensions)
                   | (DocumentChunk.embedding_task_type != config.document_task_type))
            .limit(1))
        if mismatch is not None:
            raise IncompatibleVectorStoreError("Stored document embeddings do not match the active configuration")
        has_compatible_rows = session.scalar(base.where(
            DocumentChunk.embedding_provider == config.provider,
            DocumentChunk.embedding_model == config.model,
            DocumentChunk.embedding_dimensions == config.dimensions,
            DocumentChunk.embedding_task_type == config.document_task_type,
        ).limit(1))
        if has_compatible_rows is None:
            return Make_retrieval_result(query, user_id, [], threshold)
    query_vector = validate_chunk_embedding(embedder.embed_query(query), config.dimensions)
    with SessionLocal() as session:
        distance = DocumentChunk.embedding.l2_distance(query_vector).label("distance")
        statement = (
            select(DocumentChunk, Document.filename, distance)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(
                DocumentChunk.user_id == user_id,
                Document.user_id == user_id,
                Document.status == "READY",
                DocumentChunk.embedding_provider == config.provider,
                DocumentChunk.embedding_model == config.model,
                DocumentChunk.embedding_dimensions == config.dimensions,
                DocumentChunk.embedding_task_type == config.document_task_type,
            )
            .order_by(distance, DocumentChunk.id)
            .limit(min(k, 5))
        )
        if allowed_document_ids is not None:
            statement = statement.where(Document.id.in_(allowed_document_ids))
        rows = session.execute(statement).all()
    chunks = []
    for row, filename, value in rows:
        value = float(value)
        if not math.isfinite(value):
            continue
        chunks.append({
            "source": filename,
            "document_id": row.document_id,
            "user_id": row.user_id,
            "page": row.page_number,
            "text": row.text,
            "distance": value,
        })
    return Make_retrieval_result(query, user_id, chunks, 1.00)


def Load_ready_chunk_metadata(user_id: int) -> list[dict]:
    """Load only the authenticated user's READY chunk text for cache provenance."""
    with SessionLocal() as session:
        rows = session.execute(
            select(DocumentChunk, Document.filename)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(DocumentChunk.user_id == user_id, Document.user_id == user_id,
                   Document.status == "READY")
            .order_by(DocumentChunk.document_id, DocumentChunk.chunk_index)
        ).all()
    return [{"source": filename, "document_id": row.document_id,
             "user_id": row.user_id, "page": row.page_number, "text": row.text}
            for row, filename in rows]
