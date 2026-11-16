import asyncio
import os
import sys
import types
import unittest
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from starlette.datastructures import Headers, UploadFile


# Upload tests must not initialize the local embedding model or call providers.
_ingest_stub = types.ModuleType("Rag.ingest")
_ingest_stub.Build_rag = Mock()
with patch.dict(sys.modules, {"Rag.ingest": _ingest_stub}):
    from App.Routers import documents
    from App.oauth2 import get_current_user
    from Rag import user_storage


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
        self.client = TestClient(self.app)
        self.build_patch = patch.object(documents, "Build_rag")
        self.build_rag = self.build_patch.start()
        self.addCleanup(self.build_patch.stop)

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
        return asyncio.run(documents.Upload_Document(file=upload, current_user=self.user))

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
        self.build_rag.assert_called_once_with(7)
        self._assert_no_staging_files()

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
        self.build_rag.assert_called_once_with(7)

    def test_missing_content_length_does_not_prevent_stream_validation(self):
        result = self._direct_upload("notes.pdf", make_pdf())
        self.assertEqual(result["filename"], "notes.pdf")
        self.build_rag.assert_called_once_with(7)

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
