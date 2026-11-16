import os
import secrets
import sys
import types
import unittest
import uuid
from io import BytesIO
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch
import jwt
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from fastapi import HTTPException
from fastapi.testclient import TestClient

TEST_SECRET = "task-two-csrf-test-secret-32-bytes-minimum"
FRONTEND_ORIGIN = "http://localhost:1234"


def valid_pdf_bytes():
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
    stream.set_data(b"BT /F1 12 Tf 10 40 Td (CSRF upload test) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(stream)
    content = BytesIO()
    writer.write(content)
    return content.getvalue()


rag_stub = types.ModuleType("Rag.rag")
rag_stub.Ask_question = Mock()
rag_stub.RAGProcessingError = type("RAGProcessingError", (RuntimeError,), {})
ingest_stub = types.ModuleType("Rag.ingest")
ingest_stub.Build_rag = Mock()
sys.modules["Rag.rag"] = rag_stub
sys.modules["Rag.ingest"] = ingest_stub
from App.Routers import auth, chat, documents, signup
from App import oauth2
from App.config import get_security_settings
from App.csrf import create_csrf_token
from App.database import Base, get_db

class FakeResult:
    def __init__(self, user, rows=()):
        self.user = user
        self.rows = rows

    def scalar_one_or_none(self):
        return self.user

    def all(self):
        return self.rows

class FakeScalarList:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values

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
        self.user = users[0]
        self.execute_count = 0
        self.add_count = 0
        self.commit_count = 0
        self.documents = []

    def query(self, *_args):
        return FakeQuery(list(self.users))

    def execute(self, *_args):
        self.execute_count += 1
        rows = [
            (item.storage_filename, item.sha256)
            for item in self.documents
            if item.user_id == self.user.ID and item.status in {"PROCESSING", "READY"}
        ]
        return FakeResult(self.user, rows)

    def scalars(self, *_args):
        return FakeScalarList([
            item.storage_filename for item in self.documents
            if item.user_id == 7 and item.status in {"PROCESSING", "READY"}
        ])

    def add(self, item):
        self.add_count += 1
        if hasattr(item, "storage_filename"):
            item.id = item.id or str(uuid.uuid4())
            self.documents.append(item)

    def commit(self):
        self.commit_count += 1

    def refresh(self, _item):
        return None

    def rollback(self):
        return None

class CsrfProtectionTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(
            os.environ,
            {
                "APP_ENV": "test",
                "SECRET_KEY": "task-two-independent-jwt-test-secret-32-bytes",
                "ALGORITHM": "HS256",
                "ACCESS_TOKEN_EXPIRE_MINUTES": "30",
                "CSRF_SECRET_KEY": TEST_SECRET,
                "CSRF_TOKEN_TTL_SECONDS": "3600",
                "CORS_ALLOWED_ORIGINS": FRONTEND_ORIGIN,
                "COOKIE_SECURE": "false",
                "COOKIE_SAMESITE": "lax",
                "COOKIE_DOMAIN": "",
            },
        )
        self.environment.start()
        self.addCleanup(self.environment.stop)

        self.user = types.SimpleNamespace(
            ID=7,
            Name="Test Student",
            Email="student@example.com",
            Password="hashed-password",
            Created_at=datetime.now(UTC),
        )
        self.other_user = types.SimpleNamespace(
            ID=8,
            Name="Other Student",
            Email="other@example.com",
            Password="hashed-password",
            Created_at=datetime.now(UTC),
        )
        self.db = FakeDB(self.user, self.other_user)
        with patch.object(Base.metadata, "create_all"):
            from App.main import app as configured_app
        self.app = configured_app
        self.app.dependency_overrides.clear()
        self.app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(self.app)

        self.temp_dir = TemporaryDirectory(dir=os.getcwd())
        self.user_paths_patch = patch.object(
            documents,
            "Get_user_paths",
            side_effect=lambda user_id: (
                Path(self.temp_dir.name) / f"documents-user-{user_id}",
                Path(self.temp_dir.name) / f"storage-user-{user_id}",
            ),
        )
        self.user_paths_patch.start()
        self.addCleanup(self.user_paths_patch.stop)
        self.addCleanup(self.temp_dir.cleanup)
        self.ask_question_patch = patch.object(chat, "Ask_question", return_value=types.SimpleNamespace(
            answer="You haven't uploaded any documents yet. Upload a document to start asking questions.",
            answer_mode="INSUFFICIENT_CONFIDENCE",
            message=None,
            reliability="LOW",
            conflict_status="NONE",
            fallback_reason="NO_DOCUMENTS_UPLOADED",
            claims=[],
            sources=[],
        ))
        self.build_rag_patch = patch.object(documents, "Build_rag")
        self.password_patch = patch.object(auth, "verify_password", return_value=True)
        self.hash_patch = patch.object(signup, "hashed_password", return_value="hashed-password")
        self.ask_question = self.ask_question_patch.start()
        self.build_rag = self.build_rag_patch.start()
        self.verify_password = self.password_patch.start()
        self.hash_password = self.hash_patch.start()
        self.addCleanup(self.ask_question_patch.stop)
        self.addCleanup(self.build_rag_patch.stop)
        self.addCleanup(self.password_patch.stop)
        self.addCleanup(self.hash_patch.stop)
        self.addCleanup(self.app.dependency_overrides.clear)

    def _origin_headers(self, token=None, origin=FRONTEND_ORIGIN):
        headers = {"Origin": origin}
        if token is not None:
            headers["X-CSRF-Token"] = token
        return headers

    def _bootstrap(self):
        response = self.client.get("/users/csrf")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["cache-control"], "no-store")
        return response.json()["csrf_token"]

    def _login(self):
        pre_auth_token = self._bootstrap()
        response = self.client.post(
            "/users/login",
            json={"Email": self.user.Email, "Password": "password"},
            headers=self._origin_headers(pre_auth_token),
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["csrf_token"], response

    def test_missing_csrf_token_is_rejected_before_chat_logic(self):
        self._login()
        response = self.client.post(
            "/chat/query",
            json={"query": "Explain this"},
            headers=self._origin_headers(),
        )
        self.assertEqual(response.status_code, 403)
        self.ask_question.assert_not_called()

    def test_document_delete_requires_csrf_before_delete_logic(self):
        self._login()
        response = self.client.delete(
            "/documents/00000000-0000-0000-0000-000000000001",
            headers=self._origin_headers(),
        )
        self.assertEqual(response.status_code, 403)
        self.build_rag.assert_not_called()

    def test_invalid_signed_csrf_token_is_rejected_before_chat_logic(self):
        self._login()
        self.client.cookies.set("csrf_token", "not-a-signed-token")
        response = self.client.post(
            "/chat/query",
            json={"query": "Explain this"},
            headers=self._origin_headers("not-a-signed-token"),
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CSRF token is missing or invalid")
        self.ask_question.assert_not_called()

    def test_expired_csrf_token_is_rejected_before_chat_logic(self):
        self._login()
        access_token = self.client.cookies.get("access_token")
        with patch("App.csrf.time.time", return_value=1):
            expired_token = create_csrf_token(access_token=access_token)
        self.client.cookies.set("csrf_token", expired_token)
        with patch("App.csrf.time.time", return_value=3602):
            response = self.client.post(
                "/chat/query",
                json={"query": "Explain this"},
                headers=self._origin_headers(expired_token),
            )
        self.assertEqual(response.status_code, 403)
        self.ask_question.assert_not_called()

    def test_csrf_token_is_bound_to_the_current_jwt_cookie(self):
        token, _ = self._login()
        self.client.cookies.set(
            "access_token",
            oauth2.create_access_token(str(self.other_user.ID)),
        )
        response = self.client.post(
            "/chat/query",
            json={"query": "Explain this"},
            headers=self._origin_headers(token),
        )
        self.assertEqual(response.status_code, 403)
        self.ask_question.assert_not_called()

    def test_client_supplied_user_id_does_not_override_jwt_subject(self):
        self._login()
        response = self.client.get("/users/me?user_id=8&ID=8")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["ID"], self.user.ID)

    def test_unauthorized_origin_is_rejected_even_with_valid_token(self):
        token, _ = self._login()
        for origin in ("https://attacker.example", "null", "http://localhost:1234.attacker.example", "http://localhost:1234/path", None):
            with self.subTest(origin=origin):
                headers = (
                    self._origin_headers(token, origin=origin)
                    if origin
                    else {"X-CSRF-Token": token}
                )
                response = self.client.post(
                    "/chat/query",
                    json={"query": "Explain this"},
                    headers=headers,
                )
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.json()["detail"], "Request origin is not allowed")
        self.ask_question.assert_not_called()

    def test_signup_rejects_unauthorized_origin_before_database_lookup(self):
        token = self._bootstrap()
        response = self.client.post(
            "/users/signup",
            json={"Name": "New Student", "Email": "new@example.com", "Password": "password123"},
            headers=self._origin_headers(token, origin="https://attacker.example"),
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.db.execute_count, 0)

    def test_valid_csrf_and_allowed_origin_reach_chat_and_upload(self):
        token, _ = self._login()
        chat_response = self.client.post(
            "/chat/query",
            json={"query": "Explain this"},
            headers=self._origin_headers(token),
        )
        self.assertEqual(chat_response.status_code, 200)
        self.ask_question.assert_called_once_with("Explain this", self.user.ID)

        upload_response = self.client.post(
            "/documents/upload",
            files={"file": ("notes.pdf", valid_pdf_bytes(), "application/pdf")},
            headers=self._origin_headers(token),
        )
        self.assertEqual(upload_response.status_code, 201)
        self.build_rag.assert_called_once()
        self.assertEqual(self.build_rag.call_args.args, (self.user.ID,))
        self.assertEqual(len(self.build_rag.call_args.kwargs["eligible_storage_filenames"]), 1)

    def test_safe_get_does_not_require_csrf_header_or_origin(self):
        self._login()
        response = self.client.get("/users/me")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["Email"], self.user.Email)

    def test_login_and_logout_cookie_attributes_and_csrf_requirements(self):
        self.db.execute_count = 0
        missing_token_login = self.client.post(
            "/users/login",
            json={"Email": self.user.Email, "Password": "password"},
            headers={"Origin": FRONTEND_ORIGIN},
        )
        self.assertEqual(missing_token_login.status_code, 403)
        self.assertEqual(self.db.execute_count, 0)

        pre_auth_token = self._bootstrap()
        login_response = self.client.post(
            "/users/login",
            json={"Email": self.user.Email, "Password": "password"},
            headers=self._origin_headers(pre_auth_token),
        )
        self.assertEqual(login_response.status_code, 200)
        self.assertIsNotNone(self.client.cookies.get("access_token"))
        claims = jwt.decode(
            self.client.cookies.get("access_token"),
            oauth2.SECRET_KEY,
            algorithms=[oauth2.ALGORITHM],
        )
        self.assertEqual(claims["sub"], str(self.user.ID))
        self.assertNotIn("Email", claims)
        cookie_headers = login_response.headers.get_list("set-cookie")
        access_cookie = next(value.lower() for value in cookie_headers if value.startswith("access_token="))
        csrf_cookie = next(value.lower() for value in cookie_headers if value.startswith("csrf_token="))
        for cookie in (access_cookie, csrf_cookie):
            self.assertIn("path=/", cookie)
            self.assertIn("samesite=lax", cookie)
            self.assertNotIn("domain=", cookie)
            self.assertNotIn("; secure", cookie)
            self.assertIn("httponly", cookie)
        self.assertIn("max-age=3600", csrf_cookie)
        self.assertEqual(login_response.json()["csrf_token"], self.client.cookies.get("csrf_token"))

        csrf_token = login_response.json()["csrf_token"]
        logout_response = self.client.post(
            "/users/logout", headers=self._origin_headers(csrf_token)
        )
        self.assertEqual(logout_response.status_code, 200)
        delete_headers = [value.lower() for value in logout_response.headers.get_list("set-cookie")]
        self.assertEqual(len(delete_headers), 3)
        for cookie in delete_headers:
            self.assertIn("path=/", cookie)
            self.assertIn("samesite=lax", cookie)
            self.assertIn("max-age=0", cookie)

    def test_cors_preflight_allows_the_csrf_header_for_configured_origin(self):
        response = self.client.options(
            "/chat/query",
            headers={
                "Origin": FRONTEND_ORIGIN,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "x-csrf-token,content-type",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("x-csrf-token", response.headers["access-control-allow-headers"].lower())

    def test_production_cookie_defaults_to_secure_and_cannot_be_downgraded(self):
        with patch.dict(
            os.environ,
            {
                "APP_ENV": "production",
                "CORS_ALLOWED_ORIGINS": "https://learn.example.com",
                "COOKIE_SAMESITE": "lax",
                "CSRF_SECRET_KEY": TEST_SECRET,
            },
            clear=True,
        ):
            settings = get_security_settings()
            self.assertTrue(settings.cookie_secure)
            self.assertEqual(settings.cookie_samesite, "lax")

        with patch.dict(
            os.environ,
            {
                "APP_ENV": "production",
                "CORS_ALLOWED_ORIGINS": "https://learn.example.com",
                "COOKIE_SECURE": "false",
                "COOKIE_SAMESITE": "lax",
                "CSRF_SECRET_KEY": TEST_SECRET,
            },
            clear=True,
        ):
            with self.assertRaisesRegex(ValueError, "true in production"):
                get_security_settings()

        with patch.dict(
            os.environ,
            {
                "APP_ENV": "development",
                "CORS_ALLOWED_ORIGINS": FRONTEND_ORIGIN,
                "COOKIE_SECURE": "false",
                "COOKIE_SAMESITE": "none",
                "CSRF_SECRET_KEY": TEST_SECRET,
            },
            clear=True,
        ):
            with self.assertRaisesRegex(ValueError, "COOKIE_SECURE must be true"):
                get_security_settings()

    def test_security_configuration_rejects_missing_short_placeholder_and_reused_secrets(self):
        base = {
            "APP_ENV": "test",
            "CORS_ALLOWED_ORIGINS": FRONTEND_ORIGIN,
            "COOKIE_SECURE": "false",
        }
        cases = [
            ({}, "CSRF_SECRET_KEY must be configured"),
            ({"CSRF_SECRET_KEY": "short"}, "at least 32 bytes"),
            ({"CSRF_SECRET_KEY": "replace-with-" + "x" * 40}, "placeholder"),
            ({"CSRF_SECRET_KEY": TEST_SECRET, "SECRET_KEY": TEST_SECRET}, "different from SECRET_KEY"),
        ]
        for values, message in cases:
            with self.subTest(values=list(values)):
                with patch.dict(os.environ, {**base, **values}, clear=True):
                    with self.assertRaisesRegex(ValueError, message):
                        get_security_settings()

    def test_security_configuration_rejects_predictable_secret_patterns(self):
        base = {
            "APP_ENV": "test",
            "CORS_ALLOWED_ORIGINS": FRONTEND_ORIGIN,
            "SECRET_KEY": "a-separate-jwt-signing-key-value",
        }
        weak_values = [
            "your_secret_key_here_" + "x" * 20,
            "password" + "x" * 24,
            "a" * 32,
            "!" * 32,
            " " * 32,
            "abc123" * 6,
            "0123456789abcdef" * 2,
            "0-1-2-3-4-5-6-7-8-9-0-1-2-3-4-5-6-7-8-9-0-1-2-3-4-5-6-7-8-9",
            "hgfedcba" + "z" * 24,
        ]
        for value in weak_values:
            with self.subTest(secret=value[:16]):
                with patch.dict(
                    os.environ,
                    {**base, "CSRF_SECRET_KEY": value},
                    clear=True,
                ):
                    with self.assertRaisesRegex(ValueError, "placeholder or predictable"):
                        get_security_settings()

    def test_cryptographically_generated_secret_is_accepted(self):
        generated_secret = secrets.token_urlsafe(32)
        with patch.dict(
            os.environ,
            {
                "APP_ENV": "test",
                "CSRF_SECRET_KEY": generated_secret,
                "SECRET_KEY": "a-separate-jwt-signing-key-value",
                "CORS_ALLOWED_ORIGINS": FRONTEND_ORIGIN,
            },
            clear=True,
        ):
            self.assertEqual(get_security_settings().csrf_secret_key, generated_secret)

    def test_app_env_must_be_explicit_and_production_requires_explicit_origins(self):
        with patch.dict(os.environ, {"CSRF_SECRET_KEY": TEST_SECRET}, clear=True):
            with self.assertRaisesRegex(ValueError, "APP_ENV must be explicitly configured"):
                get_security_settings()
        with patch.dict(os.environ, {
            "APP_ENV": "production", "CSRF_SECRET_KEY": TEST_SECRET,
            "SECRET_KEY": "different-jwt-secret-value",
        }, clear=True):
            with self.assertRaisesRegex(ValueError, "CORS_ALLOWED_ORIGINS"):
                get_security_settings()

    def test_bootstrap_reuses_valid_token_and_pre_auth_binding_is_client_specific(self):
        first = self._bootstrap()
        initial_set_cookie = self.client.get("/users/csrf").headers.get_list("set-cookie")
        self.assertEqual(self.client.cookies.get("csrf_token"), first)
        self.assertFalse(any(value.startswith("csrf_token=") for value in initial_set_cookie))

        other_client = TestClient(self.app)
        other_token = other_client.get("/users/csrf").json()["csrf_token"]
        self.assertNotEqual(first, other_token)
        other_client.cookies.set("csrf_token", first)
        response = other_client.post(
            "/users/login",
            json={"Email": self.user.Email, "Password": "password"},
            headers=self._origin_headers(first),
        )
        self.assertEqual(response.status_code, 403)
        self.verify_password.assert_not_called()

    def test_pre_auth_token_cannot_authorize_authenticated_unsafe_request_after_login(self):
        pre_auth_token = self._bootstrap()
        authenticated_token, _ = self._login()
        self.client.cookies.set("csrf_token", pre_auth_token)
        response = self.client.post(
            "/chat/query", json={"query": "Explain this"},
            headers=self._origin_headers(pre_auth_token),
        )
        self.assertEqual(response.status_code, 403)
        self.assertNotEqual(pre_auth_token, authenticated_token)
        self.ask_question.assert_not_called()

    def test_authenticated_unsafe_route_without_csrf_configuration_fails_closed(self):
        from starlette.requests import Request

        configured_settings = self.app.state.csrf_settings
        delattr(self.app.state, "csrf_settings")
        valid_jwt = oauth2.create_access_token(str(self.user.ID))
        try:
            with patch.dict(os.environ, {"APP_ENV": "test", "SECRET_KEY": oauth2.SECRET_KEY,
                                        "CSRF_SECRET_KEY": "", "CORS_ALLOWED_ORIGINS": FRONTEND_ORIGIN}):
                request = Request({
                    "type": "http", "http_version": "1.1", "method": "POST",
                    "scheme": "http", "path": "/chat/query", "raw_path": b"/chat/query",
                    "query_string": b"", "headers": [
                        (b"origin", FRONTEND_ORIGIN.encode()),
                        (b"x-csrf-token", b"x"),
                    ], "server": ("testserver", 80), "client": ("testclient", 50000),
                    "root_path": "", "app": self.app,
                })
                with self.assertRaises(HTTPException) as authenticated_error:
                    oauth2.get_current_user(request, valid_jwt, self.db)
                with self.assertRaises(HTTPException) as anonymous_error:
                    oauth2.get_current_user(request, None, self.db)
            self.assertEqual(authenticated_error.exception.status_code, 503)
            self.assertEqual(authenticated_error.exception.detail, "CSRF protection is unavailable")
            self.assertEqual(anonymous_error.exception.status_code, 401)
            self.ask_question.assert_not_called()
        finally:
            self.app.state.csrf_settings = configured_settings

    def test_production_csrf_cookie_is_secure(self):
        from fastapi import Response
        with patch.dict(os.environ, {
            "APP_ENV": "production", "CSRF_SECRET_KEY": TEST_SECRET,
            "SECRET_KEY": "separate-jwt-secret-value", "CORS_ALLOWED_ORIGINS": "https://learn.example.com",
        }, clear=True):
            settings = get_security_settings()
        response = Response()
        from App.csrf import set_csrf_cookie
        set_csrf_cookie(response, "signed-token", settings)
        cookie = response.headers["set-cookie"].lower()
        self.assertIn("secure", cookie)
        self.assertIn("httponly", cookie)
        self.assertIn("samesite=lax", cookie)


if __name__ == "__main__":
    unittest.main()
