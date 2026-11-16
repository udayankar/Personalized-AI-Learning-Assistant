"""Helpers for document hashes and the one-time legacy catalog backfill."""

import hashlib
import json

from .user_storage import Get_user_paths


def Calculate_file_hash(file_path):
    hasher = hashlib.sha256()
    with open(file_path, "rb") as file:
        while chunk := file.read(4096):
            hasher.update(chunk)
    return hasher.hexdigest()


def Load_legacy_document_metadata(user_id: int):
    """Read documents.json only for the one-time legacy catalog backfill."""
    _, storage_dir = Get_user_paths(user_id)
    documents_path = storage_dir / "documents.json"
    if not documents_path.exists():
        return {}
    with documents_path.open("r", encoding="utf-8") as file:
        return json.load(file)


# Compatibility aliases for existing local migration tooling. Runtime
# ingestion uses PostgreSQL document hashes and never calls these functions.
Load_document_metadata = Load_legacy_document_metadata


def Save_document_metadata(metadata, user_id: int):
    """Write a legacy manifest only when explicitly used by migration tooling."""
    _, storage_dir = Get_user_paths(user_id)
    storage_dir.mkdir(parents=True, exist_ok=True)
    with (storage_dir / "documents.json").open("w", encoding="utf-8") as file:
        json.dump(metadata, file, indent=4)


def Document_status(file_path, user_id: int):
    """Compare against the legacy manifest; not used by application runtime."""
    metadata = Load_legacy_document_metadata(user_id)
    file_name = getattr(file_path, "name", None)
    if file_name is None:
        from pathlib import Path
        file_name = Path(file_path).name
    current_hash = Calculate_file_hash(file_path)
    if file_name not in metadata:
        return "new", current_hash
    if metadata[file_name] != current_hash:
        return "modified", current_hash
    return "unchanged", current_hash


if __name__ == "__main__":
    raise SystemExit("Legacy document tracking is only used for catalog migration.")
