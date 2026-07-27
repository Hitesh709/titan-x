"""
Smoke tests — verify the deployed application is alive and responding correctly.
Run against any environment::

    pytest tests/smoke -v --base-url=http://localhost:8000 --api-key=xxx
"""
from __future__ import annotations

import os

import pytest
import httpx

pytestmark = pytest.mark.smoke


def pytest_addoption(parser):
    parser.addoption("--base-url", default=os.getenv("SMOKE_BASE_URL", "http://localhost:8000"))
    parser.addoption("--api-key", default=os.getenv("SMOKE_API_KEY", ""))


@pytest.fixture(scope="session")
def base_url(request):
    return request.config.getoption("--base-url")


@pytest.fixture(scope="session")
def api_key(request):
    return request.config.getoption("--api-key")


@pytest.fixture(scope="session")
def client(base_url, api_key):
    headers = {"X-API-Key": api_key} if api_key else {}
    with httpx.Client(base_url=base_url, headers=headers, timeout=10.0) as c:
        yield c


class TestLiveness:
    def test_live_endpoint(self, client):
        resp = client.get("/health/live")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") == "ok" or "status" in data

    def test_ready_endpoint(self, client):
        resp = client.get("/health/ready")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") == "ok" or "database" in data or "status" in data

    def test_version_endpoint(self, client):
        resp = client.get("/api/v1/version")
        assert resp.status_code == 200
        data = resp.json()
        assert "version" in data or "app_version" in data or "app" in data

    def test_cors_headers_present(self, client):
        resp = client.options(
            "/api/v1/version",
            headers={"Origin": "https://app.titanx.io", "Access-Control-Request-Method": "GET"},
        )
        assert "access-control-allow-origin" in resp.headers


class TestApiAuth:
    def test_unauthenticated_access_returns_401(self, client):
        resp = client.get("/api/v1/users/me")
        assert resp.status_code in (401, 403), f"Expected 401/403, got {resp.status_code}"

    def test_invalid_api_key_returns_403(self, base_url):
        resp = httpx.get(
            f"{base_url}/api/v1/version",
            headers={"X-API-Key": "invalid-key"},
            timeout=10.0,
        )
        assert resp.status_code in (401, 403)

    def test_health_does_not_require_auth(self, client):
        resp = client.get("/health/live")
        assert resp.status_code == 200


class TestSecurityHeaders:
    def test_security_headers_present(self, client):
        resp = client.get("/health/live")
        headers = {k.lower(): v for k, v in resp.headers.items()}
        security_headers = [
            "x-content-type-options",
            "x-frame-options",
            "x-xss-protection",
            "strict-transport-security",
        ]
        for h in security_headers:
            assert h in headers, f"Missing security header: {h}"


class TestApiResponse:
    def test_response_time_within_limit(self, client):
        import time

        start = time.monotonic()
        client.get("/health/live")
        elapsed_ms = (time.monotonic() - start) * 1000
        assert elapsed_ms < 1000, f"Response time too slow: {elapsed_ms:.0f}ms"

    def test_json_content_type(self, client):
        resp = client.get("/api/v1/version")
        assert "application/json" in resp.headers.get("content-type", "")
