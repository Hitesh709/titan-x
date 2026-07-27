from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.api.dependencies import (
    get_current_active_user,
    request_session,
    require_api_key,
)
from titan_x.models.user import User
from titan_x.api.schemas import PaginatedResponse
from titan_x.services.watchlist_engine import WatchlistEngine
from titan_x.services.watchlist_monitor_service import WatchlistMonitorService

router = APIRouter(prefix="/watchlists", tags=["watchlists"], dependencies=[Depends(require_api_key)])


def _get_engine(
    session: AsyncSession = Depends(request_session),
) -> WatchlistEngine:
    return WatchlistEngine(session)


@router.post("/folders", status_code=201)
async def create_folder(
    body: dict[str, Any],
    current_user: User = Depends(get_current_active_user),
    engine: WatchlistEngine = Depends(_get_engine),
) -> dict[str, Any]:
    return await engine.create_folder(
        user_id=current_user.id,
        name=body["name"],
        description=body.get("description"),
        parent_id=body.get("parent_id"),
        color=body.get("color"),
        sort_order=body.get("sort_order", 0),
    )


@router.get("/folders")
async def list_folders(
    current_user: User = Depends(get_current_active_user),
    engine: WatchlistEngine = Depends(_get_engine),
) -> list[dict[str, Any]]:
    return await engine.list_folders(current_user.id)


@router.get("/folders/{folder_id}")
async def get_folder(
    folder_id: int,
    current_user: User = Depends(get_current_active_user),
    engine: WatchlistEngine = Depends(_get_engine),
) -> dict[str, Any]:
    folder = await engine.get_folder(folder_id, current_user.id)
    if folder is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Folder not found")
    return folder


@router.put("/folders/{folder_id}")
async def update_folder(
    folder_id: int,
    body: dict[str, Any],
    current_user: User = Depends(get_current_active_user),
    engine: WatchlistEngine = Depends(_get_engine),
) -> dict[str, Any]:
    folder = await engine.update_folder(folder_id, current_user.id, **body)
    if folder is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Folder not found")
    return folder


