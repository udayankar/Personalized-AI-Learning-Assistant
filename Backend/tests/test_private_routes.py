import sys
import types
import unittest
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch
import jwt
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

rag_stub = types.ModuleType("Rag.rag")
rag_stub.Ask_question = Mock()
ingest_stub = types.ModuleType("Rag.ingest")
ingest_stub.Build_rag = Mock()
with patch.dict(sys.modules, {"Rag.rag": rag_stub, "Rag.ingest": ingest_stub}):
    from App.Routers import chat, documents
    from App import oauth2
    from App.database import get_db
    from App.csrf import configure_csrf_protection, create_csrf_token

class FakeQuery:
    def __init__(self, user):
        self.user = user

    def filter(self, *_args):
        return self

    def first(self):
        return self.user


class FakeDB:
    def __init__(self, user):
        self.user = user

    def query(self, *_args):
        return FakeQuery(self.user)


class PrivateRouteAuthenticationTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {
            "APP_ENV": "test",
            "CSRF_SECRET_KEY": "task-one-csrf-test-secret-with-32-bytes",
            "SECRET_KEY": oauth2.SECRET_KEY,
            "CORS_ALLOWED_ORIGINS": "http://localhost:1234",
            "COOKIE_SECURE": "false",
            "COOKIE_SAMESITE": "lax",
        })
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.app = FastAPI()
        self.app.include_router(chat.router)
        self.app.include_router(documents.router)
        configure_csrf_protection(self.app)
        self.app.dependency_overrides[get_db] = lambda: FakeDB(
            types.SimpleNamespace(Email="student@example.com")
        )
        self.client = TestClient(self.app)
        self.temp_dir = TemporaryDirectory(dir=os.getcwd())
        self.documents_dir_patch = patch.object(
            documents, "DOCUMENTS_DIR", Path(self.temp_dir.name)
        )
        self.documents_dir_patch.start()
        self.addCleanup(self.documents_dir_patch.stop)
        self.addCleanup(self.temp_dir.cleanup)
        self.ask_question = patch.object(chat, "Ask_question", return_value=("Answer", []))
        self.build_rag = patch.object(documents, "Build_rag")
        self.ask_question_mock = self.ask_question.start()
        self.build_rag_mock = self.build_rag.start()
        self.addCleanup(self.ask_question.stop)
        self.addCleanup(self.build_rag.stop)

    def _token(self, payload=None, key=None):
        return jwt.encode(
            payload or {"Email": "student@example.com", "exp": datetime.now(UTC) + timedelta(minutes=5)},
            key or oauth2.SECRET_KEY,
            algorithm=oauth2.ALGORITHM,
        )

    def _upload(self, cookies=None):
        headers = self._csrf_headers(cookies) if cookies else None
        return self.client.post(
            "/documents/upload",
            files={"file": ("notes.pdf", b"%PDF-test", "application/pdf")},
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
        self.build_rag_mock.assert_not_called()
        self.assertEqual(list(Path(self.temp_dir.name).iterdir()), [])

    def test_missing_malformed_invalid_signature_and_expired_tokens_are_rejected(self):
        expired = self._token(
            {"Email": "student@example.com", "exp": datetime.now(UTC) - timedelta(minutes=1)}
        )
        invalid_signature = self._token(key="a-different-signing-secret")
        cases = [
            ("missing", None),
            ("malformed", "not-a-jwt"),
            ("invalid signature", invalid_signature),
            ("expired", expired),
        ]
        for label, token in cases:
            with self.subTest(token=label):
                cookies = {"access_token": token} if token is not None else None
                response = self.client.post(
                    "/chat/query", json={"query": "Explain this"}, cookies=cookies
                )
                self.assertEqual(response.status_code, 401)
        self.ask_question_mock.assert_not_called()

    def test_valid_authenticated_chat_reaches_existing_logic(self):
        cookies, csrf = self._auth_cookies()
        response = self.client.post(
            "/chat/query",
            json={"query": "Explain this"},
            cookies=cookies,
            headers=self._csrf_headers(cookies),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"answer": "Answer", "sources": []})
        self.ask_question_mock.assert_called_once_with("Explain this")

    def test_valid_authenticated_upload_reaches_existing_logic(self):
        cookies, _ = self._auth_cookies()
        response = self._upload(cookies=cookies)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["filename"], "notes.pdf")
        self.build_rag_mock.assert_called_once_with()
        self.assertTrue((Path(self.temp_dir.name) / "notes.pdf").exists())

    def test_no_answer_preserves_intended_503(self):
        self.ask_question_mock.return_value = (None, [])
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
        self.build_rag_mock.side_effect = HTTPException(status_code=503, detail="Processing unavailable")
        cookies, _ = self._auth_cookies()
        response = self._upload(cookies=cookies)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], "Processing unavailable")
        self.assertFalse((Path(self.temp_dir.name) / "notes.pdf").exists())


if __name__ == "__main__":
    unittest.main()
