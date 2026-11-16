import os
import hmac
from dataclasses import dataclass
from urllib.parse import urlsplit
from dotenv import load_dotenv

load_dotenv()

SUPPORTED_JWT_ALGORITHMS = frozenset({"HS256", "HS384", "HS512"})
MAX_ACCESS_TOKEN_EXPIRE_MINUTES = 24 * 60
MAX_CSRF_TOKEN_TTL_SECONDS = 7 * 24 * 60 * 60
DEFAULT_MAX_PDF_UPLOAD_SIZE_BYTES = 20 * 1024 * 1024
DEFAULT_MAX_PDF_PAGE_COUNT = 250
DEFAULT_MAX_USER_PDF_STORAGE_BYTES = 200 * 1024 * 1024

_PLACEHOLDER_SECRETS = {
    "changeme",
    "change-me",
    "change_me",
    "secret",
    "secret-key",
    "secret_key",
    "password",
    "default-secret",
    "development-secret",
    "example-secret",
    "test-secret",
    "sample-secret",
    "your-secret-key",
    "your-secret-key-here",
    "your_csrf_secret_key",
    "your_jwt_secret_key",
    "development",
    "development-secret-key",
    "dev-secret",
    "insecure-secret",
    "jwt-secret",
    "jwt_secret",
    "local-secret",
    "test",
    "testing",
    "replace-me",
    "replace_me",
    "replace-with-a-dedicated-random-secret-of-at-least-32-bytes",
    "placeholder",
}

_PLACEHOLDER_PREFIXES = (
    "replace-with-",
    "replace_with_",
    "replace-with_",
    "replace-me",
    "replace_me",
    "your-",
    "your_",
    "placeholder-",
    "placeholder_",
    "change-this",
    "change-this-",
    "change_this",
    "password",
    "dev-secret",
    "test-secret",
    "sample-secret",
)

