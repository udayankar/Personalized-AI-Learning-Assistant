import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from App.base import Base
from App.models import Document, User
from App import document_recovery
from Rag import user_storage


class DocumentRecoveryTests(unittest.TestCase):
    def test_startup_marks_interrupted_upload_failed_and_cleans_only_temporary_artifacts(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            documents_root = root / "documents"
            storage_root = root / "indexes"
            engine = create_engine(
                "sqlite://",
                connect_args={"check_same_thread": False},
                poolclass=StaticPool,
            )
            Base.metadata.create_all(engine)
            session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

            with patch.object(user_storage, "DOCUMENTS_ROOT", documents_root), \
                 patch.object(user_storage, "STORAGE_ROOT", storage_root), \
                 patch.object(document_recovery, "DOCUMENTS_ROOT", documents_root), \
                 patch.object(document_recovery, "SessionLocal", session_factory):
                with session_factory() as session:
                    session.add_all([
                        User(ID=7, Name="Student", Email="student@example.test", Password="hash"),
                        User(ID=8, Name="Other", Email="other@example.test", Password="hash"),
                    ])
                    session.flush()
                    interrupted = Document(
                        user_id=7,
                        filename="notes.pdf",
                        storage_filename="notes--abc.pdf",
                        file_size_bytes=5,
                        page_count=1,
                        sha256="a" * 64,
                        status="PROCESSING",
                    )
                    session.add(interrupted)
                    session.commit()
                    interrupted_id = interrupted.id

                user_documents, _ = user_storage.Get_user_paths(7)
                user_documents.mkdir(parents=True)
                uploaded_pdf = user_documents / "notes--abc.pdf"
                uploaded_pdf.write_bytes(b"keep")
                abandoned_upload = user_documents / ".upload-abandoned.part"
                abandoned_upload.write_bytes(b"partial")
                _, user_storage_dir = user_storage.Get_user_paths(8)
                user_storage_dir.mkdir(parents=True)
                abandoned_index = user_storage_dir / "index.faiss.abandoned.tmp"
                abandoned_index.write_bytes(b"partial")

                document_recovery.recover_interrupted_document_work()

                with session_factory() as session:
                    stored = session.scalar(select(Document).where(Document.id == interrupted_id))
                    self.assertEqual(stored.status, "FAILED")
                    self.assertIsNotNone(stored.updated_at)
                self.assertTrue(uploaded_pdf.exists())
                self.assertFalse(abandoned_upload.exists())
                self.assertFalse(abandoned_index.exists())
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
