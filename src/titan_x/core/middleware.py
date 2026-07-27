import re
from collections.abc import Awaitable, Callable
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse, RedirectResponse, Response
from starlette.types import ASGIApp

from titan_x.core.config import Settings


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "0"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response


class TrustedHostMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        super().__init__(app)
        self.allowed_hosts: list[str] = settings.parsed_trusted_hosts
        self.allowed_patterns: list[re.Pattern[str]] = [
            re.compile(pattern.replace(".", r"\.").replace("*", r".*") + "$")
            for pattern in self.allowed_hosts
        ]

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        if not self.allowed_hosts:
            return await call_next(request)

        host: str = request.headers.get("host", "").split(":")[0]
        if not host:
            return await call_next(request)

        if not any(pattern.match(host) for pattern in self.allowed_patterns):
            return PlainTextResponse("Invalid Host header", status_code=400)

        return await call_next(request)


class HTTPSRedirectMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        super().__init__(app)
        self.enabled: bool = settings.enable_https_redirect

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        if not self.enabled:
            return await call_next(request)

        if request.url.scheme != "https" and not request.url.hostname in ("localhost", "127.0.0.1"):
            redirect_url = request.url.replace(scheme="https")
            return RedirectResponse(url=str(redirect_url), status_code=307)

        return await call_next(request)
