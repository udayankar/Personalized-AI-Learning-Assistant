import unittest
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from App.base import Base
from App.models import Document, DocumentChunk, User
from App import document_recovery
from App.upload_storage import blocking_file_lock


class DocumentRecoveryTests(unittest.TestCase):
    def test_recovery_marks_incomplete_documents_failed_and_finishes_deletions(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            engine = create_engine(f"sqlite:///{root / 'recovery.sqlite'}", poolclass=StaticPool)
            @event.listens_for(engine, "connect")
            def _foreign_keys(connection, _record):
                connection.execute("PRAGMA foreign_keys=ON")
            Base.metadata.create_all(engine)
            session_factory = sessionmaker(bind=engine, expire_on_commit=False)
            with session_factory() as session:
                user = User(ID=7, Name="Student", Email="student@example.test", Password="hash")
                session.add(user)
                session.flush()
                processing = Document(user_id=7, filename="processing.pdf", storage_filename="a",
                                      file_size_bytes=5, page_count=1, sha256="a"*64, status="PROCESSING")
                ready_empty = Document(user_id=7, filename="empty.pdf", storage_filename="b",
                                       file_size_bytes=5, page_count=1, sha256="b"*64, status="READY")
                deleting = Document(user_id=7, filename="deleting.pdf", storage_filename="c",
                                    file_size_bytes=5, page_count=1, sha256="c"*64, status="DELETING")
                session.add_all([processing, ready_empty, deleting])
                session.flush()
                session.add(DocumentChunk(
                    user_id=7, document_id=deleting.id, chunk_index=0, text="remove",
                    embedding=[1.0]+[0.0]*767, embedding_provider="gemini",
                    embedding_model="gemini-embedding-001", embedding_dimensions=768,
                    embedding_task_type="RETRIEVAL_DOCUMENT",
                ))
                session.commit()
                processing_id, empty_id, deleting_id = processing.id, ready_empty.id, deleting.id

            temp_upload_root = root / "temporary-uploads"
            temp_lock_root = root / "locks"
            temp_upload_root.mkdir()
            stale_upload = temp_upload_root / "upload-abandoned.pdf"
            stale_upload.write_bytes(b"temporary")
            keep_file = temp_upload_root / "other-file.txt"
            keep_file.write_text("keep", encoding="utf-8")
            with patch.object(document_recovery, "SessionLocal", session_factory), \
                 patch.object(document_recovery, "TEMP_UPLOAD_ROOT", temp_upload_root), \
                 patch.object(document_recovery, "LOCK_ROOT", temp_lock_root):
                document_recovery.recover_interrupted_document_work()

            with session_factory() as session:
                self.assertEqual(session.get(Document, processing_id).status, "FAILED")
                self.assertEqual(session.get(Document, empty_id).status, "FAILED")
                self.assertIsNone(session.get(Document, deleting_id))
                self.assertEqual(session.query(DocumentChunk).filter_by(document_id=deleting_id).count(), 0)
            self.assertFalse(stale_upload.exists())
            self.assertTrue(keep_file.exists())
            engine.dispose()

    def test_recovery_waits_for_active_upload_lock_before_marking_processing_failed(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            engine = create_engine(f"sqlite:///{root / 'recovery-concurrency.sqlite'}", poolclass=StaticPool)
            @event.listens_for(engine, "connect")
            def _foreign_keys(connection, _record):
                connection.execute("PRAGMA foreign_keys=ON")
            Base.metadata.create_all(engine)
            session_factory = sessionmaker(bind=engine, expire_on_commit=False)
            with session_factory() as session:
                session.add(User(ID=7, Name="Student", Email="student@example.test", Password="hash"))
                session.flush()
                session.add(Document(user_id=7, filename="active.pdf", storage_filename="active",
                                     file_size_bytes=5, page_count=1, sha256="a"*64, status="PROCESSING"))
                session.commit()
            lock_root = root / "locks"
            lock_path = lock_root / "user-7.lock"
            upload_root = root / "uploads"
            upload_root.mkdir()
            staged_pdf = upload_root / "upload-active.pdf"
            staged_pdf.write_bytes(b"still in use")
            with patch.object(document_recovery, "SessionLocal", session_factory), \
                 patch.object(document_recovery, "TEMP_UPLOAD_ROOT", upload_root), \
                 patch.object(document_recovery, "LOCK_ROOT", lock_root):
                with ThreadPoolExecutor(max_workers=1) as pool:
                    with blocking_file_lock(lock_path):
                        recovery = pool.submit(document_recovery.recover_interrupted_document_work)
                        time.sleep(0.15)
                        self.assertFalse(recovery.done())
                        with session_factory() as session:
                            self.assertEqual(session.scalar(select(Document.status)), "PROCESSING")
                        self.assertTrue(staged_pdf.exists())
                    recovery.result(timeout=5)
            with session_factory() as session:
                self.assertEqual(session.scalar(select(Document.status)), "FAILED")
            self.assertFalse(staged_pdf.exists())
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
