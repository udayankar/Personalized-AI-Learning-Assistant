from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
DOCUMENTS_ROOT = BACKEND_DIR / "Data" / "Documents" / "Users"
STORAGE_ROOT = BACKEND_DIR / "Storage" / "Users"


def Get_user_paths(user_id: int) -> tuple[Path, Path]:
    """Return the document and vector-store directories for a database user ID."""
    if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0:
        raise ValueError("A positive database user ID is required")

    # The numeric identity check prevents path separators/traversal before a
    # directory name is composed. Avoid resolving paths here: concurrent first
    # writes can race while Windows is creating the shared parent directories.
    directory_name = f"user_{user_id}"
    return DOCUMENTS_ROOT / directory_name, STORAGE_ROOT / directory_name
