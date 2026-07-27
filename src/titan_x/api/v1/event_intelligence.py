from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.api import deps
from titan_x.models.user import User
from titan_x.services.event_intelligence_service import EventIntelligenceService

router = APIRouter(prefix="/event-intelligence", tags=["event_intelligence"])


async def _get_service(
    session: AsyncSession = Depends(deps.get_session),
) -> EventIntelligenceService:
    return EventIntelligenceService(session)


def _evt_dict(e: Any) -> dict[str, Any]:
    return {
        "id": e.id,
        "symbol": e.symbol,
        "event_type": e.event_type,
        "event_label": e.event_label,
        "impact_score": e.impact_score,
        "confidence": e.confidence,
        "source": e.source,
        "description": e.description,
        "detected_at": e.detected_at.isoformat() if e.detected_at else None,
        "event_date": e.event_date.isoformat() if e.event_date else None,
        "related_symbols": e.related_symbols,
        "is_resolved": e.is_resolved,
        "article_id": e.article_id,
    }


@router.post("/detect/news/{article_id}", summary="Detect events from a news article")
async def detect_from_news(
    article_id: int,
    service: EventIntelligenceService = Depends(_get_service),
    current_user: User = Depends(deps.get_current_active_superuser),
) -> dict[str, Any]:
    events = await service.detect_from_news(article_id)
    return {"detected": len(events), "events": [_evt_dict(e) for e in events]}


@router.post("/detect/recent", summary="Detect events from recent news")
async def detect_recent(
    hours: int = Query(24, description="Lookback hours"),
    service: EventIntelligenceService = Depends(_get_service),
    current_user: User = Depends(deps.get_current_active_superuser),
) -> dict[str, Any]:
    events = await service.detect_all_recent(hours)
    return {"detected": len(events), "events": [_evt_dict(e) for e in events]}


@router.get("/events", summary="List detected events")
async def list_events(
    symbol: str | None = Query(None),
    event_type: str | None = Query(None),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    limit: int = Query(100),
    offset: int = Query(0),
    service: EventIntelligenceService = Depends(_get_service),
) -> dict[str, Any]:
    events = await service.get_events(symbol, event_type, start_date, end_date, limit, offset)
    return {"total": len(events), "events": [_evt_dict(e) for e in events]}


@router.get("/summary/{symbol}", summary="Event summary for a symbol")
async def event_summary(
    symbol: str,
    days: int = Query(30),
    service: EventIntelligenceService = Depends(_get_service),
) -> dict[str, Any]:
    return await service.get_event_summary(symbol.upper(), days)


@router.post("/impact/daily", summary="Compute daily impact summary")
async def daily_impact(
    target_date: date | None = None,
    service: EventIntelligenceService = Depends(_get_service),
    current_user: User = Depends(deps.get_current_active_superuser),
) -> dict[str, Any]:
    history = await service.compute_daily_impact(target_date)
    return {
        "id": history.id,
        "impact_date": history.impact_date.isoformat() if history.impact_date else None,
        "total_positive": history.total_positive,
        "total_negative": history.total_negative,
        "total_neutral": history.total_neutral,
        "net_impact_score": history.net_impact_score,
    }
