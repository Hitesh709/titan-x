import asyncio
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.api.router import api_router
from titan_x.core.audit import audit_event_later
from titan_x.core.config import Settings, get_settings
from titan_x.core.events import on_shutdown, on_startup
from titan_x.core.exceptions import register_exception_handlers
from titan_x.core.logging import configure_logging
from titan_x.core.middleware import HTTPSRedirectMiddleware, SecurityHeadersMiddleware, TrustedHostMiddleware

settings: Settings = get_settings()
configure_logging(settings.log_level, settings.log_format)
logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await on_startup(app, settings)
    try:
        yield
    finally:
        await on_shutdown(app, settings)


# Audit recording for every API call is handled by
# ``titan_x.core.audit.audit_event_later`` from the request_logging middleware.


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
        request_id = request.headers.get("X-Request-ID") or str(uuid4())
        correlation_id = request.headers.get("X-Correlation-ID") or request_id
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            correlation_id=correlation_id,
            method=request.method,
            path=request.url.path,
        )
        start = time.monotonic()
        response = None
        status_code: int | None = None
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Correlation-ID"] = correlation_id
            return response
        except Exception:
            status_code = 500
            raise
        finally:
            duration_ms = int((time.monotonic() - start) * 1000)
            if (
                status_code is not None
                and request.url.path.startswith("/api/v1")
                and not request.url.path.startswith(("/api/v1/health", "/api/v1/docs"))
            ):
                req_logger = logger.bind(request_id=request_id, correlation_id=correlation_id)
                req_logger.info(
                    "request_completed",
                    status_code=status_code,
                    duration_ms=duration_ms,
                )
                if duration_ms >= settings.log_slow_request_ms:
                    req_logger.warning("slow_request", status_code=status_code, duration_ms=duration_ms)
                audit_event_later(
                    request,
                    action=request.method.lower(),
                    entity_type="api_call",
                    details={
                        "method": request.method,
                        "path": request.url.path,
                        "query": str(request.url.query),
                        "status_code": status_code,
                        "duration_ms": duration_ms,
                        "request_id": request_id,
                        "correlation_id": correlation_id,
                        "user_agent": request.headers.get("User-Agent"),
                    },
                    category="api_call",
                    severity="info" if status_code < 400 else "warning" if status_code < 500 else "critical",
                )
            structlog.contextvars.clear_contextvars()

    _app.include_router(api_router)
    return _app


app = create_app()
