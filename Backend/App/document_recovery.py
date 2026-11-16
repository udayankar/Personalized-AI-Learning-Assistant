"""Small single-instance recovery for interrupted synchronous document work."""

import logging
from datetime import datetime, timezone

from sqlalchemy import select

from .database import SessionLocal
from .models import Document, User
from Rag.user_storage import DOCUMENTS_ROOT, Get_user_paths
from Rag.vector_store import (
    Cleanup_vector_store_temporary_files,
    _atomic_json,
    _load_version,
    _manifest,
)


logger = logging.getLogger(__name__)


def recover_interrupted_document_work() -> None:
    """Mark crashed ingestions retryable and remove abandoned temporary files."""
    with SessionLocal() as session:
        user_ids = set(session.scalars(select(User.ID)).all())
        interrupted = session.scalars(
            select(Document).where(Document.status == "PROCESSING")
        ).all()
        recovered_at = datetime.now(timezone.utc)
        for document in interrupted:
            document.status = "FAILED"
            document.updated_at = recovered_at
        session.commit()

    try:
        documents_root = DOCUMENTS_ROOT.resolve()
    except OSError:
        logger.warning("document_recovery storage_root_unavailable=root")
        return

    for user_id in user_ids:
        documents_dir, _ = Get_user_paths(user_id)
        try:
            Cleanup_vector_store_temporary_files(user_id)
            _, storage_dir = Get_user_paths(user_id)
            manifest_path = storage_dir / "manifest.json"
            previous = storage_dir / "manifest.previous.json"
            if manifest_path.exists() or previous.exists():
                import json
                try:
                    active = _manifest(storage_dir)
                    if active is None and previous.exists():
                        raise ValueError("active manifest is missing")
                    if active is not None and active["active_version"] is not None:
                        _load_version(storage_dir, active["active_version"], user_id)
                except (OSError, ValueError, TypeError, KeyError):
                    try:
                        backup = json.loads(previous.read_text(encoding="utf-8"))
                        if not isinstance(backup, dict):
                            raise ValueError("invalid backup manifest")
                        version = backup.get("active_version")
                        if backup.get("schema_version") != 1:
                            raise ValueError("invalid backup schema")
                        if version is not None:
                            _load_version(storage_dir, version, user_id)
                        _atomic_json(manifest_path, backup)
                    except (OSError, ValueError, TypeError, KeyError):
                        logger.warning("document_recovery index_manifest_unrecoverable user_id=%s", user_id)
            if not documents_dir.exists():
                continue
            resolved_dir = documents_dir.resolve()
            if resolved_dir.parent != documents_root:
                logger.warning("document_recovery skipped_storage_path user_id=%s", user_id)
                continue
            for staged_file in resolved_dir.glob(".upload-*.part"):
                if staged_file.is_file() and staged_file.resolve().parent == resolved_dir:
                    staged_file.unlink(missing_ok=True)
        except OSError as error:
            logger.warning(
                "document_recovery cleanup_failed user_id=%s error_type=%s",
                user_id,
                type(error).__name__,
            )

