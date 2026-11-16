"""Idempotently add existing per-user PDFs to the document catalog.

Run from Backend after applying Alembic migrations:
    python -m scripts.backfill_documents

Use --dry-run to inspect counts without inserting catalog rows.
"""
import argparse
import re
from datetime import UTC, datetime
from pathlib import Path

from pypdf import PdfReader
from sqlalchemy import select

from App.database import SessionLocal
from App.models import Document, User
from Rag.document_tracker import Calculate_file_hash, Load_document_metadata
from App.upload_storage import sanitized_display_filename
from Rag.user_storage import DOCUMENTS_ROOT
from Rag.vector_store import Load_vector_store


def _legacy_page_count(path: Path) -> int | None:
    try:
        reader = PdfReader(str(path))
        if reader.is_encrypted:
            return None
        count = len(reader.pages)
        return count if count > 0 else None
    except Exception:
        return None


def _display_filename(storage_filename: str) -> str:
    stem = Path(storage_filename).stem
    stem = re.sub(r"--[0-9a-f]{32}$", "", stem)
    return sanitized_display_filename(f"{stem}.pdf")


def backfill_documents(session, *, dry_run: bool = False) -> dict[str, int]:
    counts = {"ready": 0, "failed": 0, "existing": 0, "skipped": 0}
    users = {
        user.ID: user
        for user in session.scalars(select(User)).all()
        if isinstance(user.ID, int) and user.ID > 0
    }
    if not DOCUMENTS_ROOT.exists():
        return counts

    root = DOCUMENTS_ROOT.resolve()
    for user_dir in DOCUMENTS_ROOT.iterdir():
        match = re.fullmatch(r"user_([1-9][0-9]*)", user_dir.name)
        if not user_dir.is_dir() or match is None:
            counts["skipped"] += 1
            continue
        user_id = int(match.group(1))
        if user_id not in users:
            counts["skipped"] += 1
            continue
        try:
            resolved_user_dir = user_dir.resolve()
            if resolved_user_dir.parent != root:
                counts["skipped"] += 1
                continue
        except OSError:
            counts["skipped"] += 1
            continue

        try:
            manifest = Load_document_metadata(user_id)
            if not isinstance(manifest, dict):
                manifest = {}
        except (OSError, ValueError, TypeError):
            manifest = {}
        try:
            _index, chunks = Load_vector_store(user_id)
            indexed_names = {
                chunk.get("document_id") for chunk in chunks
                if chunk.get("user_id", user_id) == user_id
            }
        except (OSError, ValueError, RuntimeError):
            indexed_names = set()

        for path in resolved_user_dir.iterdir():
            if not path.is_file() or path.suffix.lower() != ".pdf":
                continue
            try:
                if path.resolve().parent != resolved_user_dir:
                    counts["skipped"] += 1
                    continue
                existing = session.scalar(select(Document.id).where(
                    Document.user_id == user_id,
                    Document.storage_filename == path.name,
                ))
                if existing is not None:
                    counts["existing"] += 1
                    continue
                digest = Calculate_file_hash(path)
                page_count = _legacy_page_count(path)
                indexed = (
                    page_count is not None
                    and manifest.get(path.name) == digest
                    and path.name in indexed_names
                )
                stat = path.stat()
                uploaded_at = datetime.fromtimestamp(stat.st_mtime, UTC)
                row = Document(
                    user_id=user_id,
                    filename=_display_filename(path.name),
                    storage_filename=path.name,
                    file_size_bytes=stat.st_size,
                    page_count=page_count,
                    sha256=digest,
                    status="READY" if indexed else "FAILED",
                    uploaded_at=uploaded_at,
                    updated_at=uploaded_at,
                )
                if not dry_run:
                    session.add(row)
                    session.flush()
                counts["ready" if indexed else "failed"] += 1
            except (OSError, ValueError, TypeError):
                counts["skipped"] += 1
        if not dry_run:
            session.commit()
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="report counts without inserting rows")
    args = parser.parse_args()
    with SessionLocal() as session:
        counts = backfill_documents(session, dry_run=args.dry_run)
    action = "Would import" if args.dry_run else "Imported"
    print(
        f"{action} legacy document records: ready={counts['ready']}, "
        f"needs_attention={counts['failed']}, existing={counts['existing']}, "
        f"skipped={counts['skipped']}"
    )


if __name__ == "__main__":
    main()
