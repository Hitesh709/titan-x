import pytest
from httpx import ASGITransport, AsyncClient
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route

from titan_x.core.config import Settings
from titan_x.core.middleware import HTTPSRedirectMiddleware, SecurityHeadersMiddleware, TrustedHostMiddleware


async def ok_endpoint(request: object) -> PlainTextResponse:
    return PlainTextResponse("OK")


def _app_with_middleware(settings: Settings, middlewares: list) -> Starlette:
    app = Starlette(routes=[Route("/", endpoint=ok_endpoint)])
    for middleware_cls, kwargs in middlewares:
        app.add_middleware(middleware_cls, **kwargs)
    return app


class TestSecurityHeadersMiddleware:
    @pytest.mark.asyncio
    async def test_sets_security_headers(self) -> None:
        settings = Settings(
            database_url="sqlite+aiosqlite:///",
            redis_url="redis://localhost:6379/0",
            api_key="a" * 32,
            jwt_secret_key="b" * 32,
            environment="test",
        )
        app = _app_with_middleware(settings, [(SecurityHeadersMiddleware, {})])
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/")
            assert resp.headers["X-Content-Type-Options"] == "nosniff"
            assert resp.headers["X-Frame-Options"] == "DENY"
            assert resp.headers["X-XSS-Protection"] == "0"
            assert resp.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
            assert resp.headers["Permissions-Policy"] == "camera=(), microphone=(), geolocation=()"

    @pytest.mark.asyncio
    async def test_sets_hsts_over_https(self) -> None:
        settings = Settings(
            database_url="sqlite+aiosqlite:///",
            redis_url="redis://localhost:6379/0",
            api_key="a" * 32,
            jwt_secret_key="b" * 32,
            environment="test",
        )
        app = _app_with_middleware(settings, [(SecurityHeadersMiddleware, {})])
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="https://test") as client:
            resp = await client.get("/")
            assert resp.headers["Strict-Transport-Security"] == "max-age=31536000; includeSubDomains"

    @pytest.mark.asyncio
    async def test_does_not_set_hsts_over_http(self) -> None:
        settings = Settings(
            database_url="sqlite+aiosqlite:///",
            redis_url="redis://localhost:6379/0",
            api_key="a" * 32,
            jwt_secret_key="b" * 32,
            environment="test",
        )
        app = _app_with_middleware(settings, [(SecurityHeadersMiddleware, {})])
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/")
            assert "Strict-Transport-Security" not in resp.headers


class TestTrustedHostMiddleware:
    @pytest.mark.asyncio
    async def test_allows_trusted_host(self) -> None:
        settings = Settings(
            database_url="sqlite+aiosqlite:///",
            redis_url="redis://localhost:6379/0",
            api_key="a" * 32,
            jwt_secret_key="b" * 32,
            environment="test",
            trusted_hosts="example.com,api.example.com",
        )
        app = _app_with_middleware(settings, [(TrustedHostMiddleware, {"settings": settings})])
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://example.com") as client:
            resp = await client.get("/")
            assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_rejects_untrusted_host(self) -> None:
        settings = Settings(
            database_url="sqlite+aiosqlite:///",
            redis_url="redis://localhost:6379/0",
            api_key="a" * 32,
            jwt_secret_key="b" * 32,
            environment="test",
            trusted_hosts="example.com",
        )
        app = _app_with_middleware(settings, [(TrustedHostMiddleware, {"settings": settings})])
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://malicious.com") as client:
            resp = await client.get("/")
            assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_allows_wildcard_pattern(self) -> None:
        settings = Settings(
            database_url="sqlite+aiosqlite:///",
            redis_url="redis://localhost:6379/0",
            api_key="a" * 32,
            jwt_secret_key="b" * 32,
            environment="test",
            trusted_hosts="*.example.com",
        )
        app = _app_with_middleware(settings, [(TrustedHostMiddleware, {"settings": settings})])
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://sub.example.com") as client:
            resp = await client.get("/")
            assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_passes_through_when_no_hosts_configured(self) -> None:
        settings = Settings(
            database_url="sqlite+aiosqlite:///",
            redis_url="redis://localhost:6379/0",
            api_key="a" * 32,
            jwt_secret_key="b" * 32,
            environment="test",
            trusted_hosts="",
        )
        app = _app_with_middleware(settings, [(TrustedHostMiddleware, {"settings": settings})])
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://any-host.com") as client:
            resp = await client.get("/")
            assert resp.status_code == 200


class TestHTTPSRedirectMiddleware:
    @pytest.mark.asyncio
    async def test_redirects_to_https_when_enabled(self) -> None:
        settings = Settings(
            database_url="sqlite+aiosqlite:///",
            redis_url="redis://localhost:6379/0",
            api_key="a" * 32,
            jwt_secret_key="b" * 32,
            environment="production",
            enable_https_redirect=True,
        )
        app = _app_with_middleware(settings, [(HTTPSRedirectMiddleware, {"settings": settings})])
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://example.com") as client:
            resp = await client.get("/", follow_redirects=False)
            assert resp.status_code == 307
            assert resp.headers["location"].startswith("https://example.com")

    @pytest.mark.asyncio
    async def test_does_not_redirect_when_disabled(self) -> None:
        settings = Settings(
            database_url="sqlite+aiosqlite:///",
            redis_url="redis://localhost:6379/0",
            api_key="a" * 32,
            jwt_secret_key="b" * 32,
            environment="test",
            enable_https_redirect=False,
        )
        app = _app_with_middleware(settings, [(HTTPSRedirectMiddleware, {"settings": settings})])
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://example.com") as client:
            resp = await client.get("/", follow_redirects=False)
            assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_does_not_redirect_localhost(self) -> None:
        settings = Settings(
            database_url="sqlite+aiosqlite:///",
            redis_url="redis://localhost:6379/0",
            api_key="a" * 32,
            jwt_secret_key="b" * 32,
            environment="production",
            enable_https_redirect=True,
        )
        app = _app_with_middleware(settings, [(HTTPSRedirectMiddleware, {"settings": settings})])
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://localhost:8000") as client:
            resp = await client.get("/", follow_redirects=False)
            assert resp.status_code == 200
