import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.testclient import TestClient

from App.oauth2 import get_current_user
from App.Routers import auth, chat, documents, signup
from App.rate_limit import (
    InMemoryRateLimiter,
    client_ip,
    ip_rate_limit,
    user_rate_limit,
)


class RateLimiterTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {
            "APP_ENV": "test",
            "RATE_LIMIT_ENABLED": "true",
            "RATE_LIMIT_TRUST_CF_CONNECTING_IP": "true",
            "RATE_LIMIT_MAX_BUCKETS": "20",
            "RATE_LIMIT_LOGIN_REQUESTS": "2",
            "RATE_LIMIT_LOGIN_WINDOW_SECONDS": "60",
            "RATE_LIMIT_SIGNUP_REQUESTS": "2",
            "RATE_LIMIT_SIGNUP_WINDOW_SECONDS": "60",
            "RATE_LIMIT_UPLOAD_REQUESTS": "2",
            "RATE_LIMIT_UPLOAD_WINDOW_SECONDS": "60",
            "RATE_LIMIT_CHAT_REQUESTS": "1",
            "RATE_LIMIT_CHAT_WINDOW_SECONDS": "60",
        })
        self.environment.start()
        self.addCleanup(self.environment.stop)
        from App import rate_limit
        self.original_limiter = rate_limit.limiter
        rate_limit.limiter = InMemoryRateLimiter(max_buckets=20)
        self.addCleanup(setattr, rate_limit, "limiter", self.original_limiter)
        self.app = FastAPI()
        router = APIRouter()

        @router.post("/ip", dependencies=[Depends(ip_rate_limit("login"))])
        def ip_limited():
            return {"ok": True}

        @router.post("/user", dependencies=[Depends(user_rate_limit("chat"))])
        def user_limited():
            return {"ok": True}

        @router.get("/client-ip")
        def reported_client_ip(request: Request):
            return {"ip": client_ip(request, trust_cf_connecting_ip=True)}

        self.app.include_router(router)

        def authenticated_user(request: Request):
            import types
            return types.SimpleNamespace(ID=int(request.headers.get("X-Test-User", "1")))

        self.app.dependency_overrides[get_current_user] = authenticated_user
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)

    def test_ip_limit_allows_requests_then_returns_429_and_retry_after(self):
        headers = {"CF-Connecting-IP": "203.0.113.10"}
        self.assertEqual(self.client.post("/ip", headers=headers).status_code, 200)
        self.assertEqual(self.client.post("/ip", headers=headers).status_code, 200)
        response = self.client.post("/ip", headers=headers)
        self.assertEqual(response.status_code, 429)
        self.assertGreaterEqual(int(response.headers["Retry-After"]), 1)
        self.assertLessEqual(int(response.headers["Retry-After"]), 60)

    def test_ip_limits_are_independent_and_untrusted_xff_is_ignored(self):
        first = {"CF-Connecting-IP": "203.0.113.11"}
        second = {"CF-Connecting-IP": "203.0.113.12"}
        self.assertEqual(self.client.post("/ip", headers=first).status_code, 200)
        self.assertEqual(self.client.post("/ip", headers=second).status_code, 200)
        self.assertEqual(self.client.get(
            "/client-ip", headers={"X-Forwarded-For": "198.51.100.200"}
        ).json()["ip"], "testclient")

    def test_authenticated_limits_are_user_scoped(self):
        self.assertEqual(self.client.post("/user", headers={"X-Test-User": "10"}).status_code, 200)
        limited = self.client.post("/user", headers={"X-Test-User": "10"})
        self.assertEqual(limited.status_code, 429)
        self.assertTrue(limited.headers.get("Retry-After"))
        self.assertEqual(self.client.post("/user", headers={"X-Test-User": "11"}).status_code, 200)

    def test_concurrent_requests_never_exceed_limit(self):
        limiter = InMemoryRateLimiter(max_buckets=50)

        def attempt(_):
            try:
                limiter.check("chat:user", 99, limit=7, window_seconds=60)
                return True
            except Exception as error:
                self.assertEqual(getattr(error, "status_code", None), 429)
                return False

        with ThreadPoolExecutor(max_workers=20) as pool:
            results = list(pool.map(attempt, range(40)))
        self.assertEqual(sum(results), 7)

    def test_expired_buckets_are_cleaned_and_capacity_is_bounded(self):
        now = [0.0]
        limiter = InMemoryRateLimiter(max_buckets=2, cleanup_every=1, clock=lambda: now[0])
        limiter.check("login:ip", "a", 1, 2)
        limiter.check("login:ip", "b", 1, 2)
        self.assertEqual(limiter.bucket_count, 2)
        with self.assertRaisesRegex(Exception, "Rate limiter is at capacity"):
            limiter.check("login:ip", "c", 1, 2)
        now[0] = 3.0
        limiter.check("login:ip", "c", 1, 2)
        self.assertLessEqual(limiter.bucket_count, 2)

    def test_protected_application_routes_have_the_expected_limit_dependencies(self):
        expected = {
            ("/users/login", "ip", "login"): auth.router,
            ("/users/signup", "ip", "signup"): signup.router,
            ("/documents/upload", "user", "upload"): documents.router,
            ("/chat/query", "user", "chat"): chat.router,
        }
        for (path, scope, action), router in expected.items():
            route = next(item for item in router.routes if item.path == path)
            markers = {
                (getattr(dependency.call, "rate_limit_scope", None),
                 getattr(dependency.call, "rate_limit_action", None))
                for dependency in route.dependant.dependencies
            }
            self.assertIn((scope, action), markers)


if __name__ == "__main__":
    unittest.main()
