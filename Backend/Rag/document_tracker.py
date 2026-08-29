import hashlib
import json
from pathlib import Path

STORAGE_DIR = Path("Storage")
DOCUMENTS_PATH = STORAGE_DIR / "documents.json"

def Calculate_file_hash(file_path):
    hasher = hashlib.sha256()
    with open(file_path, "rb") as file:
        while chunk := file.read(4096):
            hasher.update(chunk)

    return hasher.hexdigest()

def Load_document_metadata():
    if not DOCUMENTS_PATH.exists():
        return {}
    with open(DOCUMENTS_PATH, "r") as file:
        return json.load(file)


def Save_document_metadata(metadata):
    STORAGE_DIR.mkdir(exist_ok=True)
    with open(DOCUMENTS_PATH, "w") as file:
        json.dump(metadata, file, indent=4)

def Document_status(file_path):
    metadata = Load_document_metadata()
    file_name = Path(file_path).name
    current_hash = Calculate_file_hash(file_path)
    if file_name not in metadata:
        return "new", current_hash
    if metadata[file_name] != current_hash:
        return "modified", current_hash

    return "unchanged", current_hash

if __name__ == "__main__":

    file_path = "Data/Documents/opencv-notes.pdf"

    status, file_hash = Document_status(file_path)

    print("Status:", status)
    print("Hash:", file_hash)

    metadata = Load_document_metadata()

    metadata[Path(file_path).name] = file_hash

    Save_document_metadata(metadata)

    print("\nMetadata saved.")