def _is_predictable_secret(secret: str) -> bool:
    raw_normalized = secret.lower()
    normalized = secret.strip().lower()
    if normalized in _PLACEHOLDER_SECRETS or normalized.startswith(_PLACEHOLDER_PREFIXES):
        return True

    compact = "".join(character for character in normalized if character.isalnum())
    if len(raw_normalized) >= 2 and len(set(raw_normalized)) == 1:
        return True

    for value in {raw_normalized, normalized, compact}:
        for pattern_length in range(1, min(17, len(value))):
            if len(value) % pattern_length == 0:
                pattern = value[:pattern_length]
                if pattern * (len(value) // pattern_length) == value:
                    return True

    for value in (normalized, compact):
        for alphabet in ("0123456789", "abcdefghijklmnopqrstuvwxyz"):
            for index in range(len(alphabet) - 7):
                ascending = alphabet[index:index + 8]
                descending = ascending[::-1]
                if ascending in value or descending in value:
                    return True
    return False

@dataclass(frozen=True)
class SecuritySettings:
    environment: str
    csrf_secret_key: str
    csrf_token_ttl_seconds: int
    cors_allowed_origins: tuple[str, ...]
    cookie_secure: bool
    cookie_samesite: str
    cookie_domain: str | None
    cookie_path: str = "/"


@dataclass(frozen=True)
class JwtSettings:
    secret_key: str
    algorithm: str
    access_token_expire_minutes: int


@dataclass(frozen=True)
class UploadSettings:
    max_pdf_upload_size_bytes: int
    max_pdf_page_count: int
    max_user_pdf_storage_bytes: int


def _positive_integer_setting(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be a positive integer") from error
    if not 1 <= parsed <= 2**63 - 1:
        raise ValueError(f"{name} must be a positive integer")
    return parsed


def get_upload_settings() -> UploadSettings:
    return UploadSettings(
        max_pdf_upload_size_bytes=_positive_integer_setting(
            "MAX_PDF_UPLOAD_SIZE_BYTES", DEFAULT_MAX_PDF_UPLOAD_SIZE_BYTES
        ),
        max_pdf_page_count=_positive_integer_setting(
            "MAX_PDF_PAGE_COUNT", DEFAULT_MAX_PDF_PAGE_COUNT
        ),
        max_user_pdf_storage_bytes=_positive_integer_setting(
            "MAX_USER_PDF_STORAGE_BYTES", DEFAULT_MAX_USER_PDF_STORAGE_BYTES
        ),
    )


def get_jwt_settings() -> JwtSettings:
    secret_key = os.getenv("SECRET_KEY", "")
    if not secret_key:
        raise ValueError("SECRET_KEY must be configured")
    if len(secret_key.encode("utf-8")) < 32:
        raise ValueError("SECRET_KEY must contain at least 32 bytes")
    if _is_predictable_secret(secret_key):
        raise ValueError("SECRET_KEY must not be a placeholder or predictable value")

    algorithm = os.getenv("ALGORITHM", "")
    if algorithm not in SUPPORTED_JWT_ALGORITHMS:
        supported = ", ".join(sorted(SUPPORTED_JWT_ALGORITHMS))
        raise ValueError(f"ALGORITHM must be one of the supported values: {supported}")

    ttl_value = os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "")
    try:
        expire_minutes = int(ttl_value)
    except (TypeError, ValueError) as error:
        raise ValueError("ACCESS_TOKEN_EXPIRE_MINUTES must be an integer from 1 to 1440") from error
    if not 1 <= expire_minutes <= MAX_ACCESS_TOKEN_EXPIRE_MINUTES:
        raise ValueError("ACCESS_TOKEN_EXPIRE_MINUTES must be an integer from 1 to 1440")

    return JwtSettings(secret_key, algorithm, expire_minutes)

def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized not in {"true", "false", "1", "0", "yes", "no"}:
        raise ValueError(f"{name} must be a boolean value")
    return normalized in {"true", "1", "yes"}

def get_security_settings() -> SecuritySettings:
    environment_value = os.getenv("APP_ENV")
    if not environment_value or not environment_value.strip():
        raise ValueError("APP_ENV must be explicitly configured")
    environment = environment_value.strip().lower()
    if environment not in {"development", "test", "production"}:
        raise ValueError("APP_ENV must be development, test, or production")
    production = environment == "production"

    csrf_secret_key = os.getenv("CSRF_SECRET_KEY", "")
    if not csrf_secret_key:
        raise ValueError("CSRF_SECRET_KEY must be configured")
    encoded_secret = csrf_secret_key.encode("utf-8")
    if len(encoded_secret) < 32:
        raise ValueError("CSRF_SECRET_KEY must contain at least 32 bytes")
    if _is_predictable_secret(csrf_secret_key):
        raise ValueError("CSRF_SECRET_KEY must not be a placeholder or predictable value")
    jwt_secret = os.getenv("SECRET_KEY", "")
    if jwt_secret and hmac.compare_digest(encoded_secret, jwt_secret.encode("utf-8")):
        raise ValueError("CSRF_SECRET_KEY must be different from SECRET_KEY")

    origins_value = os.getenv("CORS_ALLOWED_ORIGINS")
    if not origins_value and production:
        raise ValueError("CORS_ALLOWED_ORIGINS must be configured in production")
    origins = tuple(
        origin.strip()
        for origin in (origins_value or "http://localhost:1234").split(",")
        if origin.strip()
    )
    if not origins or any("*" in origin for origin in origins):
        raise ValueError("CORS_ALLOWED_ORIGINS must contain explicit origins")
    for origin in origins:
        parsed_origin = urlsplit(origin)
        if (
            parsed_origin.scheme not in {"http", "https"}
            or not parsed_origin.hostname
            or parsed_origin.username is not None
            or parsed_origin.password is not None
            or parsed_origin.path
            or parsed_origin.query
            or parsed_origin.fragment
            or origin != f"{parsed_origin.scheme}://{parsed_origin.netloc}"
        ):
            raise ValueError("CORS_ALLOWED_ORIGINS entries must be exact origins without paths")
        if production and parsed_origin.scheme != "https":
            raise ValueError("Production CORS_ALLOWED_ORIGINS entries must use HTTPS")

    cookie_secure = _env_bool("COOKIE_SECURE", production)
    if production and not cookie_secure:
        raise ValueError("COOKIE_SECURE must be true in production")
    cookie_samesite = os.getenv("COOKIE_SAMESITE", "lax").strip().lower()
    if cookie_samesite not in {"lax", "strict", "none"}:
        raise ValueError("COOKIE_SAMESITE must be lax, strict, or none")
    if cookie_samesite == "none" and not cookie_secure:
        raise ValueError("COOKIE_SECURE must be true when COOKIE_SAMESITE is none")

    ttl_value = os.getenv("CSRF_TOKEN_TTL_SECONDS", "3600")
    try:
        csrf_token_ttl_seconds = int(ttl_value)
    except ValueError as error:
        raise ValueError("CSRF_TOKEN_TTL_SECONDS must be a positive integer") from error
    if not 1 <= csrf_token_ttl_seconds <= MAX_CSRF_TOKEN_TTL_SECONDS:
        raise ValueError("CSRF_TOKEN_TTL_SECONDS must be an integer from 1 to 604800")

    return SecuritySettings(
        environment=environment,
        csrf_secret_key=csrf_secret_key,
        csrf_token_ttl_seconds=csrf_token_ttl_seconds,
        cors_allowed_origins=origins,
        cookie_secure=cookie_secure,
        cookie_samesite=cookie_samesite,
        cookie_domain=os.getenv("COOKIE_DOMAIN") or None,
    )


def validate_production_configuration(settings: SecuritySettings) -> None:
    if settings.environment != "production":
        return

    provider_key = os.getenv("LLM_API_KEY", "").strip()
    placeholder_prefixes = (
        "replace-with",
        "replace_with",
        "your-api-key",
        "your_api_key",
        "placeholder",
    )
    if not provider_key or provider_key.lower().startswith(placeholder_prefixes):
        raise ValueError("LLM_API_KEY must contain a configured provider key in production")
