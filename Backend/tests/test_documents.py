import asyncio
import json
import os
import sys
import types
import unittest
import uuid
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch
from datetime import UTC, datetime, timedelta

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.datastructures import Headers, UploadFile


# Upload tests must not initialize the local embedding model or call providers.
_ingest_stub = types.ModuleType("Rag.ingest")
_ingest_stub.Build_rag = Mock()
with patch.dict(sys.modules, {"Rag.ingest": _ingest_stub}):
    from App.Routers import documents
    from App.base import Base
    from App.database import get_db
    from App.models import AnswerCache, Document, User
    from App.upload_storage import generated_storage_filename
    from App.oauth2 import get_current_user
    from Rag import document_tracker, user_storage


def make_pdf(page_count=1, password=None, include_text=True):
    writer = PdfWriter()
    for _ in range(page_count):
        page = writer.add_blank_page(width=72, height=72)
        if include_text:
            font = DictionaryObject({
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            })
            page[NameObject("/Resources")] = DictionaryObject({
                NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})
            })
            stream = DecodedStreamObject()
            stream.set_data(b"BT /F1 12 Tf 10 40 Td (Upload test text) Tj ET")
            page[NameObject("/Contents")] = writer._add_object(stream)
    if password:
        writer.encrypt(password)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


class DocumentsUploadTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.documents_root_patch = patch.object(
            user_storage, "DOCUMENTS_ROOT", Path(self.temp_dir.name) / "documents"
        )
        self.documents_root_patch.start()
        self.addCleanup(self.documents_root_patch.stop)
        self.addCleanup(self.temp_dir.cleanup)
        self.storage_root_patch = patch.object(
            user_storage, "STORAGE_ROOT", Path(self.temp_dir.name) / "storage"
        )
        self.storage_root_patch.start()
        self.addCleanup(self.storage_root_patch.stop)

        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.addCleanup(self.engine.dispose)
        with self.Session() as session:
            session.add_all([
                User(ID=7, Name="User Seven", Email="seven@example.test", Password="hashed"),
                User(ID=8, Name="User Eight", Email="eight@example.test", Password="hashed"),
            ])
            session.commit()

        self.upload_limits = patch.dict(
            os.environ,
            {
                "MAX_PDF_UPLOAD_SIZE_BYTES": str(20 * 1024 * 1024),
                "MAX_PDF_PAGE_COUNT": "250",
                "MAX_USER_PDF_STORAGE_BYTES": str(200 * 1024 * 1024),
            },
        )
        self.upload_limits.start()
        self.addCleanup(self.upload_limits.stop)

        self.user = SimpleNamespace(ID=7)
        self.app = FastAPI()
        self.app.include_router(documents.router)
        self.app.dependency_overrides[get_current_user] = lambda: self.user
        self.app.dependency_overrides[get_db] = self._get_db
        self.client = TestClient(self.app)
        self.build_patch = patch.object(documents, "Build_rag")
        self.build_rag = self.build_patch.start()
        self.addCleanup(self.build_patch.stop)

    def _get_db(self):
        with self.Session() as session:
            yield session

    def _vector_store(self):
        if hasattr(self, "vector_store_module"):
            return self.vector_store_module
        from Rag import vector_store

        self.vector_store_module = vector_store
        self.vector_store_path_patch = patch.object(
            vector_store, "Get_user_paths", user_storage.Get_user_paths
        )
        self.vector_store_path_patch.start()
        self.addCleanup(self.vector_store_path_patch.stop)
        return self.vector_store_module

    def _post(self, filename="notes.pdf", content=None, content_type="application/pdf", headers=None):
        return self.client.post(
            "/documents/upload",
            files={"file": (filename, make_pdf() if content is None else content, content_type)},
            headers=headers,
        )

    def _user_directory(self, user_id=7):
        return Path(self.temp_dir.name) / "documents" / f"user_{user_id}"

    def _direct_upload(self, filename, content, headers=None):
        upload_headers = {"content-type": "application/pdf"}
        upload_headers.update(headers or {})
        upload = UploadFile(
            filename=filename,
            file=BytesIO(content),
            headers=Headers(upload_headers),
        )
        with self.Session() as session:
            return asyncio.run(documents.Upload_Document(
                file=upload, current_user=self.user, db=session
            ))

    def _assert_no_staging_files(self, directory=None):
        directory = directory or self._user_directory()
        if directory.exists():
            self.assertEqual(list(directory.glob(".upload-*.part")), [])

    def test_valid_pdf_within_limits_preserves_response_and_uses_generated_storage_name(self):
        response = self._post()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["filename"], "notes.pdf")
        self.assertEqual(
            response.json()["message"],
            "Document uploaded and processed successfully",
        )
        stored_pdfs = list(self._user_directory().glob("*.pdf"))
        self.assertEqual(len(stored_pdfs), 1)
        self.assertRegex(stored_pdfs[0].name, r"^notes--[0-9a-f]{32}\.pdf$")
        self.build_rag.assert_called_once()
        self.assertEqual(self.build_rag.call_args.args, (7,))
        self.assertEqual(
            self.build_rag.call_args.kwargs["eligible_storage_filenames"],
            {stored_pdfs[0].name},
        )
        with self.Session() as session:
            record = session.scalar(select(Document).where(Document.user_id == 7))
            self.assertIsNotNone(record)
            self.assertEqual(record.filename, "notes.pdf")
            self.assertEqual(record.storage_filename, stored_pdfs[0].name)
            self.assertEqual(record.file_size_bytes, stored_pdfs[0].stat().st_size)
            self.assertEqual(record.page_count, 1)
            self.assertEqual(record.status, "READY")
            self.assertEqual(len(record.sha256), 64)
        self._assert_no_staging_files()

    def _seed_document(self, user_id, display_name, text=None, status="READY"):
        storage_filename = generated_storage_filename(display_name)
        directory = self._user_directory(user_id)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / storage_filename
        path.write_bytes(make_pdf())
        row = Document(
            id=str(uuid.uuid4()),
            user_id=user_id,
            filename=display_name,
            storage_filename=storage_filename,
            file_size_bytes=path.stat().st_size,
            page_count=1,
            sha256=document_tracker.Calculate_file_hash(path),
            status=status,
        )
        with self.Session() as session:
            session.add(row)
            session.commit()
        return row, path

    def _cache_row(self, user_id):
        return AnswerCache(
            user_id=user_id,
            normalized_query_hash=uuid.uuid4().hex * 2,
            answer="Cached answer",
            answer_mode="GENERAL_KNOWLEDGE",
            message="General knowledge",
            reliability="MODERATE",
            conflict_status="NONE",
            fallback_reason="NO_SUFFICIENT_DOCUMENT_EVIDENCE",
            claims=[],
            sources=[],
            context_fingerprint=uuid.uuid4().hex * 2,
            pipeline_version="test",
            gemini_calls=1,
            created_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )

    def _rebuild_index(self, user_id, eligible_storage_filenames=None):
        import numpy as np

        vector_store = self._vector_store()
        directory = self._user_directory(user_id)
        pdfs = sorted(
            path for path in directory.glob("*.pdf")
            if eligible_storage_filenames is None or path.name in eligible_storage_filenames
        )
        chunks = [{
            "source": path.name,
            "document_id": path.name,
            "user_id": user_id,
            "page": 1,
            "text": path.stem,
        } for path in pdfs]
        vectors = np.array([[float(i), 0.0] for i in range(len(chunks))], dtype="float32")
        index = vector_store.Create_vector_store(vectors)
        if index is not None:
            vector_store.Save_vector_store(index, chunks, user_id)
        elif chunks:
            self.fail("Expected an index for nonempty documents")
        manifest = {
            path.name: document_tracker.Calculate_file_hash(path)
            for path in pdfs
        }
        document_tracker.Save_document_metadata(manifest, user_id)

    def test_list_and_details_are_scoped_to_authenticated_user(self):
        first, first_path = self._seed_document(7, "first.pdf")
        other, _other_path = self._seed_document(8, "private.pdf")

        response = self.client.get("/documents")
        self.assertEqual(response.status_code, 200)
        payload = response.json()["documents"]
        self.assertEqual([item["id"] for item in payload], [first.id])
        self.assertEqual(payload[0]["filename"], "first.pdf")
        self.assertEqual(payload[0]["file_size_bytes"], first_path.stat().st_size)
        self.assertEqual(payload[0]["page_count"], 1)
        self.assertEqual(payload[0]["status"], "READY")
        self.assertTrue(payload[0]["available"])
        self.assertNotIn(str(first_path), response.text)

        details = self.client.get(f"/documents/{first.id}")
        self.assertEqual(details.status_code, 200)
        self.assertEqual(details.json()["id"], first.id)
        self.assertNotIn("sha256", details.json())

        forbidden = self.client.get(f"/documents/{other.id}")
        self.assertEqual(forbidden.status_code, 404)
        missing = self.client.get(f"/documents/{uuid.uuid4()}")
        self.assertEqual(missing.status_code, 404)

    def test_empty_document_listing_returns_an_empty_array(self):
        response = self.client.get("/documents")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"documents": []})

    def test_successful_delete_rebuilds_only_users_index_and_invalidates_only_users_cache(self):
        removed, removed_path = self._seed_document(7, "remove.pdf")
        remaining, remaining_path = self._seed_document(7, "keep.pdf")
        other, other_path = self._seed_document(8, "other.pdf")
        self._rebuild_index(7)
        self._rebuild_index(8)
        other_index_before = (user_storage.Get_user_paths(8)[1] / "index.faiss").read_bytes()
        with self.Session() as session:
            session.add_all([self._cache_row(7), self._cache_row(8)])
            session.commit()

        self.build_rag.side_effect = self._rebuild_index
        with self.Session() as session:
            response = asyncio.run(documents.Delete_Document(
                removed.id, current_user=self.user, db=session
            ))

        self.assertEqual(response.status_code, 204)
        self.assertFalse(removed_path.exists())
        self.assertTrue(remaining_path.exists())
        self.assertTrue(other_path.exists())
        vector_store = self._vector_store()
        self.assertEqual(
            {chunk["document_id"] for chunk in vector_store.Load_vector_store(7)[1]},
            {remaining.storage_filename},
        )
        self.assertEqual(
            (user_storage.Get_user_paths(8)[1] / "index.faiss").read_bytes(),
            other_index_before,
        )
        with self.Session() as session:
            self.assertIsNone(session.get(Document, removed.id))
            self.assertIsNotNone(session.get(Document, remaining.id))
            self.assertEqual(session.query(AnswerCache).filter_by(user_id=7).count(), 0)
            self.assertEqual(session.query(AnswerCache).filter_by(user_id=8).count(), 1)

    def test_failed_delete_keeps_recoverable_state_and_filters_deleted_chunks(self):
        document, _path = self._seed_document(7, "delete-fails.pdf")
        self._rebuild_index(7)
        with self.Session() as session:
            session.add(self._cache_row(7))
            session.commit()
        self.build_rag.side_effect = RuntimeError("private index path")

        with self.Session() as session:
            with self.assertRaises(HTTPException) as error:
                asyncio.run(documents.Delete_Document(
                    document.id, current_user=self.user, db=session
                ))
        self.assertEqual(error.exception.status_code, 503)
        self.assertNotIn("private index path", error.exception.detail)
        with self.Session() as session:
            stored = session.get(Document, document.id)
            self.assertEqual(stored.status, "DELETING")
            self.assertEqual(session.query(AnswerCache).filter_by(user_id=7).count(), 0)
            ready_documents = set(session.scalars(
                select(Document.storage_filename).where(
                    Document.user_id == 7,
                    Document.status == "READY",
                )
            ).all())
        self.assertTrue(list(self._user_directory().glob(".deleting-*.part")))
        import numpy as np
        vector_store = self._vector_store()
        index, chunks = vector_store.Load_vector_store(7)
        retrieval = vector_store.Retrieve(
            "q", index, chunks,
            SimpleNamespace(encode=lambda _query: np.array([0.0, 0.0])),
            7,
            allowed_document_ids=ready_documents,
        )
        self.assertEqual(retrieval.chunks, ())

    def test_delete_missing_or_other_users_document_returns_404_without_changes(self):
        other, other_path = self._seed_document(8, "other.pdf")
        with self.Session() as session:
            with self.assertRaises(HTTPException) as error:
                asyncio.run(documents.Delete_Document(
                    other.id, current_user=self.user, db=session
                ))
        self.assertEqual(error.exception.status_code, 404)
        self.assertTrue(other_path.exists())
        with self.Session() as session:
            with self.assertRaises(HTTPException) as missing:
                asyncio.run(documents.Delete_Document(
                    str(uuid.uuid4()), current_user=self.user, db=session
                ))
        self.assertEqual(missing.exception.status_code, 404)

    def test_legacy_backfill_is_idempotent_and_only_marks_indexed_files_ready(self):
        vector_store = self._vector_store()
        from scripts import backfill_documents

        import numpy as np

        legacy_root = Path(self.temp_dir.name) / "legacy-documents"
        legacy_storage = Path(self.temp_dir.name) / "legacy-storage"
        user_dir = legacy_root / "user_7"
        user_dir.mkdir(parents=True)
        indexed_path = user_dir / "indexed.pdf"
        unindexed_path = user_dir / "unindexed.pdf"
        indexed_path.write_bytes(make_pdf())
        unindexed_path.write_bytes(make_pdf())
        patch_root = patch.object(backfill_documents, "DOCUMENTS_ROOT", legacy_root)
        patch_root.start()
        self.addCleanup(patch_root.stop)
        path_patch = patch.object(
            vector_store,
            "Get_user_paths",
            lambda user_id: (legacy_root / f"user_{user_id}", legacy_storage / f"user_{user_id}"),
        )
        path_patch.start()
        self.addCleanup(path_patch.stop)
        load_patch = patch.object(
            backfill_documents, "Load_vector_store", vector_store.Load_vector_store
        )
        load_patch.start()
        self.addCleanup(load_patch.stop)
        manifest = {indexed_path.name: document_tracker.Calculate_file_hash(indexed_path)}
        (user_dir / "documents.json").write_text(json.dumps(manifest), encoding="utf-8")
        manifest_patch = patch.object(
            backfill_documents, "Load_document_metadata",
            side_effect=lambda _user_id: manifest,
        )
        manifest_patch.start()
        self.addCleanup(manifest_patch.stop)

        legacy_storage_user_dir = legacy_storage / "user_7"
        legacy_storage_user_dir.mkdir(parents=True)
        vector_store.Save_vector_store(
            vector_store.Create_vector_store(np.array([[0.0, 0.0]], dtype="float32")),
            [{"source": indexed_path.name, "document_id": indexed_path.name,
              "user_id": 7, "page": 1, "text": "indexed"}],
            7,
        )
        with self.Session() as session:
            first = backfill_documents.backfill_documents(session)
            self.assertEqual(first["ready"], 1)
            self.assertEqual(first["failed"], 1)
            second = backfill_documents.backfill_documents(session)
            self.assertEqual(second["existing"], 2)
            rows = session.scalars(select(Document).where(Document.user_id == 7)).all()
            self.assertEqual(
                {row.storage_filename: row.status for row in rows},
                {"indexed.pdf": "READY", "unindexed.pdf": "FAILED"},
            )
        self.assertTrue(indexed_path.exists())
        self.assertTrue(unindexed_path.exists())

    def test_per_file_size_is_enforced_while_streaming_not_from_content_length(self):
        pdf = make_pdf() + (b"x" * 70000)
        with patch.dict(os.environ, {"MAX_PDF_UPLOAD_SIZE_BYTES": str(64 * 1024)}):
            with self.assertRaises(HTTPException) as error:
                self._direct_upload("notes.pdf", pdf, {"content-length": "1"})
        self.assertEqual(error.exception.status_code, 413)
        self.assertIn("per-file size limit", error.exception.detail)
        self.build_rag.assert_not_called()
        self._assert_no_staging_files()

    def test_upload_at_the_configured_file_size_limit_is_accepted(self):
        pdf = make_pdf()
        with patch.dict(os.environ, {"MAX_PDF_UPLOAD_SIZE_BYTES": str(len(pdf))}):
            result = self._direct_upload("notes.pdf", pdf)
        self.assertEqual(result["filename"], "notes.pdf")
        self.build_rag.assert_called_once()
        self.assertEqual(len(self.build_rag.call_args.kwargs["eligible_storage_filenames"]), 1)

    def test_missing_content_length_does_not_prevent_stream_validation(self):
        result = self._direct_upload("notes.pdf", make_pdf())
        self.assertEqual(result["filename"], "notes.pdf")
        self.build_rag.assert_called_once()
        self.assertEqual(len(self.build_rag.call_args.kwargs["eligible_storage_filenames"]), 1)

    def test_user_quota_is_checked_and_isolated_per_authenticated_user(self):
        self._user_directory(7).mkdir(parents=True)
        (self._user_directory(7) / "existing.pdf").write_bytes(b"x" * 9900)
        pdf = make_pdf()
        with patch.dict(os.environ, {"MAX_USER_PDF_STORAGE_BYTES": "10000"}):
            over_quota = self._post(content=pdf)
            self.assertEqual(over_quota.status_code, 413)
            self.assertIn("stored PDF size limit", over_quota.json()["detail"])

            self.user = SimpleNamespace(ID=8)
            within_quota = self._post(content=pdf)

        self.assertEqual(within_quota.status_code, 201)
        self.assertEqual(len(list(self._user_directory(7).glob("*.pdf"))), 1)
        self.assertEqual(len(list(self._user_directory(8).glob("*.pdf"))), 1)

    def test_unsupported_media_type_and_non_pdf_content_are_rejected(self):
        unsupported_extension = self._post(filename="notes.txt", content=make_pdf())
        self.assertEqual(unsupported_extension.status_code, 415)

        unsupported_mime = self._post(content_type="application/octet-stream")
        self.assertEqual(unsupported_mime.status_code, 415)

        renamed_text = self._post(content=b"This is not a PDF")
        self.assertEqual(renamed_text.status_code, 400)
        self.build_rag.assert_not_called()
        self._assert_no_staging_files()

    def test_missing_filename_is_rejected(self):
        response = self._post(filename="")
        # FastAPI rejects an empty multipart filename before entering the route.
        self.assertEqual(response.status_code, 422)
        self.build_rag.assert_not_called()

    def test_empty_corrupt_encrypted_and_page_limited_pdfs_are_rejected(self):
        for content in (b"", b"%PDF-corrupt"):
            response = self._post(content=content)
            self.assertEqual(response.status_code, 400)

        encrypted = self._post(content=make_pdf(password="test-password"))
        self.assertEqual(encrypted.status_code, 400)
        self.assertIn("unreadable, encrypted", encrypted.json()["detail"])

        scanned_or_blank = self._post(content=make_pdf(include_text=False))
        self.assertEqual(scanned_or_blank.status_code, 400)
        self.assertIn("no extractable text", scanned_or_blank.json()["detail"])

        with patch.dict(os.environ, {"MAX_PDF_PAGE_COUNT": "1"}):
            too_many_pages = self._post(content=make_pdf(page_count=2))
        self.assertEqual(too_many_pages.status_code, 413)
        self.assertIn("page limit", too_many_pages.json()["detail"])
        self.build_rag.assert_not_called()
        self._assert_no_staging_files()

    def test_filename_path_traversal_is_sanitized_and_never_used_as_storage_path(self):
        result = self._direct_upload(r"..\..\outside.pdf", make_pdf())
        self.assertEqual(result["filename"], "outside.pdf")
        stored_pdfs = list(self._user_directory().glob("*.pdf"))
        self.assertEqual(len(stored_pdfs), 1)
        self.assertTrue(stored_pdfs[0].name.startswith("outside--"))
        self.assertFalse((Path(self.temp_dir.name) / "outside.pdf").exists())

    def test_duplicate_display_filename_is_rejected(self):
        self.assertEqual(self._post().status_code, 201)
        duplicate = self._post()
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(len(list(self._user_directory().glob("*.pdf"))), 1)
        self.assertEqual(self.build_rag.call_count, 1)

    def test_unexpected_ingestion_failure_removes_published_pdf_and_hides_details(self):
        self.build_rag.side_effect = RuntimeError("internal filesystem location")
        response = self._post()
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["detail"], "Failed to process the uploaded PDF")
        self.assertNotIn("internal filesystem location", response.text)
        self.assertEqual(list(self._user_directory().glob("*.pdf")), [])
        self._assert_no_staging_files()

    def test_temporary_storage_failure_returns_safe_error_and_publishes_nothing(self):
        with patch.object(documents, "write_staged_upload", side_effect=OSError("private path")):
            response = self._post()
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["detail"], "Temporary upload storage is unavailable")
        self.assertNotIn("private path", response.text)
        self.assertEqual(list(self._user_directory().glob("*.pdf")), [])
        self._assert_no_staging_files()

    def test_cancellation_during_streaming_cleans_staged_file_and_closes_upload(self):
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
        with self.assertRaises(asyncio.CancelledError):
            asyncio.run(documents.Upload_Document(file=upload, current_user=self.user))
        self.assertTrue(upload.closed)
        self.assertEqual(list(self._user_directory().glob(".upload-*.part")), [])
        self.assertEqual(list(self._user_directory().glob("*.pdf")), [])
        self.build_rag.assert_not_called()


if __name__ == "__main__":
    unittest.main()
