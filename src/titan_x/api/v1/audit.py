import json
from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.api.dependencies import get_current_active_user, request_session
from titan_x.models.user import User
from titan_x.services.audit_service import (
    CATEGORIES, SEVERITY_CRITICAL, SEVERITY_INFO, SEVERITY_WARNING,
    AuditService,
)

router = APIRouter(prefix="/audit", tags=["audit"])


async def get_audit_service(
    session: Annotated[AsyncSession, Depends(request_session)],
) -> AuditService:
    return AuditService(session)


@router.post("")
async def log_action(
    request: Request,
    user: Annotated[User, Depends(get_current_active_user)],
    svc: Annotated[AuditService, Depends(get_audit_service)],
    action: str = Query(..., min_length=1, max_length=50),
    entity_type: str = Query(..., min_length=1, max_length=50),
    entity_id: int | None = Query(None),
    details_json: str | None = Query(None),
    category: str = Query("api_call", pattern="^(api_call|user_action|ai_decision|config_change|security_event)$"),
    severity: str = Query("info", pattern="^(info|warning|critical)$"),
):
    entry = await svc.log(
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        user_id=user.id,
        details_json=details_json,
        ip_address=request.client.host if request.client else None,
        category=category,
        severity=severity,
    )
    return entry.to_dict()


@router.get("")
async def list_logs(
    user: Annotated[User, Depends(get_current_active_user)],
    svc: Annotated[AuditService, Depends(get_audit_service)],
    action: str | None = Query(None, max_length=50),
    entity_type: str | None = Query(None, max_length=50),
    category: str | None = Query(None, pattern="^(api_call|user_action|ai_decision|config_change|security_event)$"),
    severity: str | None = Query(None, pattern="^(info|warning|critical)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    since: str | None = Query(None, description="ISO datetime filter (inclusive)"),
    until: str | None = Query(None, description="ISO datetime filter (inclusive)"),
):
    since_dt = datetime.fromisoformat(since) if since else None
    until_dt = datetime.fromisoformat(until) if until else None
    logs, total = await svc.list_logs(
        user_id=user.id,
        action=action,
        entity_type=entity_type,
        category=category,
        severity=severity,
        limit=limit,
        offset=offset,
        since=since_dt,
        until=until_dt,
    )
    return {"items": [log.to_dict() for log in logs], "total": total}


@router.get("/all")
async def list_all_logs(
    svc: Annotated[AuditService, Depends(get_audit_service)],
    action: str | None = Query(None, max_length=50),
    entity_type: str | None = Query(None, max_length=50),
    category: str | None = Query(None, pattern="^(api_call|user_action|ai_decision|config_change|security_event)$"),
    severity: str | None = Query(None, pattern="^(info|warning|critical)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    since: str | None = Query(None, description="ISO datetime filter (inclusive)"),
    until: str | None = Query(None, description="ISO datetime filter (inclusive)"),
    current_user: Annotated[User, Depends(get_current_active_user)] = None,
):
    since_dt = datetime.fromisoformat(since) if since else None
    until_dt = datetime.fromisoformat(until) if until else None
    logs, total = await svc.list_logs(
        action=action,
        entity_type=entity_type,
        category=category,
        severity=severity,
        limit=limit,
        offset=offset,
        since=since_dt,
        until=until_dt,
    )
    return {"items": [log.to_dict() for log in logs], "total": total}


@router.get("/stats")
async def audit_stats(
    user: Annotated[User, Depends(get_current_active_user)],
    svc: Annotated[AuditService, Depends(get_audit_service)],
    category: str | None = Query(None, pattern="^(api_call|user_action|ai_decision|config_change|security_event)$"),
    since: str | None = Query(None, description="ISO datetime filter"),
    until: str | None = Query(None, description="ISO datetime filter"),
    scope: str = Query("user", pattern="^(user|global)$"),
):
    since_dt = datetime.fromisoformat(since) if since else None
    until_dt = datetime.fromisoformat(until) if until else None
    stats = await svc.get_stats(
        user_id=user.id if scope == "user" else None,
        category=category,
        since=since_dt,
        until=until_dt,
    )
    stats["scope"] = scope
    return stats


@router.get("/stats/global")
async def global_audit_stats(
    svc: Annotated[AuditService, Depends(get_audit_service)],
    since: str | None = Query(None, description="ISO datetime filter"),
    until: str | None = Query(None, description="ISO datetime filter"),
    current_user: Annotated[User, Depends(get_current_active_user)] = None,
):
    since_dt = datetime.fromisoformat(since) if since else None
    until_dt = datetime.fromisoformat(until) if until else None
    stats = await svc.get_stats(since=since_dt, until=until_dt)
    stats["scope"] = "global"
    return stats


@router.get("/categories")
async def list_categories():
    return {"categories": CATEGORIES}
