import base64
import binascii
import hashlib
import hmac
import json
import secrets
import time
from fastapi import HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from .config import SecuritySettings, get_security_settings

CSRF_COOKIE_NAME = "csrf_token"
PREAUTH_COOKIE_NAME = "csrf_pre_session"
CSRF_HEADER_NAME = "X-CSRF-Token"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")

def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))

def _session_binding(access_token: str | None, preauth_session: str | None = None) -> str:
    if access_token:
        context = "authenticated:" + access_token
    elif preauth_session:
        context = "preauth:" + preauth_session
    else:
        raise ValueError("A CSRF session binding is required")
    return hashlib.sha256(context.encode("utf-8")).hexdigest()

def create_csrf_token(
    access_token: str | None = None,
    settings: SecuritySettings | None = None,
    preauth_session: str | None = None,
) -> str:
    settings = settings or get_security_settings()
    payload = _b64encode(
        json.dumps(
            {
                "iat": int(time.time()),
                "nonce": secrets.token_urlsafe(24),
                "session": _session_binding(access_token, preauth_session),
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    )
    signature = hmac.new(
        settings.csrf_secret_key.encode("utf-8"), payload.encode("ascii"), hashlib.sha256
    ).digest()
    return f"{payload}.{_b64encode(signature)}"

def set_csrf_cookie(response: Response, token: str, settings: SecuritySettings | None = None) -> None:
    settings = settings or get_security_settings()
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=token,
        max_age=settings.csrf_token_ttl_seconds,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        domain=settings.cookie_domain,
        path=settings.cookie_path,
    )

def issue_csrf_token(
    response: Response,
    access_token: str | None,
    settings: SecuritySettings | None = None,
    preauth_session: str | None = None,
) -> str:
    settings = settings or get_security_settings()
    token = create_csrf_token(access_token, settings, preauth_session)
    set_csrf_cookie(response, token, settings)
    return token

def _validate_token(token: str, request: Request, settings: SecuritySettings) -> None:
    payload_part, signature_part = token.split(".", 1)
    signature = _b64decode(signature_part)
    expected_signature = hmac.new(
        settings.csrf_secret_key.encode("utf-8"), payload_part.encode("ascii"), hashlib.sha256
    ).digest()
    if not hmac.compare_digest(signature, expected_signature):
        raise ValueError("Invalid signature")
    payload = json.loads(_b64decode(payload_part))
    issued_at = int(payload["iat"])
    age = int(time.time()) - issued_at
    if age < 0 or age > settings.csrf_token_ttl_seconds:
        raise ValueError("Expired token")
    expected_session = _session_binding(
        request.cookies.get("access_token"), request.cookies.get(PREAUTH_COOKIE_NAME)
    )
    if not hmac.compare_digest(str(payload["session"]), expected_session):
        raise ValueError("Wrong session")
    if not payload.get("nonce"):
        raise ValueError("Missing nonce")

def token_is_valid(token: str | None, request: Request, settings: SecuritySettings) -> bool:
    if not token:
        return False
    try:
        _validate_token(token, request, settings)
        return True
    except (
        ValueError,
        TypeError,
        KeyError,
        json.JSONDecodeError,
        UnicodeDecodeError,
        UnicodeEncodeError,
        binascii.Error,
    ):
        return False

def validate_csrf_request(request: Request, settings: SecuritySettings | None = None) -> None:
    if request.method.upper() in SAFE_METHODS:
        return
    try:
        settings = settings or get_security_settings()
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="CSRF protection is unavailable",
        )

    origin = request.headers.get("origin")
    if origin not in settings.cors_allowed_origins:
        raise HTTPException(status_code=403, detail="Request origin is not allowed")

    cookie_token = request.cookies.get(CSRF_COOKIE_NAME)
    header_token = request.headers.get(CSRF_HEADER_NAME)
    try:
        tokens_match = bool(cookie_token and header_token) and hmac.compare_digest(
            cookie_token.encode("utf-8"), header_token.encode("utf-8")
        )
    except UnicodeEncodeError:
        tokens_match = False
    if not tokens_match or not token_is_valid(cookie_token, request, settings):
        raise HTTPException(status_code=403, detail="CSRF token is missing or invalid")

def require_csrf(request: Request) -> None:
    validate_csrf_request(request, settings=getattr(request.app.state, "csrf_settings", None))

def configure_csrf_protection(app) -> SecuritySettings:
    settings = get_security_settings()
    app.state.csrf_settings = settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_allowed_origins),
        allow_credentials=True,
        allow_methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Accept", CSRF_HEADER_NAME],
    )
    return settings