@router.delete("/folders/{folder_id}", status_code=204)
async def delete_folder(
    folder_id: int,
    current_user: User = Depends(get_current_active_user),
    engine: WatchlistEngine = Depends(_get_engine),
) -> None:
    deleted = await engine.delete_folder(folder_id, current_user.id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Folder not found")


@router.post("", status_code=201)
async def create_watchlist(
    body: dict[str, Any],
    current_user: User = Depends(get_current_active_user),
    engine: WatchlistEngine = Depends(_get_engine),
) -> dict[str, Any]:
    return await engine.create_watchlist(
        user_id=current_user.id,
        name=body["name"],
        description=body.get("description"),
        folder_id=body.get("folder_id"),
        is_default=body.get("is_default", False),
    )


@router.get("")
async def list_watchlists(
    folder_id: int | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    current_user: User = Depends(get_current_active_user),
    engine: WatchlistEngine = Depends(_get_engine),
) -> dict[str, Any]:
    rows, total = await engine.list_watchlists(current_user.id, folder_id, skip, limit)
    return {"items": [engine._watchlist_to_dict(w) for w in rows], "total": total}


@router.get("/{watchlist_id}")
async def get_watchlist(
    watchlist_id: int,
    current_user: User = Depends(get_current_active_user),
    engine: WatchlistEngine = Depends(_get_engine),
) -> dict[str, Any]:
    wl = await engine.get_watchlist(watchlist_id, current_user.id)
    if wl is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Watchlist not found")
    return {
        "id": wl.id,
        "user_id": wl.user_id,
        "folder_id": wl.folder_id,
        "name": wl.name,
        "description": wl.description,
        "is_default": wl.is_default,
        "created_at": wl.created_at.isoformat() if wl.created_at else None,
        "items": [engine._item_to_dict(i) for i in wl.items],
    }


@router.put("/{watchlist_id}")
async def update_watchlist(
    watchlist_id: int,
    body: dict[str, Any],
    current_user: User = Depends(get_current_active_user),
    engine: WatchlistEngine = Depends(_get_engine),
) -> dict[str, Any]:
    wl = await engine.update_watchlist(watchlist_id, current_user.id, **body)
    if wl is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Watchlist not found")
    return wl


@router.delete("/{watchlist_id}", status_code=204)
async def delete_watchlist(
    watchlist_id: int,
    current_user: User = Depends(get_current_active_user),
    engine: WatchlistEngine = Depends(_get_engine),
) -> None:
    deleted = await engine.delete_watchlist(watchlist_id, current_user.id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Watchlist not found")


@router.post("/{watchlist_id}/items", status_code=201)
async def add_item(
    watchlist_id: int,
    body: dict[str, Any],
    current_user: User = Depends(get_current_active_user),
    engine: WatchlistEngine = Depends(_get_engine),
) -> dict[str, Any]:
    try:
        item = await engine.add_item(
            watchlist_id, current_user.id,
            symbol=body["symbol"],
            notes=body.get("notes"),
            sort_order=body.get("sort_order"),
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Watchlist not found")
    return item


@router.get("/{watchlist_id}/items")
async def list_items(
    watchlist_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    current_user: User = Depends(get_current_active_user),
    engine: WatchlistEngine = Depends(_get_engine),
) -> list[dict[str, Any]]:
    items = await engine.list_items(watchlist_id, current_user.id, skip, limit)
    if items is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Watchlist not found")
    return items


@router.put("/{watchlist_id}/items/{item_id}")
async def update_item(
    watchlist_id: int,
    item_id: int,
    body: dict[str, Any],
    current_user: User = Depends(get_current_active_user),
    engine: WatchlistEngine = Depends(_get_engine),
) -> dict[str, Any]:
    item = await engine.update_item(item_id, watchlist_id, current_user.id, **body)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
    return item


@router.delete("/{watchlist_id}/items/{item_id}", status_code=204)
async def remove_item(
    watchlist_id: int,
    item_id: int,
    current_user: User = Depends(get_current_active_user),
    engine: WatchlistEngine = Depends(_get_engine),
) -> None:
    deleted = await engine.remove_item(item_id, watchlist_id, current_user.id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")


@router.put("/{watchlist_id}/items/reorder")
async def reorder_items(
    watchlist_id: int,
    body: dict[str, Any],
    current_user: User = Depends(get_current_active_user),
    engine: WatchlistEngine = Depends(_get_engine),
) -> dict[str, str]:
    ok = await engine.reorder_items(watchlist_id, current_user.id, body["item_ids"])
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Watchlist not found")
    return {"status": "ok"}


@router.post("/tags", status_code=201)
async def create_tag(
    body: dict[str, Any],
    current_user: User = Depends(get_current_active_user),
    engine: WatchlistEngine = Depends(_get_engine),
) -> dict[str, Any]:
    return await engine.create_tag(
        user_id=current_user.id,
        name=body["name"],
        color=body.get("color"),
    )


@router.get("/tags")
async def list_tags(
    current_user: User = Depends(get_current_active_user),
    engine: WatchlistEngine = Depends(_get_engine),
) -> list[dict[str, Any]]:
    return await engine.list_tags(current_user.id)


@router.delete("/tags/{tag_id}", status_code=204)
async def delete_tag(
    tag_id: int,
    current_user: User = Depends(get_current_active_user),
    engine: WatchlistEngine = Depends(_get_engine),
) -> None:
    deleted = await engine.delete_tag(tag_id, current_user.id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")


@router.post("/{watchlist_id}/items/{item_id}/tags/{tag_id}", status_code=201)
async def tag_item(
    watchlist_id: int,
    item_id: int,
    tag_id: int,
    current_user: User = Depends(get_current_active_user),
    engine: WatchlistEngine = Depends(_get_engine),
) -> dict[str, str]:
    ok = await engine.tag_item(item_id, tag_id, watchlist_id, current_user.id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item, tag, or watchlist not found")
    return {"status": "tagged"}


@router.delete("/{watchlist_id}/items/{item_id}/tags/{tag_id}", status_code=204)
async def untag_item(
    watchlist_id: int,
    item_id: int,
    tag_id: int,
    current_user: User = Depends(get_current_active_user),
    engine: WatchlistEngine = Depends(_get_engine),
) -> None:
    ok = await engine.untag_item(item_id, tag_id, watchlist_id, current_user.id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item, tag, or watchlist not found")


@router.post("/{watchlist_id}/alerts", status_code=201)
async def create_alert(
    watchlist_id: int,
    body: dict[str, Any],
    current_user: User = Depends(get_current_active_user),
    engine: WatchlistEngine = Depends(_get_engine),
) -> dict[str, Any]:
    alert = await engine.create_alert(
        item_id=body["item_id"],
        watchlist_id=watchlist_id,
        user_id=current_user.id,
        alert_type=body["alert_type"],
        operator=body["operator"],
        threshold_value=body["threshold_value"],
    )
    if alert is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Watchlist or item not found")
    return alert


@router.get("/{watchlist_id}/alerts")
async def list_alerts(
    watchlist_id: int,
    current_user: User = Depends(get_current_active_user),
    engine: WatchlistEngine = Depends(_get_engine),
) -> list[dict[str, Any]]:
    alerts = await engine.list_alerts(watchlist_id, current_user.id)
    if alerts is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Watchlist not found")
    return alerts


@router.put("/{watchlist_id}/alerts/{alert_id}")
async def update_alert(
    watchlist_id: int,
    alert_id: int,
    body: dict[str, Any],
    current_user: User = Depends(get_current_active_user),
    engine: WatchlistEngine = Depends(_get_engine),
) -> dict[str, Any]:
    alert = await engine.update_alert(alert_id, watchlist_id, current_user.id, **body)
    if alert is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
    return alert


@router.delete("/{watchlist_id}/alerts/{alert_id}", status_code=204)
async def delete_alert(
    watchlist_id: int,
    alert_id: int,
    current_user: User = Depends(get_current_active_user),
    engine: WatchlistEngine = Depends(_get_engine),
) -> None:
    deleted = await engine.delete_alert(alert_id, watchlist_id, current_user.id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")


@router.post("/{watchlist_id}/ai/analyze")
async def run_ai_analysis(
    watchlist_id: int,
    current_user: User = Depends(get_current_active_user),
    engine: WatchlistEngine = Depends(_get_engine),
) -> list[dict[str, Any]]:
    return await engine.run_ai_analysis(watchlist_id, current_user.id)


@router.get("/{watchlist_id}/ai/insights")
async def get_insights(
    watchlist_id: int,
    insight_type: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    engine: WatchlistEngine = Depends(_get_engine),
) -> list[dict[str, Any]]:
    insights = await engine.get_insights(watchlist_id, current_user.id, insight_type, skip, limit)
    if insights is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Watchlist not found")
    return insights


@router.delete("/{watchlist_id}/ai/insights/{insight_id}", status_code=204)
async def delete_insight(
    watchlist_id: int,
    insight_id: int,
    current_user: User = Depends(get_current_active_user),
    engine: WatchlistEngine = Depends(_get_engine),
) -> None:
    deleted = await engine.delete_insight(insight_id, watchlist_id, current_user.id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Insight not found")


@router.get("/notifications")
async def list_notifications(
    is_read: bool | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    engine: WatchlistEngine = Depends(_get_engine),
) -> dict[str, Any]:
    rows, total = await engine.list_notifications(current_user.id, is_read, skip, limit)
    return {"items": [engine._notification_to_dict(n) for n in rows], "total": total}


@router.put("/notifications/{notification_id}/read")
async def mark_notification_read(
    notification_id: int,
    current_user: User = Depends(get_current_active_user),
    engine: WatchlistEngine = Depends(_get_engine),
) -> dict[str, str]:
    ok = await engine.mark_notification_read(notification_id, current_user.id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    return {"status": "ok"}


@router.put("/notifications/read-all")
async def mark_all_notifications_read(
    current_user: User = Depends(get_current_active_user),
    engine: WatchlistEngine = Depends(_get_engine),
) -> dict[str, Any]:
    count = await engine.mark_all_notifications_read(current_user.id)
    return {"marked_read": count}


@router.delete("/notifications/{notification_id}", status_code=204)
async def delete_notification(
    notification_id: int,
    current_user: User = Depends(get_current_active_user),
    engine: WatchlistEngine = Depends(_get_engine),
) -> None:
    deleted = await engine.delete_notification(notification_id, current_user.id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")


def _get_monitor(
    session: AsyncSession = Depends(request_session),
) -> WatchlistMonitorService:
    return WatchlistMonitorService(session)


@router.post("/{watchlist_id}/monitor/check")
async def check_watchlist(
    watchlist_id: int,
    current_user: User = Depends(get_current_active_user),
    monitor: WatchlistMonitorService = Depends(_get_monitor),
) -> dict:
    events = await monitor.check_watchlist(watchlist_id, current_user.id)
    return {"events_detected": len(events)}


@router.post("/monitor/check-all")
async def check_all_watchlists(
    current_user: User = Depends(get_current_active_user),
    monitor: WatchlistMonitorService = Depends(_get_monitor),
) -> dict:
    events = await monitor.check_all_watchlists(current_user.id)
    return {"events_detected": len(events)}


@router.get("/monitor/events")
async def list_monitor_events(
    current_user: User = Depends(get_current_active_user),
    monitor: WatchlistMonitorService = Depends(_get_monitor),
    event_type: str | None = Query(None),
    symbol: str | None = Query(None, min_length=1, max_length=16),
    severity: str | None = Query(None, pattern="^(info|warning|critical)$"),
    is_read: bool | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
) -> PaginatedResponse[dict]:
    rows, total = await monitor.list_events(
        current_user.id, event_type, symbol, severity, is_read, skip, limit,
    )
    items = [{
        "id": e.id, "symbol": e.symbol, "event_type": e.event_type,
        "severity": e.severity, "title": e.title, "message": e.message,
        "previous_value": e.previous_value, "current_value": e.current_value,
        "change_pct": e.change_pct, "is_read": e.is_read,
        "triggered_at": e.triggered_at.isoformat() if e.triggered_at else None,
    } for e in rows]
    return PaginatedResponse(items=items, total=total, skip=skip, limit=limit)


@router.post("/monitor/events/{event_id}/read")
async def mark_event_read(
    event_id: int,
    current_user: User = Depends(get_current_active_user),
    monitor: WatchlistMonitorService = Depends(_get_monitor),
) -> dict:
    ok = await monitor.mark_read(event_id, current_user.id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    return {"status": "read"}


@router.get("/monitor/stats")
async def monitor_stats(
    current_user: User = Depends(get_current_active_user),
    monitor: WatchlistMonitorService = Depends(_get_monitor),
) -> dict:
    return await monitor.get_event_stats(current_user.id)
