"""Small process-local rate limiter for the single-worker deployment."""
from collections import OrderedDict
from ipaddress import ip_address
import math
import os
import threading
import time

from fastapi import Depends, HTTPException, Request

from .oauth2 import get_current_user


DEFAULT_POLICIES = {
    "login": (10, 15 * 60),
    "signup": (5, 60 * 60),
    "upload": (5, 60 * 60),
    "chat": (20, 60),
}


def _positive_int(name, default, maximum=2**31 - 1):
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be a positive integer") from error
    if not 1 <= value <= maximum:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _env_bool(name, default):
    raw = os.getenv(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value not in {"true", "false", "1", "0", "yes", "no"}:
        raise ValueError(f"{name} must be a boolean")
    return value in {"true", "1", "yes"}


def get_rate_limit_settings():
    environment = os.getenv("APP_ENV", "development").strip().lower()
    enabled = _env_bool("RATE_LIMIT_ENABLED", environment != "test")
    trust_cf = _env_bool("RATE_LIMIT_TRUST_CF_CONNECTING_IP", False)
    if environment == "production" and enabled and not trust_cf:
        raise ValueError(
            "RATE_LIMIT_TRUST_CF_CONNECTING_IP must be true in production on Render"
        )
    policies = {}
    for action, (default_count, default_window) in DEFAULT_POLICIES.items():
        policies[action] = (
            _positive_int(f"RATE_LIMIT_{action.upper()}_REQUESTS", default_count),
            _positive_int(f"RATE_LIMIT_{action.upper()}_WINDOW_SECONDS", default_window),
        )
    max_buckets = _positive_int("RATE_LIMIT_MAX_BUCKETS", 20_000, 1_000_000)
    return enabled, trust_cf, policies, max_buckets


class InMemoryRateLimiter:
    """Thread-safe fixed-window limits with bounded, periodically cleaned state."""

    def __init__(self, max_buckets=20_000, cleanup_every=128, clock=time.monotonic):
        self.max_buckets = max_buckets
        self.cleanup_every = cleanup_every
        self.clock = clock
        self._buckets = OrderedDict()
        self._lock = threading.Lock()
        self._request_count = 0

    @property
    def bucket_count(self):
        with self._lock:
            return len(self._buckets)

    def clear(self):
        with self._lock:
            self._buckets.clear()
            self._request_count = 0

    def set_max_buckets(self, value):
        if value < 1:
            raise ValueError("max_buckets must be positive")
        with self._lock:
            self.max_buckets = value
            self._cleanup(self.clock())

    def _cleanup(self, now):
        expired = [key for key, (_started, _count, expires_at) in self._buckets.items()
                   if expires_at <= now]
        for key in expired:
            self._buckets.pop(key, None)

    def check(self, scope, identity, limit, window_seconds):
        now = self.clock()
        key = (scope, str(identity))
        with self._lock:
            self._request_count += 1
            if (self._request_count % self.cleanup_every == 0
                    or len(self._buckets) >= self.max_buckets):
                self._cleanup(now)

            bucket = self._buckets.get(key)
            if bucket is None:
                if len(self._buckets) >= self.max_buckets:
                    retry_after = max(
                        1,
                        math.ceil(min(item[2] for item in self._buckets.values()) - now),
                    )
                    self._raise_limited(retry_after, "Rate limiter is at capacity")
                started, count = now, 1
                expires_at = now + window_seconds
                self._buckets[key] = (started, count, expires_at)
                return

            started, count, expires_at = bucket
            if expires_at <= now:
                self._buckets[key] = (now, 1, now + window_seconds)
                self._buckets.move_to_end(key)
                return
            if count >= limit:
                self._raise_limited(max(1, math.ceil(expires_at - now)))
            self._buckets[key] = (started, count + 1, expires_at)
            self._buckets.move_to_end(key)

    @staticmethod
    def _raise_limited(retry_after, detail="Too many requests. Please retry later."):
        raise HTTPException(
            status_code=429,
            detail=detail,
            headers={"Retry-After": str(retry_after)},
        )


limiter = InMemoryRateLimiter()


def client_ip(request: Request, trust_cf_connecting_ip=False) -> str:
    """Use Render's Cloudflare-overwritten visitor header only when explicitly trusted.

    Never inspect X-Forwarded-For: callers can supply or prepend values there.
    """
    if trust_cf_connecting_ip:
        forwarded = request.headers.get("cf-connecting-ip", "").strip()
        if forwarded:
            try:
                return ip_address(forwarded).compressed
            except ValueError:
                pass
    client = request.client
    return client.host if client and client.host else "unknown-client"


def _enforce(request, action, identity, scope):
    enabled, trust_cf, policies, max_buckets = get_rate_limit_settings()
    if not enabled:
        return
    limiter.set_max_buckets(max_buckets)
    limit, window = policies[action]
    if scope == "ip":
        identity = client_ip(request, trust_cf)
    limiter.check(f"{action}:{scope}", identity, limit, window)


def ip_rate_limit(action):
    async def dependency(request: Request):
        _enforce(request, action, None, "ip")
    dependency.rate_limit_action = action
    dependency.rate_limit_scope = "ip"
    return dependency


def user_rate_limit(action):
    async def dependency(request: Request, current_user=Depends(get_current_user)):
        _enforce(request, action, current_user.ID, "user")
    dependency.rate_limit_action = action
    dependency.rate_limit_scope = "user"
    return dependency


def validate_rate_limit_configuration():
    get_rate_limit_settings()


__all__ = [
    "InMemoryRateLimiter", "client_ip", "get_rate_limit_settings",
    "ip_rate_limit", "limiter", "user_rate_limit", "validate_rate_limit_configuration",
]
