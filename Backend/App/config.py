import os
import hmac
from dataclasses import dataclass
from urllib.parse import urlsplit
from dotenv import load_dotenv

load_dotenv()

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
    "replace-me",
    "replace_me",
    "replace-with-a-dedicated-random-secret-of-at-least-32-bytes",
    "placeholder",
}

_PLACEHOLDER_PREFIXES = (
    "replace-with-",
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
    if not origins or "*" in origins:
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
    if csrf_token_ttl_seconds <= 0:
        raise ValueError("CSRF_TOKEN_TTL_SECONDS must be a positive integer")

    return SecuritySettings(
        environment=environment,
        csrf_secret_key=csrf_secret_key,
        csrf_token_ttl_seconds=csrf_token_ttl_seconds,
        cors_allowed_origins=origins,
        cookie_secure=cookie_secure,
        cookie_samesite=cookie_samesite,
        cookie_domain=os.getenv("COOKIE_DOMAIN") or None,
    )
