import asyncio
import json
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.api.router import api_router
from titan_x.core.config import Settings, get_settings
from titan_x.core.events import on_shutdown, on_startup
from titan_x.core.exceptions import register_exception_handlers
from titan_x.core.logging import configure_logging
from titan_x.core.middleware import HTTPSRedirectMiddleware, SecurityHeadersMiddleware, TrustedHostMiddleware
from titan_x.core.security import decode_token
from titan_x.models.audit import AuditLog

settings: Settings = get_settings()
configure_logging(settings.log_level)
logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await on_startup(app, settings)
    try:
        yield
    finally:
        await on_shutdown(app, settings)


async def _audit_api_call(request: Request, status_code: int, duration_ms: int) -> None:
    try:
        user_id = None
        auth = request.headers.get("Authorization")
        if auth and auth.startswith("Bearer "):
            try:
                payload = decode_token(auth[7:], settings.jwt_secret_key.get_secret_value(), settings.jwt_algorithm)
                if payload.get("type") == "access":
                    user_id = int(payload["sub"])
            except Exception:
                pass
        severity = "info" if status_code < 400 else "warning" if status_code < 500 else "critical"
        details = json.dumps({
            "method": request.method, "path": request.url.path,
            "query": str(request.url.query), "duration_ms": duration_ms,
        })
        factory = request.app.state.session_factory
        async with factory() as session:
            session.add(AuditLog(
                user_id=user_id, action=request.method.lower(), entity_type="api_call",
                details_json=details, ip_address=request.client.host if request.client else None,
                category="api_call", severity=severity,
            ))
            await session.commit()
    except Exception:
        logger.warning("audit_log_failed", exc_info=True)


def create_app() -> FastAPI:
    _app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.debug,
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
        lifespan=lifespan,
    )

    @_app.get("/")
    async def root() -> dict[str, str]:
        return {
            "app": settings.app_name,
            "version": settings.app_version,
            "docs": "/docs" if settings.docs_enabled else "/api/v1/",
            "api": "/api/v1/",
        }

    _app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.parsed_cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "X-API-Key", "X-Request-ID", "Authorization"],
    )
    _app.add_middleware(SecurityHeadersMiddleware)
    _app.add_middleware(TrustedHostMiddleware, settings=settings)
    _app.add_middleware(HTTPSRedirectMiddleware, settings=settings)
    register_exception_handlers(_app)

    @_app.middleware("http")
    async def request_logging(request: Request, call_next: object) -> object:
        request_id = request.headers.get("X-Request-ID", str(uuid4()))
        structlog.contextvars.bind_contextvars(
            request_id=request_id, method=request.method, path=request.url.path
        )
        start = time.monotonic()
        response = None
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            duration_ms = int((time.monotonic() - start) * 1000)
            structlog.contextvars.clear_contextvars()
            if response is not None and request.url.path.startswith("/api/v1") and not request.url.path.startswith(("/api/v1/health", "/api/v1/docs")):
                asyncio.ensure_future(_audit_api_call(request, response.status_code, duration_ms))

    _app.include_router(api_router)
    return _app


app = create_app()
