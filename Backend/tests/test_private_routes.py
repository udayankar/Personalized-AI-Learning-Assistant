import asyncio
import sys
import threading
import types
import unittest
import os
from types import SimpleNamespace
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch
import jwt
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.requests import Request

rag_stub = types.ModuleType("Rag.rag")
rag_stub.Ask_question = Mock()
class StubRAGProcessingError(RuntimeError):
    pass
rag_stub.RAGProcessingError = StubRAGProcessingError
ingest_stub = types.ModuleType("Rag.ingest")
ingest_stub.Process_document = Mock(return_value=([{"text": "test passage", "page": 1}], [[1.0] + [0.0] * 767]))
with patch.dict(sys.modules, {"Rag.rag": rag_stub, "Rag.ingest": ingest_stub}):
    from App.Routers import auth, chat, documents
    from App import oauth2
    from App.database import get_db
    from App.base import Base
    from App.models import User
    from App.csrf import configure_csrf_protection, create_csrf_token
    from Rag import user_storage

class FakeQuery:
    def __init__(self, users):
        self.users = users

    def filter(self, *criteria):
        users = self.users
        for criterion in criteria:
            field = criterion.left.key
            expected = criterion.right.value
            users = [user for user in users if getattr(user, field) == expected]
        return FakeQuery(users)

    def first(self):
        return self.users[0] if self.users else None


class FakeDB:
    def __init__(self, *users):
        self.users = users

    def query(self, *_args):
        return FakeQuery(list(self.users))


class PrivateRouteAuthenticationTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {
            "APP_ENV": "test",
            "CSRF_SECRET_KEY": "task-one-csrf-test-secret-with-32-bytes",
            "SECRET_KEY": oauth2.SECRET_KEY,
            "ALGORITHM": "HS256",
            "ACCESS_TOKEN_EXPIRE_MINUTES": "30",
            "CORS_ALLOWED_ORIGINS": "http://localhost:1234",
            "COOKIE_SECURE": "false",
            "COOKIE_SAMESITE": "lax",
        })
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.app = FastAPI()
        self.app.include_router(chat.router)
        self.app.include_router(documents.router)
        self.app.include_router(auth.router)
        configure_csrf_protection(self.app)
        self.user = types.SimpleNamespace(
            ID=7,
            Name="Test Student",
            Email="student@example.com",
            Created_at=datetime.now(UTC),
        )
        self.other_user = types.SimpleNamespace(
            ID=8,
            Name="Other Student",
            Email="other@example.com",
            Created_at=datetime.now(UTC),
        )
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        with self.Session() as session:
            session.add_all([
                User(ID=7, Name=self.user.Name, Email=self.user.Email, Password="hashed"),
                User(ID=8, Name=self.other_user.Name, Email=self.other_user.Email, Password="hashed"),
            ])
            session.commit()

        def get_test_db():
            with self.Session() as session:
                yield session

        self.app.dependency_overrides[get_db] = get_test_db
        self.addCleanup(self.engine.dispose)
        self.client = TestClient(self.app)
        self.temp_dir = TemporaryDirectory(dir=os.getcwd())
        self.temp_root_patch = patch.object(documents.tempfile, "gettempdir", return_value=self.temp_dir.name)
        self.temp_root_patch.start()
        self.addCleanup(self.temp_root_patch.stop)
        self.documents_root_patch = patch.object(
            user_storage, "DOCUMENTS_ROOT", Path(self.temp_dir.name) / "documents"
        )
        self.storage_root_patch = patch.object(
            user_storage, "STORAGE_ROOT", Path(self.temp_dir.name) / "storage"
        )
        self.documents_root_patch.start()
        self.storage_root_patch.start()
        self.addCleanup(self.documents_root_patch.stop)
        self.addCleanup(self.storage_root_patch.stop)
        self.addCleanup(self.temp_dir.cleanup)
        no_information = "You haven't uploaded any documents yet. Upload a document to start asking questions."
        self.ask_question = patch.object(chat, "Ask_question", return_value=SimpleNamespace(
            answer=no_information,
            answer_mode="INSUFFICIENT_CONFIDENCE",
            message=None,
            reliability="LOW",
            conflict_status="NONE",
            fallback_reason="NO_DOCUMENTS_UPLOADED",
            claims=[],
            sources=[],
        ))
        self.process_document = patch.object(documents, "Process_document", return_value=([{"text": "test passage", "page": 1}], [[1.0] + [0.0] * 767]))
        self.ask_question_mock = self.ask_question.start()
        self.process_document_mock = self.process_document.start()
        self.addCleanup(self.ask_question.stop)
        self.addCleanup(self.process_document.stop)

    def _token(self, payload=None, key=None):
        return jwt.encode(
            payload or {"sub": "7", "exp": datetime.now(UTC) + timedelta(minutes=5)},
            key or oauth2.SECRET_KEY,
            algorithm=oauth2.ALGORITHM,
        )

    def _upload(self, cookies=None, data=None):
        headers = self._csrf_headers(cookies) if cookies else None
        writer = PdfWriter()
        page = writer.add_blank_page(width=72, height=72)
        font = DictionaryObject({
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        })
        page[NameObject("/Resources")] = DictionaryObject({
            NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})
        })
        stream = DecodedStreamObject()
        stream.set_data(b"BT /F1 12 Tf 10 40 Td (Private route upload test) Tj ET")
        page[NameObject("/Contents")] = writer._add_object(stream)
        content = BytesIO()
        writer.write(content)
        return self.client.post(
            "/documents/upload",
            files={"file": ("notes.pdf", content.getvalue(), "application/pdf")},
            data=data,
            cookies=cookies,
            headers=headers,
        )

    def _auth_cookies(self):
        access = self._token()
        csrf = create_csrf_token(access_token=access)
        return {"access_token": access, "csrf_token": csrf}, csrf

    def _csrf_headers(self, cookies):
        return {"Origin": "http://localhost:1234", "X-CSRF-Token": cookies["csrf_token"]}

    def test_anonymous_chat_is_rejected_before_rag(self):
        response = self.client.post("/chat/query", json={"query": "Explain this"})
        self.assertEqual(response.status_code, 401)
        self.ask_question_mock.assert_not_called()

    def test_anonymous_upload_is_rejected_before_file_processing(self):
        response = self._upload()
        self.assertEqual(response.status_code, 401)
        self.process_document_mock.assert_not_called()
        self.assertEqual(list(Path(self.temp_dir.name).iterdir()), [])

    def test_missing_malformed_invalid_signature_and_expired_tokens_are_rejected(self):
        future_expiry = datetime.now(UTC) + timedelta(minutes=5)
        expired = self._token(
            {"sub": "7", "exp": datetime.now(UTC) - timedelta(minutes=1)}
        )
        invalid_signature = self._token(key="a-different-signing-secret")
        cases = [
            ("missing", None),
            ("malformed", "not-a-jwt"),
            ("invalid signature", invalid_signature),
            ("expired", expired),
            ("missing subject", self._token({"exp": future_expiry})),
            ("email-only legacy token", self._token({"Email": "student@example.com", "exp": future_expiry})),
            ("malformed subject", self._token({"sub": "not-an-id", "exp": future_expiry})),
            ("non-string subject", self._token({"sub": 7, "exp": future_expiry})),
            ("zero subject", self._token({"sub": "0", "exp": future_expiry})),
            ("negative subject", self._token({"sub": "-7", "exp": future_expiry})),
            ("nonexistent user", self._token({"sub": "999", "exp": future_expiry})),
        ]
        for label, token in cases:
            with self.subTest(token=label):
                cookies = {"access_token": token} if token is not None else None
                response = self.client.post(
                    "/chat/query", json={"query": "Explain this"}, cookies=cookies
                )
                self.assertEqual(response.status_code, 401)
        self.ask_question_mock.assert_not_called()

    def test_token_creation_accepts_only_a_positive_user_id_and_uses_sub(self):
        token = oauth2.create_access_token("7")
        claims = jwt.decode(token, oauth2.SECRET_KEY, algorithms=[oauth2.ALGORITHM])
        self.assertEqual(claims["sub"], "7")
        self.assertNotIn("Email", claims)
        for invalid_user_id in ("0", "07", "-7", "not-an-id", {"sub": "8"}):
            with self.subTest(user_id=invalid_user_id):
                with self.assertRaises(ValueError):
                    oauth2.create_access_token(invalid_user_id)

    def test_optional_current_user_uses_subject_and_rejects_legacy_email_tokens(self):
        def request_with_cookie(token):
            return Request({
                "type": "http",
                "http_version": "1.1",
                "method": "GET",
                "scheme": "http",
                "path": "/",
                "raw_path": b"/",
                "query_string": b"",
                "headers": [(b"cookie", f"access_token={token}".encode())],
                "server": ("testserver", 80),
                "client": ("testclient", 50000),
                "root_path": "",
            })

        authenticated = oauth2.get_current_user_optional(
            request_with_cookie(self._token()), FakeDB(self.user, self.other_user)
        )
        legacy_token = self._token({
            "Email": self.user.Email,
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        })
        legacy = oauth2.get_current_user_optional(
            request_with_cookie(legacy_token), FakeDB(self.user, self.other_user)
        )
        self.assertIs(authenticated, self.user)
        self.assertIsNone(legacy)

    def test_authenticated_identity_comes_from_jwt_subject_not_request_ids(self):
        response = self.client.get(
            "/users/me?user_id=8",
            cookies={"access_token": self._token()},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["ID"], 7)

    def test_valid_authenticated_chat_reaches_existing_logic(self):
        cookies, csrf = self._auth_cookies()
        response = self.client.post(
            "/chat/query",
            json={"query": "Explain this", "user_id": 8},
            cookies=cookies,
            headers=self._csrf_headers(cookies),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            "answer": "You haven't uploaded any documents yet. Upload a document to start asking questions.",
            "answer_mode": "INSUFFICIENT_CONFIDENCE",
            "message": None,
            "reliability": "LOW",
            "conflict_status": "NONE",
            "fallback_reason": "NO_DOCUMENTS_UPLOADED",
            "claims": [],
            "sources": [],
        })
        self.ask_question_mock.assert_called_once_with("Explain this", 7)

    def test_chat_response_exposes_answer_mode_and_citations(self):
        cookies, _ = self._auth_cookies()
        self.ask_question_mock.return_value = SimpleNamespace(
            answer="Grounded answer",
            answer_mode="DOCUMENT_SUPPORTED",
            message=None,
            reliability="HIGH",
            conflict_status="NONE",
            fallback_reason=None,
            claims=[{
                "text": "Grounded answer",
                "classification": "SUPPORTED",
                "sources": [{
                    "reference": "passage-abc123", "source": "notes.pdf", "page": 3,
                    "text": "Retrieved passage",
                }],
            }],
            sources=[{
                "reference": "passage-abc123",
                "source": "notes.pdf",
                "page": 3,
                "text": "Retrieved passage",
            }],
        )

        response = self.client.post(
            "/chat/query", json={"query": "Explain this"},
            cookies=cookies, headers=self._csrf_headers(cookies),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["answer_mode"], "DOCUMENT_SUPPORTED")
        self.assertEqual(response.json()["reliability"], "HIGH")
        self.assertEqual(response.json()["sources"][0]["reference"], "passage-abc123")
        self.assertEqual(response.json()["sources"][0]["page"], 3)
        self.assertEqual(response.json()["claims"][0]["sources"][0]["source"], "notes.pdf")

    def test_chat_runs_synchronous_rag_work_off_the_async_event_loop(self):
        caller_thread = threading.get_ident()
        rag_thread_ids = []

        def capture_rag_thread(*_args):
            rag_thread_ids.append(threading.get_ident())
            return self.ask_question_mock.return_value

        async def invoke_chat():
            with patch.object(chat, "Ask_question", side_effect=capture_rag_thread):
                return await chat.Give_Query(
                    SimpleNamespace(query="Explain this"), self.user
                )

        result = asyncio.run(invoke_chat())
        self.assertEqual(result["answer_mode"], "INSUFFICIENT_CONFIDENCE")
        self.assertEqual(len(rag_thread_ids), 1)
        self.assertNotEqual(rag_thread_ids[0], caller_thread)

    def test_chat_reports_document_model_failure_as_temporary_service_error(self):
        cookies, _ = self._auth_cookies()
        self.ask_question_mock.side_effect = chat.RAGProcessingError("provider failure")

        response = self.client.post(
            "/chat/query", json={"query": "Explain this"},
            cookies=cookies, headers=self._csrf_headers(cookies),
        )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json()["detail"],
            "Document-based answering is temporarily unavailable. Please try again.",
        )

    def test_valid_authenticated_upload_reaches_existing_logic(self):
        cookies, _ = self._auth_cookies()
        response = self._upload(cookies=cookies, data={"user_id": "8"})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["filename"], "notes.pdf")
        self.process_document_mock.assert_called_once()
        self.assertFalse(list(Path(self.temp_dir.name).glob("**/*.pdf")))

    def test_no_answer_preserves_intended_503(self):
        self.ask_question_mock.return_value = SimpleNamespace(answer="")
        cookies, _ = self._auth_cookies()
        response = self.client.post(
            "/chat/query", json={"query": "Explain this"},
            cookies=cookies, headers=self._csrf_headers(cookies),
        )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], "Failed to generate answer")

    def test_intentional_http_exception_status_and_message_are_preserved(self):
        self.ask_question_mock.side_effect = HTTPException(status_code=429, detail="Try again later")
        cookies, _ = self._auth_cookies()
        response = self.client.post(
            "/chat/query", json={"query": "Explain this"},
            cookies=cookies, headers=self._csrf_headers(cookies),
        )
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json()["detail"], "Try again later")

    def test_unexpected_chat_exception_returns_safe_generic_500(self):
        self.ask_question_mock.side_effect = RuntimeError("private internal detail")
        cookies, _ = self._auth_cookies()
        response = self.client.post(
            "/chat/query", json={"query": "Explain this"},
            cookies=cookies, headers=self._csrf_headers(cookies),
        )
        self.assertEqual(response.status_code, 500)
        self.assertEqual(
            response.json()["detail"],
            "An error occurred while processing the query",
        )
        self.assertNotIn("private internal detail", response.text)

    def test_upload_preserves_intentional_http_exception_and_cleans_partial_file(self):
        self.process_document_mock.side_effect = HTTPException(status_code=503, detail="Processing unavailable")
        cookies, _ = self._auth_cookies()
        response = self._upload(cookies=cookies)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], "Processing unavailable")
        self.assertFalse(list(Path(self.temp_dir.name).glob("**/*.pdf")))


if __name__ == "__main__":
    unittest.main()
