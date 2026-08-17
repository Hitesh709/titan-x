"""Centralized exception handling for the API.

Registers global handlers so every error path produces a consistent JSON
payload, never leaks internals to clients, and emits structured logs with a
unique ``error_id`` that clients can quote when reporting problems.
"""
from __future__ import annotations

import uuid
from typing import Any

import structlog
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

logger = structlog.get_logger(__name__)

_INTERNAL_ERROR_DETAIL = "Internal Server Error"


def _log(request: Request, event: str, *, error: str | None = None, **extra: Any) -> str:
    error_id = uuid.uuid4().hex
    logger.error(
        event,
        error_id=error_id,
        path=request.url.path,
        method=request.method,
        error=error,
        **extra,
    )
    return error_id


async def _validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = exc.errors()
    error_id = uuid.uuid4().hex
    logger.error(
        "request_validation_error",
        error_id=error_id,
        path=request.url.path,
        method=request.method,
        validation_errors=errors,
    )
    return JSONResponse(status_code=422, content={"detail": errors, "error_id": error_id})


async def _http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    # HTTPExceptions raised with status >= 500 indicate an upstream bug; log them
    # as errors (with an error_id) while still returning the (safe) detail.
    if exc.status_code >= 500:
        error_id = _log(
            request,
            "http_server_error",
            error=str(exc.detail),
            status_code=exc.status_code,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail, "error_id": error_id},
            headers=getattr(exc, "headers", None),
        )
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=getattr(exc, "headers", None),
    )


async def _sqlalchemy_error_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
    error_id = _log(
        request,
        "database_error",
        error=type(exc).__name__,
    )
    return JSONResponse(status_code=500, content={"detail": _INTERNAL_ERROR_DETAIL, "error_id": error_id})


async def _unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    error_id = _log(
        request,
        "unhandled_exception",
        error=type(exc).__name__,
    )
    return JSONResponse(status_code=500, content={"detail": _INTERNAL_ERROR_DETAIL, "error_id": error_id})


def register_exception_handlers(app: FastAPI) -> None:
    """Wire all global exception handlers onto the application."""
    app.add_exception_handler(RequestValidationError, _validation_error_handler)
    app.add_exception_handler(HTTPException, _http_exception_handler)
    app.add_exception_handler(SQLAlchemyError, _sqlalchemy_error_handler)
    app.add_exception_handler(Exception, _unhandled_error_handler)


__all__ = ["register_exception_handlers"]
