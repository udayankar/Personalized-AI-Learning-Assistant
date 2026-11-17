"""Synchronous PDF extraction and atomic PostgreSQL chunk persistence."""
from .loader import Load_PDF
from .chunker import Chunk_Txt
from .embedder import Create_embeddings
from .vector_store import Insert_document_chunks


def Process_document(file_path):
    pages = Load_PDF(str(file_path))
    chunks = Chunk_Txt(pages)
    if not chunks:
        raise ValueError(f"No extractable text found in {file_path.name}")
    return chunks, Create_embeddings(chunks)


def Store_document(session, document, file_path):
    """Persist every chunk and READY status in the caller's single transaction."""
    chunks, embeddings = Process_document(file_path)
    Insert_document_chunks(session, document, chunks, embeddings)
    document.status = "READY"
    session.flush()
    return len(chunks)
