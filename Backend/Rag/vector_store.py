"""Per-user FAISS storage with immutable versions and an atomic manifest pointer.

Chunk metadata is JSON. Legacy pickle files are deliberately never loaded here;
use Backend/scripts/migrate_legacy_vector_store.py after reviewing/trusting them.
"""
import hashlib
import json
import math
import os
import uuid
from pathlib import Path

import faiss
import numpy as np

from .user_storage import Get_user_paths
from .relevance import Get_calibrated_relevance_threshold, Make_retrieval_result


MANIFEST = "manifest.json"
PREVIOUS_MANIFEST = "manifest.previous.json"


class LegacyVectorStoreMigrationRequired(FileNotFoundError, ValueError):
    """Raised when an old pickle-backed store requires explicit migration."""


def Create_vector_store(embeddings):
    embeddings = np.array(embeddings).astype("float32")
    if embeddings.size == 0:
        return None
    if embeddings.ndim != 2 or not np.isfinite(embeddings).all():
        raise ValueError("Embeddings must be a finite two-dimensional array")
    index = faiss.IndexFlatL2(embeddings.shape[1])
    index.add(embeddings)
    return index


def Search(index, query_embedding, k=5):
    if index is None or index.ntotal == 0 or k <= 0:
        return np.array([], dtype="float32"), np.array([], dtype="int64")
    distances, indices = index.search(np.array([query_embedding]).astype("float32"), min(k, index.ntotal))
    return distances[0], indices[0]


def Retrieve(query, index, chunks, model, user_id: int, k=5, allowed_document_ids=None):
    threshold = Get_calibrated_relevance_threshold()
    if index is None or not chunks or index.ntotal == 0 or k <= 0:
        return Make_retrieval_result(query, user_id, [], threshold)
    query_embedding = model.encode(query)
    search_k = k
    if allowed_document_ids is not None:
        excluded_count = sum(1 for chunk in chunks if not isinstance(chunk, dict) or chunk.get("document_id", chunk.get("source")) not in allowed_document_ids)
        search_k = min(index.ntotal, k + excluded_count)
    distances, indices = Search(index, query_embedding, search_k)
    results = []
    for distance, index_number in zip(distances, indices):
        if index_number < 0 or index_number >= len(chunks) or not math.isfinite(float(distance)):
            continue
        chunk = chunks[index_number]
        if not isinstance(chunk, dict) or "text" not in chunk:
            continue
        if allowed_document_ids is not None and chunk.get("document_id", chunk.get("source")) not in allowed_document_ids:
            continue
        results.append({**chunk, "distance": float(distance)})
    results.sort(key=lambda chunk: (chunk["distance"], str(chunk.get("document_id", chunk.get("source", "")))))
    return Make_retrieval_result(query, user_id, results[:k], threshold)


def _digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def _atomic_json(path: Path, value) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as file:
            json.dump(value, file, ensure_ascii=False, separators=(",", ":"))
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _manifest(storage_dir: Path, *, reject_legacy: bool = True):
    path = storage_dir / MANIFEST
    if not path.exists():
        if reject_legacy and ((storage_dir / "chunks.pkl").exists() or (storage_dir / "index.faiss").exists()):
            raise LegacyVectorStoreMigrationRequired(
                "Legacy pickle-backed vector store found; run the explicit trusted migration script"
            )
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError
        if data.get("schema_version") != 1 or not (data.get("active_version") is None or re_version(data["active_version"])):
            raise ValueError
        return data
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
        raise ValueError("The vector-store manifest is invalid") from error


def re_version(value) -> bool:
    return isinstance(value, str) and len(value) == 32 and all(ch in "0123456789abcdef" for ch in value)


