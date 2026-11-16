import faiss
import numpy as np
import pickle
import math
from .user_storage import Get_user_paths
from .relevance import Get_calibrated_relevance_threshold, Make_retrieval_result

def Create_vector_store(embeddings):
    embeddings = np.array(embeddings).astype("float32")
    if embeddings.size == 0:
        return None
    if embeddings.ndim != 2 or not np.isfinite(embeddings).all():
        raise ValueError("Embeddings must be a finite two-dimensional array")
    dimension = embeddings.shape[1]
    index = faiss.IndexFlatL2(dimension)
    index.add(embeddings)

    return index

def Search(index , query_embedding , k=5):
    if index is None or index.ntotal == 0 or k <= 0:
        return np.array([], dtype="float32"), np.array([], dtype="int64")
    query_embedding = np.array([query_embedding]).astype("float32")
    distances , indices = index.search(query_embedding , min(k, index.ntotal))

    return distances[0] , indices[0]

def Retrieve(query, index, chunks, model, user_id: int, k=5, allowed_document_ids=None):
    threshold = Get_calibrated_relevance_threshold()
    if index is None or not chunks or index.ntotal == 0 or k <= 0:
        return Make_retrieval_result(query, user_id, [], threshold)
    query_embedding = model.encode(query)
    search_k = k
    if allowed_document_ids is not None:
        excluded_count = sum(
            1 for chunk in chunks
            if not isinstance(chunk, dict)
            or chunk.get("document_id", chunk.get("source")) not in allowed_document_ids
        )
        search_k = min(index.ntotal, k + excluded_count)
    distances, indices = Search(index, query_embedding, search_k)
    results = []

    for distance, index_number in zip(distances, indices):
        if index_number < 0 or index_number >= len(chunks):
            continue
        if not math.isfinite(float(distance)):
            continue
        chunk = chunks[index_number]
        if not isinstance(chunk, dict) or "text" not in chunk:
            continue
        if (
            allowed_document_ids is not None
            and chunk.get("document_id", chunk.get("source")) not in allowed_document_ids
        ):
            continue
        results.append({**chunk, "distance": float(distance)})

    results.sort(key=lambda chunk: (
        chunk["distance"],
        str(chunk.get("document_id", chunk.get("source", ""))),
    ))

    return Make_retrieval_result(query, user_id, results[:k], threshold)

def Save_vector_store(index, chunks, user_id: int):
    _, storage_dir = Get_user_paths(user_id)
    storage_dir.mkdir(parents=True, exist_ok=True)
    index_path = storage_dir / "index.faiss"
    chunks_path = storage_dir / "chunks.pkl"
    faiss.write_index(index, str(index_path))
    with chunks_path.open("wb") as file:
        pickle.dump(chunks, file)

def Load_vector_store(user_id: int):
    _, storage_dir = Get_user_paths(user_id)
    index_path = storage_dir / "index.faiss"
    chunks_path = storage_dir / "chunks.pkl"
    if not index_path.exists() and not chunks_path.exists():
        return None, []
    if not index_path.exists() or not chunks_path.exists():
        raise FileNotFoundError("The user's vector store is incomplete")

    try:
        index = faiss.read_index(str(index_path))
        with chunks_path.open("rb") as file:
            chunks = pickle.load(file)
    except (OSError, RuntimeError, pickle.UnpicklingError, EOFError, ValueError, TypeError) as error:
        raise ValueError("The user's vector store is corrupted") from error
    if not isinstance(chunks, list) or any(not isinstance(chunk, dict) for chunk in chunks):
        raise ValueError("The user's chunk data is invalid")
    if index.ntotal != len(chunks):
        raise ValueError("The user's vector index and chunk data do not match")
    for chunk in chunks:
        chunk_user_id = chunk.get("user_id", user_id)
        if chunk_user_id != user_id:
            raise ValueError("The user's chunk data contains a different user ID")
        if not isinstance(chunk.get("text"), str):
            raise ValueError("The user's chunk metadata is invalid")
        if chunk.get("page") is not None and (
            isinstance(chunk.get("page"), bool) or not isinstance(chunk.get("page"), int)
        ):
            chunk["page"] = None
        chunk["user_id"] = user_id
        chunk.setdefault("source", "Unknown")
        chunk.setdefault("document_id", chunk["source"])

    return index, chunks


def Remove_vector_store(user_id: int):
    _, storage_dir = Get_user_paths(user_id)
    for filename in ("index.faiss", "chunks.pkl"):
        path = storage_dir / filename
        if path.exists():
            path.unlink()

def Add_to_vector_store(index, chunks, new_chunks, new_embeddings):
    new_embeddings = np.array(new_embeddings).astype("float32")
    index.add(new_embeddings)
    chunks.extend(new_chunks)

    return index, chunks

if __name__ == "__main__":
    raise SystemExit("Vector-store operations require an authenticated database user ID.")
