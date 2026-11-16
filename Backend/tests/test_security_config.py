import os
import secrets
import unittest
from unittest.mock import patch

from fastapi import FastAPI

from App.config import get_jwt_settings, get_security_settings, get_upload_settings
from App.csrf import configure_csrf_protection


TEST_JWT_SECRET = secrets.token_urlsafe(32)
TEST_CSRF_SECRET = secrets.token_urlsafe(32)
TEST_ORIGIN = "http://localhost:1234"


def test_environment(**overrides):
    values = {
        "APP_ENV": "test",
        "SECRET_KEY": TEST_JWT_SECRET,
        "ALGORITHM": "HS256",
        "ACCESS_TOKEN_EXPIRE_MINUTES": "30",
        "CSRF_SECRET_KEY": TEST_CSRF_SECRET,
        "CSRF_TOKEN_TTL_SECONDS": "3600",
        "COOKIE_SECURE": "false",
        "COOKIE_SAMESITE": "lax",
        "CORS_ALLOWED_ORIGINS": TEST_ORIGIN,
    }
    values.update(overrides)
    return patch.dict(os.environ, values, clear=True)


class JwtConfigurationTests(unittest.TestCase):
    def test_missing_short_and_placeholder_jwt_secrets_are_rejected(self):
        for value, message in (
            (None, "SECRET_KEY must be configured"),
            ("short", "at least 32 bytes"),
            ("replace-with-a-random-jwt-secret-of-at-least-32-bytes", "placeholder"),
            ("a" * 40, "placeholder or predictable"),
            ("0123456789abcdef" * 3, "placeholder or predictable"),
        ):
            with self.subTest(has_secret=value is not None):
                overrides = {"SECRET_KEY": "" if value is None else value}
                with test_environment(**overrides):
                    with self.assertRaisesRegex(ValueError, message):
                        get_jwt_settings()

    def test_generated_jwt_secret_is_accepted(self):
        generated_secret = secrets.token_urlsafe(32)
        with test_environment(SECRET_KEY=generated_secret):
            settings = get_jwt_settings()
        self.assertEqual(settings.secret_key, generated_secret)
        self.assertEqual(settings.algorithm, "HS256")
        self.assertEqual(settings.access_token_expire_minutes, 30)

    def test_unsupported_jwt_algorithms_are_rejected(self):
        for algorithm in ("none", "RS256", "HS1024", ""):
            with self.subTest(algorithm=algorithm):
                with test_environment(ALGORITHM=algorithm):
                    with self.assertRaisesRegex(ValueError, "ALGORITHM must be one of"):
                        get_jwt_settings()

    def test_invalid_and_unsafe_jwt_expirations_are_rejected(self):
        for value in ("", "abc", "0", "-1", "1441"):
            with self.subTest(value=value):
                with test_environment(ACCESS_TOKEN_EXPIRE_MINUTES=value):
                    with self.assertRaisesRegex(ValueError, "ACCESS_TOKEN_EXPIRE_MINUTES"):
                        get_jwt_settings()


