from .loader import Load_PDF
from .chunker import Chunk_Txt
from .embedder import Create_embeddings
from .vector_store import (
    Add_to_vector_store,
    Create_vector_store,
    Load_vector_store,
    Remove_vector_store,
    Save_vector_store,
)
from .document_tracker import (Document_status , Load_document_metadata , Save_document_metadata)
from .user_storage import Get_user_paths

def Process_document(file_path, user_id: int) :
    print(f"Processing: {file_path.name}")
    pages = Load_PDF(str(file_path))
    chunks = Chunk_Txt(pages)
    if not chunks:
        raise ValueError(f"No extractable text found in {file_path.name}")
    for chunk in chunks:
        chunk["source"] = file_path.name
        chunk["document_id"] = file_path.name
        chunk["user_id"] = user_id
    embeddings = Create_embeddings(chunks)

    return chunks, embeddings

def Rebuild_vector_store(pdf_files, user_id: int) :
    print("\nRebuilding vector store...")
    all_chunks = []
    all_embeddings = []
    for pdf_file in pdf_files:
        chunks, embeddings = Process_document(pdf_file, user_id)
        all_chunks.extend(chunks)
        all_embeddings.extend(embeddings)
    index = Create_vector_store(all_embeddings)
    Save_vector_store(index, all_chunks, user_id)

    return index, all_chunks

def Build_rag(user_id: int, eligible_storage_filenames=None) :
    documents_dir, storage_dir = Get_user_paths(user_id)
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
    metadata = Load_document_metadata(user_id)
    if not pdf_files :
        if metadata or (storage_dir / "index.faiss").exists() or (storage_dir / "chunks.pkl").exists():
            Remove_vector_store(user_id)
            Save_document_metadata({}, user_id)
        return None , []

    current_files = {pdf_file.name for pdf_file in pdf_files}
    deleted = any(file_name not in current_files for file_name in metadata)
    statuses = {}
    for pdf_file in pdf_files :
        status, file_hash = Document_status(str(pdf_file), user_id)
        statuses[pdf_file] = (status,file_hash)
        print(f"{pdf_file.name}: {status}")
    modified = any(status == "modified" for status , _ in statuses.values())
    if modified or deleted:
        if modified:
            print("\nModified document detected.")
        if deleted:
            print("\nDeleted document detected.")
        index , chunks = Rebuild_vector_store(pdf_files, user_id)
        metadata = {}
        for pdf_file in pdf_files:
            _ , file_hash = Document_status(str(pdf_file), user_id)
            metadata[pdf_file.name] = file_hash
        Save_document_metadata(metadata, user_id)

        return index, chunks

    try:
        index, chunks = Load_vector_store(user_id)
    except (FileNotFoundError, ValueError):
        # A prior interrupted two-file save is treated as unavailable and rebuilt
        # from the PDFs that are still present for this user.
        index, chunks = Rebuild_vector_store(pdf_files, user_id)
        metadata = {}
        for pdf_file in pdf_files:
            _, file_hash = Document_status(str(pdf_file), user_id)
            metadata[pdf_file.name] = file_hash
        Save_document_metadata(metadata, user_id)
        return index, chunks
    if index is None :
        print("\nNo existing vector store found.")
        statuses = {pdf_file: ("new", statuses[pdf_file][1]) for pdf_file in pdf_files}
    else:
        print("\nExisting vector store found.")

    for pdf_file , (status , file_hash) in statuses.items() :
        if status != "new" :
            continue
        new_chunks, new_embeddings = Process_document(pdf_file, user_id)
        if index is None :
            index = Create_vector_store(new_embeddings)
            chunks = new_chunks
        else :
            print("Adding document to existing index...")
            index, chunks = Add_to_vector_store(index , chunks , new_chunks , new_embeddings)
        metadata[pdf_file.name] = file_hash
    Save_document_metadata(metadata, user_id)
    if index is not None :
        Save_vector_store(index, chunks, user_id)

    return index, chunks

if __name__ == "__main__":
    raise SystemExit("RAG ingestion requires an authenticated database user ID.")
