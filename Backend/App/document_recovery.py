"""Recover interrupted synchronous PostgreSQL document lifecycle work."""
import logging
import tempfile
from contextlib import ExitStack
from pathlib import Path

from sqlalchemy import delete, exists, select

from .database import SessionLocal
from .models import AnswerCache, Document, DocumentChunk
from .upload_storage import blocking_file_lock

logger = logging.getLogger(__name__)
TEMP_UPLOAD_ROOT = Path(tempfile.gettempdir()) / "learning-assistant-uploads"
LOCK_ROOT = Path(tempfile.gettempdir()) / "learning-assistant-locks"


def recover_interrupted_document_work() -> None:
    """Recover lifecycle state while holding locks for any active upload.

    Startup invokes this before serving requests. Acquiring existing per-user OS
    locks also makes recovery wait for an upload from another process that began
    before recovery. The deployment still assumes one backend process; concurrent
    independent processes starting recovery are not a supported deployment mode.
    """
    try:
        with SessionLocal() as session:
            processing_users = session.scalars(
                select(Document.user_id).where(Document.status == "PROCESSING").distinct()
            ).all()
        lock_paths = {path for path in LOCK_ROOT.glob("user-*.lock")} if LOCK_ROOT.exists() else set()
        lock_paths.update(LOCK_ROOT / f"user-{user_id}.lock" for user_id in processing_users)
        with ExitStack() as locks:
            for lock_path in sorted(lock_paths):
                locks.enter_context(blocking_file_lock(lock_path))
            with SessionLocal() as session:
                session.execute(
                    Document.__table__.update().where(Document.status == "PROCESSING")
                    .values(status="FAILED")
                )
                session.execute(
                    Document.__table__.update().where(
                        Document.status == "READY",
                        ~exists(select(DocumentChunk.id).where(DocumentChunk.document_id == Document.id)),
                    ).values(status="FAILED")
                )
                deleting_ids = session.execute(select(Document.id, Document.user_id).where(
                    Document.status == "DELETING"
                )).all()
                for document_id, user_id in deleting_ids:
                    session.execute(delete(AnswerCache).where(AnswerCache.user_id == user_id))
                    session.execute(delete(Document).where(
                        Document.id == document_id, Document.user_id == user_id,
                        Document.status == "DELETING",
                    ))
                session.commit()

            # Only clean files after all existing upload locks are held, otherwise
            # recovery could unlink a PDF that an active upload is still reading.
            _clean_temporary_uploads()
    except Exception as error:
        logger.warning("document_recovery database_cleanup_failed error_type=%s", type(error).__name__)
        raise


def _clean_temporary_uploads() -> None:
    try:
        if TEMP_UPLOAD_ROOT.exists():
            for path in TEMP_UPLOAD_ROOT.glob("upload-*.pdf"):
                if path.is_file() and path.resolve().parent == TEMP_UPLOAD_ROOT.resolve():
                    path.unlink(missing_ok=True)
    except OSError as error:
        logger.warning("document_recovery temporary_upload_cleanup_failed error_type=%s", type(error).__name__)