class ApplicationSecurityConfigurationTests(unittest.TestCase):
    def test_upload_limits_have_safe_defaults_and_reject_invalid_values(self):
        with patch.dict(os.environ, {}, clear=True):
            settings = get_upload_settings()
        self.assertEqual(settings.max_pdf_upload_size_bytes, 20 * 1024 * 1024)
        self.assertEqual(settings.max_pdf_page_count, 250)
        self.assertEqual(settings.max_user_pdf_storage_bytes, 200 * 1024 * 1024)

        for name in (
            "MAX_PDF_UPLOAD_SIZE_BYTES",
            "MAX_PDF_PAGE_COUNT",
            "MAX_USER_PDF_STORAGE_BYTES",
        ):
            for value in ("", "invalid", "0", "-1"):
                with self.subTest(setting=name, value=value):
                    with patch.dict(os.environ, {name: value}, clear=True):
                        with self.assertRaisesRegex(ValueError, f"{name} must be a positive integer"):
                            get_upload_settings()

    def test_missing_weak_and_reused_csrf_secrets_are_rejected(self):
        cases = (
            ({"CSRF_SECRET_KEY": ""}, "CSRF_SECRET_KEY must be configured"),
            ({"CSRF_SECRET_KEY": "short"}, "at least 32 bytes"),
            ({"CSRF_SECRET_KEY": "replace-with-a-random-csrf-secret-of-at-least-32-bytes"}, "placeholder"),
            ({"CSRF_SECRET_KEY": TEST_JWT_SECRET}, "different from SECRET_KEY"),
        )
        for overrides, message in cases:
            with self.subTest(setting=next(iter(overrides))):
                with test_environment(**overrides):
                    with self.assertRaisesRegex(ValueError, message):
                        get_security_settings()

    def test_invalid_environment_and_csrf_ttl_are_rejected(self):
        with test_environment(APP_ENV="staging"):
            with self.assertRaisesRegex(ValueError, "APP_ENV must be development, test, or production"):
                get_security_settings()

        for value in ("abc", "0", "604801"):
            with self.subTest(csrf_ttl=value):
                with test_environment(CSRF_TOKEN_TTL_SECONDS=value):
                    with self.assertRaisesRegex(ValueError, "CSRF_TOKEN_TTL_SECONDS"):
                        get_security_settings()

    def test_production_requires_valid_explicit_https_origins(self):
        cases = (
            ("", "CORS_ALLOWED_ORIGINS must be configured in production"),
            ("*", "must contain explicit origins"),
            ("https://*.example.com", "must contain explicit origins"),
            ("not a URL", "must be exact origins"),
            ("http://learn.example.com", "must use HTTPS"),
        )
        for origins, message in cases:
            with self.subTest(origin_configured=bool(origins)):
                with test_environment(
                    APP_ENV="production",
                    CORS_ALLOWED_ORIGINS=origins,
                    COOKIE_SECURE="true",
                ):
                    with self.assertRaisesRegex(ValueError, message):
                        get_security_settings()

    def test_production_rejects_insecure_cookie_and_samesite_none_without_secure(self):
        with test_environment(
            APP_ENV="production",
            CORS_ALLOWED_ORIGINS="https://learn.example.com",
            COOKIE_SECURE="false",
        ):
            with self.assertRaisesRegex(ValueError, "true in production"):
                get_security_settings()

        with test_environment(
            APP_ENV="development",
            COOKIE_SECURE="false",
            COOKIE_SAMESITE="none",
        ):
            with self.assertRaisesRegex(ValueError, "true when COOKIE_SAMESITE is none"):
                get_security_settings()

        with test_environment(COOKIE_SAMESITE="sometimes"):
            with self.assertRaisesRegex(ValueError, "COOKIE_SAMESITE must be lax, strict, or none"):
                get_security_settings()

        with test_environment(COOKIE_SECURE="occasionally"):
            with self.assertRaisesRegex(ValueError, "COOKIE_SECURE must be a boolean value"):
                get_security_settings()

    def test_development_configuration_remains_usable(self):
        with test_environment():
            jwt_settings = get_jwt_settings()
            security_settings = get_security_settings()
        self.assertEqual(jwt_settings.algorithm, "HS256")
        self.assertFalse(security_settings.cookie_secure)
        self.assertEqual(security_settings.cors_allowed_origins, (TEST_ORIGIN,))

    def test_production_requires_provider_key_before_router_initialization(self):
        for provider_key in ("", "REPLACE_WITH_YOUR_PROVIDER_KEY"):
            with self.subTest(key_is_empty=not provider_key):
                with test_environment(
                    APP_ENV="production",
                    CORS_ALLOWED_ORIGINS="https://learn.example.com",
                    COOKIE_SECURE="true",
                    LLM_API_KEY=provider_key,
                ):
                    with self.assertRaisesRegex(ValueError, "LLM_API_KEY must contain a configured provider key"):
                        configure_csrf_protection(FastAPI())


if __name__ == "__main__":
    unittest.main()
