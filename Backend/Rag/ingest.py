from loader import Load_PDF
from pathlib import Path
from chunker import Chunk_Txt
from embedder import Create_embeddings
from vector_store import (Create_vector_store , Save_vector_store ,Load_vector_store , Add_to_vector_store)
from document_tracker import (Document_status , Load_document_metadata , Save_document_metadata)

DOCUMENTS_DIR = Path("Data/Documents")

def Process_document(file_path) :
    print(f"Processing: {file_path.name}")
    pages = Load_PDF(str(file_path))
    chunks = Chunk_Txt(pages)
    for chunk in chunks:
        chunk["source"] = file_path.name
    embeddings = Create_embeddings(chunks)

    return chunks, embeddings

def Rebuild_vector_store(pdf_files) :
    print("\nRebuilding vector store...")
    all_chunks = []
    all_embeddings = []
    for pdf_file in pdf_files:
        chunks, embeddings = Process_document(pdf_file)
        all_chunks.extend(chunks)
        all_embeddings.extend(embeddings)
    index = Create_vector_store(all_embeddings)
    Save_vector_store(index , all_chunks)

    return index, all_chunks

def Build_rag() :
    pdf_files = list(DOCUMENTS_DIR.glob("*.pdf"))
    if not pdf_files :
        print("No PDF documents found.")
        return None , []
    metadata = Load_document_metadata()
    current_files = {pdf_file.name for pdf_file in pdf_files}
    deleted = any(file_name not in current_files for file_name in metadata)
    statuses = {}
    for pdf_file in pdf_files :
        status, file_hash = Document_status(str(pdf_file))
        statuses[pdf_file] = (status,file_hash)
        print(f"{pdf_file.name} → {status}")
    modified = any(status == "modified" for status , _ in statuses.values())
    if modified or deleted:
        if modified:
            print("\nModified document detected.")
        if deleted:
            print("\nDeleted document detected.")
        index , chunks = Rebuild_vector_store(pdf_files)
        metadata = {}
        for pdf_file in pdf_files:
            _ , file_hash = Document_status(str(pdf_file))
            metadata[pdf_file.name] = file_hash
        Save_document_metadata(metadata)

        return index, chunks
    if (Path("Storage/faiss.index").exists() and Path("Storage/chunks.pkl").exists()) :
        print("\nExisting vector store found.")
        index, chunks = Load_vector_store()
    else :
        print("\nNo existing vector store found.")
        index = None
        chunks = []
    for pdf_file , (status , file_hash) in statuses.items() :
        if status != "new" :
            continue
        new_chunks, new_embeddings = Process_document(pdf_file)
        if index is None :
            index = Create_vector_store(new_embeddings)
            chunks = new_chunks
        else :
            print("Adding document to existing index...")
            index, chunks = Add_to_vector_store(index , chunks , new_chunks , new_embeddings)
        metadata[pdf_file.name] = file_hash
    Save_document_metadata(metadata)
    if index is not None :
        Save_vector_store(index , chunks)

    return index, chunks

if __name__ == "__main__":

    index, chunks = Build_rag()

    if index is not None:

        print("\n-------------------------")

        print(
            "Total vectors:",
            index.ntotal
        )

        print(
            "Total chunks:",
            len(chunks)
        )

        print("-------------------------")
