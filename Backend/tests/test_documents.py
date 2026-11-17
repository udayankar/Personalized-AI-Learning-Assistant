import asyncio
import os
import tempfile
import unittest
import uuid
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from sqlalchemy import create_engine, event, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.datastructures import Headers, UploadFile

from App.base import Base
from App.database import get_db
from App.models import AnswerCache, Document, DocumentChunk, User
from App.oauth2 import get_current_user
from App.Routers import documents
from Rag import vector_store


def make_pdf(pages=1, include_text=True):
    writer = PdfWriter()
    for _ in range(pages):
        page = writer.add_blank_page(width=72, height=72)
        if include_text:
            font = DictionaryObject({NameObject("/Type"): NameObject("/Font"),
                                     NameObject("/Subtype"): NameObject("/Type1"),
                                     NameObject("/BaseFont"): NameObject("/Helvetica")})
            page[NameObject("/Resources")] = DictionaryObject({
                NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})})
            stream = DecodedStreamObject()
            stream.set_data(b"BT /F1 12 Tf 10 40 Td (Upload test text) Tj ET")
            page[NameObject("/Contents")] = writer._add_object(stream)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


class DocumentDatabaseLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {
            "APP_ENV": "test", "RATE_LIMIT_ENABLED": "false",
        })
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.temp_root = Path(self.temp.name)
        self.tempdir_patch = patch.object(documents.tempfile, "gettempdir", return_value=str(self.temp_root))
        self.tempdir_patch.start()
        self.addCleanup(self.tempdir_patch.stop)
        self.engine = create_engine(
            f"sqlite:///{self.temp_root / 'documents.sqlite'}",
            connect_args={"check_same_thread": False}, poolclass=StaticPool,
        )
        @event.listens_for(self.engine, "connect")
        def _sqlite_foreign_keys(connection, _record):
            connection.execute("PRAGMA foreign_keys=ON")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.addCleanup(self.engine.dispose)
        with self.Session() as session:
            session.add_all([
                User(ID=7, Name="Seven", Email="seven@test.invalid", Password="hash"),
                User(ID=8, Name="Eight", Email="eight@test.invalid", Password="hash"),
            ])
            session.commit()
        self.user = SimpleNamespace(ID=7)
        self.commit_failure_call = None
        self.app = FastAPI()
        self.app.include_router(documents.router)
        self.app.dependency_overrides[get_current_user] = lambda: self.user
        self.app.dependency_overrides[get_db] = self._get_db
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)
        self.addCleanup(self.app.dependency_overrides.clear)
        self.process_patch = patch.object(documents, "Process_document", return_value=(
            [{"text": "Upload test text", "page": 1}], [[1.0] + [0.0] * 767]
        ))
        self.process = self.process_patch.start()
        self.addCleanup(self.process_patch.stop)

    def _get_db(self):
        with self.Session() as session:
            if self.commit_failure_call is None:
                yield session
            else:
                original_commit = session.commit
                calls = [0]
                def commit_with_failure():
                    calls[0] += 1
                    if calls[0] == self.commit_failure_call:
                        # Flush the chunk INSERTs, then fail at the commit boundary.
                        session.flush()
                        raise OperationalError("COMMIT", {}, RuntimeError("simulated commit failure"))
                    original_commit()
                with patch.object(session, "commit", side_effect=commit_with_failure):
                    yield session

    def _post(self, filename="notes.pdf", content=None, content_type="application/pdf"):
        return self.client.post("/documents/upload", files={
            "file": (filename, make_pdf() if content is None else content, content_type)
        })

    def _seed(self, user_id, name="notes.pdf", status="READY", with_chunk=True):
        row = Document(user_id=user_id, filename=name, storage_filename=f"temp-{uuid.uuid4().hex}",
                       file_size_bytes=10, page_count=1, sha256="a" * 64, status=status)
        with self.Session() as session:
            session.add(row)
            session.flush()
            if with_chunk:
                session.add(DocumentChunk(
                    user_id=user_id, document_id=row.id, chunk_index=0, text="private text",
                    page_number=1, embedding=[1.0] + [0.0] * 767,
                    embedding_provider="gemini", embedding_model="gemini-embedding-001",
                    embedding_dimensions=768, embedding_task_type="RETRIEVAL_DOCUMENT",
                ))
            session.commit()
            session.refresh(row)
        return row

    def test_upload_commits_chunks_and_ready_together_and_keeps_pdf_temporary(self):
        response = self._post()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["filename"], "notes.pdf")
        self.assertEqual(self.process.call_count, 1)
        with self.Session() as session:
            document = session.scalar(select(Document).where(Document.user_id == 7))
            self.assertEqual(document.status, "READY")
            self.assertEqual(document.page_count, 1)
            self.assertEqual(session.scalar(select(DocumentChunk.id).where(
                DocumentChunk.document_id == document.id)), 1)
        self.assertEqual(list((self.temp_root / "learning-assistant-uploads").glob("upload-*.pdf")), [])

    def test_embedding_failure_marks_document_failed_and_rolls_back_all_chunks(self):
        self.process.side_effect = RuntimeError("provider internals")
        response = self._post()
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["detail"], "Failed to process the uploaded PDF")
        with self.Session() as session:
            document = session.scalar(select(Document).where(Document.user_id == 7))
            self.assertEqual(document.status, "FAILED")
            self.assertEqual(session.scalar(select(DocumentChunk.id).where(
                DocumentChunk.document_id == document.id)), None)
        self.assertEqual(list((self.temp_root / "learning-assistant-uploads").glob("upload-*.pdf")), [])

    def _three_chunks(self, _path):
        chunks = [{"text": f"part {index}", "page": 1} for index in range(3)]
        vectors = [[1.0] + [0.0] * 767 for _ in chunks]
        return chunks, vectors

    def _assert_failed_ingestion_is_atomic(self, existing):
        response = self._post(filename="new.pdf")
        self.assertEqual(response.status_code, 500)
        with self.Session() as session:
            failed = session.scalar(select(Document).where(Document.filename == "new.pdf"))
            self.assertIsNotNone(failed)
            self.assertIn(failed.status, ("FAILED", "PROCESSING"))
            self.assertNotEqual(failed.status, "READY")
            self.assertEqual(session.scalar(select(DocumentChunk.id).where(
                DocumentChunk.document_id == failed.id)), None)
            self.assertEqual(session.get(Document, existing.id).status, "READY")
            self.assertEqual(session.query(DocumentChunk).filter_by(document_id=existing.id).count(), 1)
        self.assertEqual(list((self.temp_root / "learning-assistant-uploads").glob("upload-*.pdf")), [])

    def test_chunk_insert_failure_after_some_rows_rolls_back_every_chunk(self):
        existing = self._seed(7, "existing.pdf")
        self.process.side_effect = self._three_chunks
        with self.engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TRIGGER fail_second_chunk BEFORE INSERT ON document_chunks "
                "WHEN NEW.chunk_index = 1 BEGIN SELECT RAISE(FAIL, 'simulated insert failure'); END"
            )
        self._assert_failed_ingestion_is_atomic(existing)

    def test_chunk_insert_database_error_does_not_publish_ready_document(self):
        existing = self._seed(7, "existing.pdf")
        self.process.side_effect = self._three_chunks
        def fail_chunk_insert(_connection, _cursor, statement, _parameters, _context, _executemany):
            if statement.lstrip().upper().startswith("INSERT INTO DOCUMENT_CHUNKS"):
                raise OperationalError(statement, {}, RuntimeError("simulated insert failure"))
        event.listen(self.engine, "before_cursor_execute", fail_chunk_insert)
        try:
            self._assert_failed_ingestion_is_atomic(existing)
        finally:
            event.remove(self.engine, "before_cursor_execute", fail_chunk_insert)

    def test_chunk_transaction_commit_failure_rolls_back_flushed_rows(self):
        existing = self._seed(7, "existing.pdf")
        self.process.side_effect = self._three_chunks
        self.commit_failure_call = 2
        self._assert_failed_ingestion_is_atomic(existing)

    def test_connection_loss_during_chunk_insert_leaves_recoverable_document(self):
        existing = self._seed(7, "existing.pdf")
        self.process.side_effect = self._three_chunks
        def disconnect_before_chunk_insert(connection, _cursor, statement, _parameters, _context, _executemany):
            if statement.lstrip().upper().startswith("INSERT INTO DOCUMENT_CHUNKS"):
                connection.invalidate()
                raise OperationalError(statement, {}, OSError("simulated connection loss"))
        event.listen(self.engine, "before_cursor_execute", disconnect_before_chunk_insert)
        try:
            self._assert_failed_ingestion_is_atomic(existing)
        finally:
            event.remove(self.engine, "before_cursor_execute", disconnect_before_chunk_insert)

    def test_listing_and_detail_are_scoped_and_available_reflects_ready_status(self):
        owned = self._seed(7)
        private = self._seed(8, "private.pdf")
        response = self.client.get("/documents")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["id"] for item in response.json()["documents"]], [owned.id])
        self.assertTrue(response.json()["documents"][0]["available"])
        self.assertEqual(self.client.get(f"/documents/{private.id}").status_code, 404)

    def test_empty_listing_remains_an_empty_documents_array(self):
        self.assertEqual(self.client.get("/documents").json(), {"documents": []})

    def test_delete_cascades_chunks_invalidates_only_owner_cache_and_never_reembeds(self):
        owned = self._seed(7)
        other = self._seed(8, "other.pdf")
        with self.Session() as session:
            for user_id in (7, 8):
                session.add(AnswerCache(
                    user_id=user_id, normalized_query_hash=uuid.uuid4().hex * 2,
                    answer="cached", answer_mode="INSUFFICIENT_CONFIDENCE", reliability="LOW",
                    conflict_status="NONE", fallback_reason="NO_SUFFICIENT_DOCUMENT_EVIDENCE",
                    claims=[], sources=[], context_fingerprint=uuid.uuid4().hex * 2,
                    pipeline_version="test", gemini_calls=0,
                    expires_at=datetime.now(UTC) + timedelta(hours=1),
                ))
            session.commit()
        self.process.reset_mock()
        response = self.client.delete(f"/documents/{owned.id}")
        self.assertEqual(response.status_code, 204)
        self.assertEqual(self.process.call_count, 0)
        with self.Session() as session:
            self.assertIsNone(session.get(Document, owned.id))
            self.assertEqual(session.query(DocumentChunk).filter_by(document_id=owned.id).count(), 0)
            self.assertEqual(session.query(AnswerCache).filter_by(user_id=7).count(), 0)
            self.assertEqual(session.query(AnswerCache).filter_by(user_id=8).count(), 1)
            self.assertIsNotNone(session.get(Document, other.id))

    def test_delete_rejects_other_tenant_and_processing_record(self):
        private = self._seed(8)
        processing = self._seed(7, "processing.pdf", "PROCESSING", False)
        self.assertEqual(self.client.delete(f"/documents/{private.id}").status_code, 404)
        self.assertEqual(self.client.delete(f"/documents/{processing.id}").status_code, 409)

    def test_failed_delete_leaves_retryable_deleting_record_and_keeps_chunks(self):
        document = self._seed(7)
        with self.Session() as session:
            original_commit = session.commit
            calls = [0]
            def fail_final_commit():
                calls[0] += 1
                if calls[0] == 2:
                    raise RuntimeError("database unavailable")
                return original_commit()
            with patch.object(session, "commit", side_effect=fail_final_commit):
                with self.assertRaises(HTTPException) as raised:
                    asyncio.run(documents.Delete_Document(document.id, current_user=self.user, db=session))
            self.assertEqual(raised.exception.status_code, 503)
        with self.Session() as session:
            self.assertEqual(session.get(Document, document.id).status, "DELETING")
            self.assertEqual(session.query(DocumentChunk).filter_by(document_id=document.id).count(), 1)

    def test_invalid_uploads_are_rejected_before_embedding(self):
        self.assertEqual(self._post("notes.txt").status_code, 415)
        self.assertEqual(self._post(content=b"not a pdf").status_code, 400)
        with patch.dict(os.environ, {"MAX_PDF_PAGE_COUNT": "1"}):
            self.assertEqual(self._post(content=make_pdf(pages=2)).status_code, 413)
        self.process.assert_not_called()

    def test_upload_limits_filename_sanitization_and_temporary_storage_cleanup(self):
        payload = make_pdf() + b"x" * (64 * 1024)
        with patch.dict(os.environ, {"MAX_PDF_UPLOAD_SIZE_BYTES": str(64 * 1024)}):
            self.assertEqual(self._post(content=payload).status_code, 413)
        sanitized = self._post(filename=r"..\..\outside.pdf")
        self.assertEqual(sanitized.status_code, 201)
        self.assertEqual(sanitized.json()["filename"], "outside.pdf")
        self.assertEqual(list((self.temp_root / "learning-assistant-uploads").glob("upload-*.pdf")), [])

    def test_stream_write_failure_returns_safe_error_and_cleans_temporary_pdf(self):
        with patch.object(documents, "write_staged_upload", side_effect=OSError("private path")):
            response = self._post()
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["detail"], "Failed to process the uploaded PDF")
        self.assertNotIn("private path", response.text)
        self.assertEqual(list((self.temp_root / "learning-assistant-uploads").glob("upload-*.pdf")), [])

    def test_cancellation_during_upload_closes_input_and_removes_staging_file(self):
        class CancelDuringRead:
            filename = "notes.pdf"
            content_type = "application/pdf"
            def __init__(self):
                self.calls = 0
                self.closed = False
            async def read(self, _size):
                self.calls += 1
                if self.calls == 1:
                    return make_pdf()[:24]
                raise asyncio.CancelledError
            async def close(self):
                self.closed = True
        upload = CancelDuringRead()
        with self.Session() as session:
            with self.assertRaises(asyncio.CancelledError):
                asyncio.run(documents.Upload_Document(file=upload, current_user=self.user, db=session))
        self.assertTrue(upload.closed)
        self.assertEqual(list((self.temp_root / "learning-assistant-uploads").glob("upload-*.pdf")), [])

    def test_duplicate_filename_and_per_user_quota_are_database_backed(self):
        self._seed(7, "notes.pdf")
        self.assertEqual(self._post().status_code, 409)
        self.user = SimpleNamespace(ID=8)
        with self.Session() as session:
            session.add(Document(user_id=8, filename="large.pdf", storage_filename="legacy", file_size_bytes=9900,
                                 page_count=1, sha256="b" * 64, status="READY"))
            session.commit()
        with patch.dict(os.environ, {"MAX_USER_PDF_STORAGE_BYTES": "10000"}):
            self.assertEqual(self._post(filename="other.pdf").status_code, 413)


if __name__ == "__main__":
    unittest.main()
