from .loader import Load_PDF
from .chunker import Chunk_Txt
from .document_tracker import Calculate_file_hash
from .embedder import Create_embeddings
from .vector_store import (
    Add_to_vector_store,
    Create_vector_store,
    Load_vector_store,
    Remove_vector_store,
    Save_vector_store,
)
from .user_storage import Get_user_paths
from contextlib import contextmanager
from App.upload_storage import _try_acquire_file_lock, _release_file_lock


@contextmanager
def _build_lock(user_id: int):
    documents_dir, _ = Get_user_paths(user_id)
    lock_path = documents_dir / ".upload.lock"
    while True:
        try:
            handle = _try_acquire_file_lock(lock_path)
            break
        except BlockingIOError:
            import time
            time.sleep(0.05)
    try:
        yield
    finally:
        _release_file_lock(handle)


def Process_document(file_path, user_id: int):
    pages = Load_PDF(str(file_path))
    chunks = Chunk_Txt(pages)
    if not chunks:
        raise ValueError(f"No extractable text found in {file_path.name}")
    for chunk in chunks:
        chunk["source"] = file_path.name
        chunk["document_id"] = file_path.name
        chunk["user_id"] = user_id
    return chunks, Create_embeddings(chunks)


def Rebuild_vector_store(pdf_files, user_id: int, file_hashes):
    all_chunks = []
    all_embeddings = []
    for pdf_file in pdf_files:
        chunks, embeddings = Process_document(pdf_file, user_id)
        for chunk in chunks:
            chunk["document_sha256"] = file_hashes[pdf_file.name]
        all_chunks.extend(chunks)
        all_embeddings.extend(embeddings)
    index = Create_vector_store(all_embeddings)
    Save_vector_store(index, all_chunks, user_id)
    return index, all_chunks


def Build_rag(
    user_id: int,
    eligible_storage_filenames=None,
    document_hashes: dict[str, str] | None = None,
    *,
    lock_held: bool = False,
):
    """Build the user's index from catalog-eligible PDFs.

    PostgreSQL supplies the authoritative hashes in the API path. The optional
    fallback hash calculation keeps this helper usable by local tools/tests.
    """
    if not lock_held:
        with _build_lock(user_id):
            return Build_rag(user_id, eligible_storage_filenames, document_hashes, lock_held=True)
    documents_dir, _ = Get_user_paths(user_id)
    documents_dir.mkdir(parents=True, exist_ok=True)
    pdf_files = sorted(
        path for path in documents_dir.iterdir()
        if path.is_file()
        and path.suffix.lower() == ".pdf"
        and (
            eligible_storage_filenames is None
            or path.name in eligible_storage_filenames
        )
    )
    if not pdf_files:
        Remove_vector_store(user_id)
        return None, []

    file_hashes = {}
    for pdf_file in pdf_files:
        actual_hash = Calculate_file_hash(pdf_file)
        expected_hash = (document_hashes or {}).get(pdf_file.name)
        if expected_hash is not None and expected_hash.lower() != actual_hash:
            raise ValueError("Stored PDF does not match its document catalog hash")
        file_hashes[pdf_file.name] = expected_hash or actual_hash

    try:
        index, chunks = Load_vector_store(user_id)
    except (FileNotFoundError, ValueError):
        index, chunks = None, []

    indexed_hashes: dict[str, set[str]] = {}
    complete_hash_metadata = True
    for chunk in chunks:
        document_id = chunk.get("document_id", chunk.get("source"))
        digest = chunk.get("document_sha256")
        if not isinstance(document_id, str) or not isinstance(digest, str):
            complete_hash_metadata = False
            continue
        indexed_hashes.setdefault(document_id, set()).add(digest)

    desired_names = set(file_hashes)
    indexed_names = set(indexed_hashes)
    rebuild_required = (
        index is None
        or not complete_hash_metadata
        or not indexed_names.issubset(desired_names)
        or any(
            indexed_hashes.get(name) != {digest}
            for name, digest in file_hashes.items()
            if name in indexed_names
        )
    )
    if rebuild_required:
        return Rebuild_vector_store(pdf_files, user_id, file_hashes)

    new_files = [path for path in pdf_files if path.name not in indexed_names]
    for pdf_file in new_files:
        new_chunks, new_embeddings = Process_document(pdf_file, user_id)
        for chunk in new_chunks:
            chunk["document_sha256"] = file_hashes[pdf_file.name]
        if index is None:
            index = Create_vector_store(new_embeddings)
            chunks = new_chunks
        else:
            index, chunks = Add_to_vector_store(index, chunks, new_chunks, new_embeddings)
    if new_files:
        Save_vector_store(index, chunks, user_id)
    return index, chunks


if __name__ == "__main__":
    raise SystemExit("RAG ingestion requires an authenticated database user ID.")
