import hashlib
import json
from pathlib import Path

from .user_storage import Get_user_paths

def Calculate_file_hash(file_path):
    hasher = hashlib.sha256()
    with open(file_path, "rb") as file:
        while chunk := file.read(4096):
            hasher.update(chunk)

    return hasher.hexdigest()

def Load_document_metadata(user_id: int):
    _, storage_dir = Get_user_paths(user_id)
    documents_path = storage_dir / "documents.json"
    if not documents_path.exists():
        return {}
    with documents_path.open("r", encoding="utf-8") as file:
        return json.load(file)


def Save_document_metadata(metadata, user_id: int):
    _, storage_dir = Get_user_paths(user_id)
    storage_dir.mkdir(parents=True, exist_ok=True)
    documents_path = storage_dir / "documents.json"
    with documents_path.open("w", encoding="utf-8") as file:
        json.dump(metadata, file, indent=4)

def Document_status(file_path, user_id: int):
    metadata = Load_document_metadata(user_id)
    file_name = Path(file_path).name
    current_hash = Calculate_file_hash(file_path)
    if file_name not in metadata:
        return "new", current_hash
    if metadata[file_name] != current_hash:
        return "modified", current_hash

    return "unchanged", current_hash

if __name__ == "__main__":
    raise SystemExit("Document tracking requires an authenticated database user ID.")
