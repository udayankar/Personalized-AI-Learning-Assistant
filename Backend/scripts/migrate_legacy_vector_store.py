"""Explicitly migrate a trusted legacy pickle-backed user index to JSON.

Run from Backend only for files obtained from a trusted local installation:
    python -m scripts.migrate_legacy_vector_store --user-id 12 --trusted-local-files
The legacy files are preserved after migration for rollback/inspection.
"""
import argparse
import pickle  # Only this opt-in migration utility may deserialize legacy data.

import faiss
from sqlalchemy import select

from App.database import SessionLocal
from App.models import Document
from Rag.user_storage import Get_user_paths
from Rag.vector_store import Load_vector_store, Save_vector_store


def migrate(user_id: int, trusted_local_files: bool) -> None:
    if not trusted_local_files:
        raise SystemExit("Refusing to deserialize pickle without --trusted-local-files")
    _, directory = Get_user_paths(user_id)
    index_path, chunks_path = directory / "index.faiss", directory / "chunks.pkl"
    if not index_path.is_file() or not chunks_path.is_file():
        raise SystemExit("Both legacy index.faiss and chunks.pkl must exist")
    try:
        index = faiss.read_index(str(index_path))
        with chunks_path.open("rb") as source:
            chunks = pickle.load(source)
    except Exception as error:
        raise SystemExit(f"Could not read trusted legacy store: {type(error).__name__}") from error
    if not isinstance(chunks, list) or index.ntotal != len(chunks):
        raise SystemExit("Legacy vector and chunk counts do not match")
    with SessionLocal() as session:
        catalog = {
            row.storage_filename: row.sha256
            for row in session.scalars(select(Document).where(Document.user_id == user_id)).all()
        }
    for chunk in chunks:
        if not isinstance(chunk, dict) or not isinstance(chunk.get("text"), str):
            raise SystemExit("Legacy chunk metadata is invalid")
        if chunk.get("user_id", user_id) != user_id:
            raise SystemExit("Legacy chunks contain another user's data")
        document_id = chunk.get("document_id", chunk.get("source"))
        if document_id not in catalog:
            raise SystemExit(f"Chunk document {document_id!r} is absent from this user's catalog")
        chunk.update(user_id=user_id, document_id=document_id, document_sha256=catalog[document_id])
    try:
        Load_vector_store(user_id)
    except ValueError:
        pass
    else:
        raise SystemExit("A v2 store already exists; refusing to overwrite it")
    Save_vector_store(index, chunks, user_id)
    print(f"Migrated user {user_id}; original pickle files were preserved")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-id", type=int, required=True)
    parser.add_argument("--trusted-local-files", action="store_true")
    args = parser.parse_args()
    migrate(args.user_id, args.trusted_local_files)


if __name__ == "__main__":
    main()