def _load_version(storage_dir: Path, version: str, user_id: int):
    if not re_version(version):
        raise ValueError("Invalid vector-store version")
    directory = storage_dir / "versions" / version
    try:
        info = json.loads((directory / "version.json").read_text(encoding="utf-8"))
        if not isinstance(info, dict):
            raise ValueError
        if info.get("schema_version") != 1 or info.get("version") != version or info.get("user_id") != user_id:
            raise ValueError
        index_path, chunks_path = directory / "index.faiss", directory / "chunks.json"
        if info.get("index_sha256") != _digest(index_path) or info.get("chunks_sha256") != _digest(chunks_path):
            raise ValueError
        index = faiss.read_index(str(index_path))
        chunks = json.loads(chunks_path.read_text(encoding="utf-8"))
    except (OSError, RuntimeError, ValueError, TypeError, json.JSONDecodeError, KeyError) as error:
        raise ValueError("The active vector-store version is missing or corrupted") from error
    if not isinstance(chunks, list) or index.ntotal != len(chunks) or info.get("count") != len(chunks):
        raise ValueError("The vector index and chunk metadata do not match")
    for chunk in chunks:
        if not isinstance(chunk, dict) or not isinstance(chunk.get("text"), str):
            raise ValueError("The chunk metadata is invalid")
        if chunk.get("user_id", user_id) != user_id:
            raise ValueError("The chunk data contains a different user ID")
        page = chunk.get("page")
        if page is not None and (isinstance(page, bool) or not isinstance(page, int)):
            chunk["page"] = None
        chunk["user_id"] = user_id
        chunk.setdefault("source", "Unknown")
        chunk.setdefault("document_id", chunk["source"])
    return index, chunks


def Save_vector_store(index, chunks, user_id: int):
    _, storage_dir = Get_user_paths(user_id)
    storage_dir.mkdir(parents=True, exist_ok=True)
    if index is None or index.ntotal != len(chunks):
        raise ValueError("Vector index and chunk metadata must contain the same records")
    versions = storage_dir / "versions"
    versions.mkdir(exist_ok=True)
    version = uuid.uuid4().hex
    directory = versions / version
    directory.mkdir()
    index_path, chunks_path = directory / "index.faiss", directory / "chunks.json"
    try:
        faiss.write_index(index, str(index_path))
        with chunks_path.open("x", encoding="utf-8", newline="\n") as file:
            json.dump(chunks, file, ensure_ascii=False, separators=(",", ":"))
            file.flush()
            os.fsync(file.fileno())
        info = {"schema_version": 1, "version": version, "user_id": user_id,
                "count": len(chunks), "index_sha256": _digest(index_path), "chunks_sha256": _digest(chunks_path)}
        _atomic_json(directory / "version.json", info)
        _load_version(storage_dir, version, user_id)  # validate the complete immutable artifact before publishing
        old = _manifest(storage_dir, reject_legacy=False)
        _atomic_json(storage_dir / PREVIOUS_MANIFEST, old if old else {"schema_version": 1, "active_version": None})
        _atomic_json(storage_dir / MANIFEST, {"schema_version": 1, "active_version": version})
    except Exception:
        # Leave incomplete immutable directories for forensic recovery; they are never activated.
        raise


def Load_vector_store(user_id: int):
    _, storage_dir = Get_user_paths(user_id)
    manifest = _manifest(storage_dir)
    if manifest is None or manifest["active_version"] is None:
        return None, []
    return _load_version(storage_dir, manifest["active_version"], user_id)


def Remove_vector_store(user_id: int):
    _, storage_dir = Get_user_paths(user_id)
    storage_dir.mkdir(parents=True, exist_ok=True)
    current = _manifest(storage_dir, reject_legacy=False)
    _atomic_json(storage_dir / PREVIOUS_MANIFEST, current or {"schema_version": 1, "active_version": None})
    _atomic_json(storage_dir / MANIFEST, {"schema_version": 1, "active_version": None})


def Cleanup_vector_store_temporary_files(user_id: int):
    _, storage_dir = Get_user_paths(user_id)
    if not storage_dir.exists():
        return
    # Only unpublished atomic-write temps are removable. Version directories may
    # be observed by concurrent readers and are retained permanently for safety.
    for pattern in (".*.tmp", "index.faiss.*.tmp", "chunks.pkl.*.tmp"):
        for path in storage_dir.glob(pattern):
            if path.is_file():
                path.unlink(missing_ok=True)


def Add_to_vector_store(index, chunks, new_chunks, new_embeddings):
    new_embeddings = np.array(new_embeddings).astype("float32")
    index.add(new_embeddings)
    chunks.extend(new_chunks)
    return index, chunks


if __name__ == "__main__":
    raise SystemExit("Vector-store operations require an authenticated database user ID.")
