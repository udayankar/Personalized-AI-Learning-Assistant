import faiss
import numpy as np
import pickle
import json
from pathlib import Path

STORAGE_DIR = Path("Storage")

INDEX_PATH = STORAGE_DIR / "faiss.index"
CHUNKS_PATH = STORAGE_DIR / "chunks.pkl"
DOCUMENTS_PATH = STORAGE_DIR / "documents.json"

def Create_vector_store(embeddings):
    embeddings = np.array(embeddings).astype("float32")
    dimension = embeddings.shape[1]
    index = faiss.IndexFlatL2(dimension)
    index.add(embeddings)

    return index

def Search(index , query_embedding , k=5):
    query_embedding = np.array([query_embedding]).astype("float32")
    distances , indices = index.search(query_embedding , k)

    return distances[0] , indices[0]

def Retrieve(query, index, chunks, model, k=5):
    query_embedding = model.encode(query)
    distances, indices = Search(index, query_embedding, k)
    results = []

    for distance, index_number in zip(distances, indices):
        results.append({
            "page": chunks[index_number]["page"],
            "text": chunks[index_number]["text"],
            "source": chunks[index_number].get("source", "Unknown"),
            "distance": float(distance)
        })

    return results

def Save_vector_store(index, chunks):
    STORAGE_DIR.mkdir(exist_ok=True)
    faiss.write_index(index, str(INDEX_PATH))
    with open(CHUNKS_PATH, "wb") as file:
        pickle.dump(chunks, file)

def Load_vector_store():
    index = faiss.read_index(str(INDEX_PATH))
    with open(CHUNKS_PATH, "rb") as file:
        chunks = pickle.load(file)

    return index, chunks

def Add_to_vector_store(index, chunks, new_chunks, new_embeddings):
    new_embeddings = np.array(new_embeddings).astype("float32")
    index.add(new_embeddings)
    chunks.extend(new_chunks)

    return index, chunks

if __name__ == "__main__":

    from loader import Load_PDF
    from chunker import Chunk_Txt
    from embedder import Create_embeddings, model

    pages = Load_PDF("Data/Documents/opencv-notes.pdf")

    chunks = Chunk_Txt(pages)

    embeddings = Create_embeddings(chunks)

    index = Create_vector_store(embeddings)

    Save_vector_store(index, chunks)

    print("Vector store saved.")

    loaded_index, loaded_chunks = Load_vector_store()

    print("Vector store loaded.")
    print("Vectors:", loaded_index.ntotal)
    print("Chunks:", len(loaded_chunks))