"""Unified audit logging.

Provides helpers to record audit events (security-relevant actions, API calls,
trades, etc.) into the ``audit_logs`` table. Events are written asynchronously
and never block the request path.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

import structlog
from fastapi import Request

from titan_x.core.config import Settings, get_settings
from titan_x.core.security import decode_token
from titan_x.models.audit import AuditLog

logger = structlog.get_logger(__name__)


def _resolve_user_id(request: Request) -> int | None:
    """Best-effort extraction of the subject from a Bearer token, if present."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    try:
        settings: Settings = get_settings()
        payload = decode_token(
            auth[7:],
            settings.jwt_secret_key.get_secret_value(),
            settings.jwt_algorithm,
        )
        if payload.get("type") == "access":
            return int(payload["sub"])
    except Exception:
        return None
    return None


async def write_audit(
    session_factory: Any,
    *,
    user_id: int | None,
    action: str,
    entity_type: str,
    entity_id: int | None = None,
    details: dict[str, Any] | None = None,
    ip_address: str | None = None,
    category: str = "audit",
    severity: str = "info",
) -> None:
    """Persist a single audit record. Swallows its own failures by design."""
    try:
        async with session_factory() as session:
            session.add(
                AuditLog(
                    user_id=user_id,
                    action=action,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    details_json=json.dumps(details) if details is not None else None,
                    ip_address=ip_address,
                    category=category,
                    severity=severity,
                )
            )
            await session.commit()
    except Exception:
        logger.warning("audit_log_failed", exc_info=True)


async def audit_event(
    request: Request,
    *,
    action: str,
    entity_type: str,
    entity_id: int | None = None,
    details: dict[str, Any] | None = None,
    category: str = "audit",
    severity: str = "info",
    user_id: int | None = None,
) -> None:
    """Record an audit event derived from the incoming request."""
    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        return
    if user_id is None:
        user_id = _resolve_user_id(request)
    ip_address = request.client.host if request.client else None
    await write_audit(
        factory,
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details,
        ip_address=ip_address,
        category=category,
        severity=severity,
    )


def audit_event_later(request: Request, **kwargs: Any) -> None:
    """Schedule :func:`audit_event` without blocking the response."""
    asyncio.ensure_future(audit_event(request, **kwargs))


__all__ = ["audit_event", "audit_event_later", "write_audit"]
