from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.api.dependencies import get_current_active_user, request_session
from titan_x.models.user import User
from titan_x.services.monitoring_service import MonitoringService

router = APIRouter(prefix="/monitoring", tags=["monitoring"])
SYSTEM_ROUTER_PREFIX = "/system"


async def get_monitoring_service(
    session: Annotated[AsyncSession, Depends(request_session)],
) -> MonitoringService:
    return MonitoringService(session)


@router.get("/system")
async def system_health(
    svc: Annotated[MonitoringService, Depends(get_monitoring_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> dict:
    return await svc.get_system_health()


@router.get("/metrics/{metric_name}")
async def get_metric_history(
    metric_name: str,
    svc: Annotated[MonitoringService, Depends(get_monitoring_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    since: str | None = Query(None),
    until: str | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
) -> dict:
    since_dt = datetime.fromisoformat(since) if since else None
    until_dt = datetime.fromisoformat(until) if until else None
    metrics = await svc.get_metric_history(metric_name, since=since_dt, until=until_dt, limit=limit)
    return {
        "metric_name": metric_name,
        "count": len(metrics),
        "items": [
            {
                "id": m.id,
                "metric_name": m.metric_name,
                "metric_value": m.metric_value,
                "tags_json": m.tags_json,
                "recorded_at": m.recorded_at.isoformat() if m.recorded_at else None,
            }
            for m in metrics
        ],
    }


@router.get("/metrics/{metric_name}/stats")
async def get_metric_stats(
    metric_name: str,
    svc: Annotated[MonitoringService, Depends(get_monitoring_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    since: str | None = Query(None),
    until: str | None = Query(None),
) -> dict:
    since_dt = datetime.fromisoformat(since) if since else None
    until_dt = datetime.fromisoformat(until) if until else None
    return await svc.get_metric_stats(metric_name, since=since_dt, until=until_dt)


@router.post("/metrics/{metric_name}")
async def record_metric(
    metric_name: str,
    svc: Annotated[MonitoringService, Depends(get_monitoring_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    value: float = Query(...),
    tags: str | None = Query(None, description="JSON object string"),
) -> dict:
    tags_dict = None
    if tags:
        import json
        try:
            tags_dict = json.loads(tags)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid JSON for tags")
    entry = await svc.record_metric(metric_name, value, tags=tags_dict)
    return {
        "id": entry.id,
        "metric_name": entry.metric_name,
        "metric_value": entry.metric_value,
        "tags_json": entry.tags_json,
        "recorded_at": entry.recorded_at.isoformat() if entry.recorded_at else None,
    }
