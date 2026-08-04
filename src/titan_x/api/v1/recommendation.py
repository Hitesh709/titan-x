from fastapi import APIRouter, Depends, HTTPException, Query
from starlette.background import BackgroundTasks

from titan_x.api import deps
from titan_x.api.deps import get_app_session_factory
from titan_x.api.schemas import PaginatedResponse
from titan_x.models.user import User
from titan_x.services.recommendation_service import RecommendationService

router = APIRouter(tags=["recommendations"])


@router.get("/recommendations")
async def list_recommendations(
    symbol: str | None = None,
    direction: str | None = None,
    status: str | None = None,
    recommendation_type: str | None = None,
    timeframe: str | None = None,
    min_confidence: float | None = None,
    min_score: float | None = None,
    source: str | None = None,
    risk_level: str | None = None,
    decision: str | None = None,
    outcome: str | None = None,
    sort_by: str = "generated_at",
    sort_desc: bool = True,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_user),
):
    svc = RecommendationService(session)
    items = await svc.list_recommendations(
        symbol=symbol, direction=direction, status=status,
        recommendation_type=recommendation_type, timeframe=timeframe,
        min_confidence=min_confidence, min_score=min_score,
        source=source, risk_level=risk_level,
        decision=decision, outcome=outcome,
        sort_by=sort_by, sort_desc=sort_desc,
        limit=limit, offset=offset,
    )
    total = await svc.count_recommendations(
        symbol=symbol, direction=direction, status=status,
    )
    return PaginatedResponse(
        items=[_rec_dict(r) for r in items],
        total=total, limit=limit, offset=offset,
    )


@router.get("/recommendations/top")
async def get_top_recommendations(
    limit: int = Query(default=10, le=50),
    status: str = "active",
    min_score: float | None = None,
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_user),
):
    svc = RecommendationService(session)
    items = await svc.get_top_recommendations(
        limit=limit, status=status, min_score=min_score,
    )
    return {
        "recommendations": [_rec_dict(r) for r in items],
        "count": len(items),
    }


@router.get("/recommendations/scan/status")
async def scan_status(
    _: User = Depends(deps.get_current_active_user),
):
    from titan_x.services.recommendation_scan_service import get_scan_status

    return get_scan_status()


@router.post("/recommendations/scan")
async def trigger_scan(
    max_age_minutes: int | None = Query(default=60, ge=0),
    limit: int | None = Query(default=None, ge=1, le=2000),
    session_factory=Depends(get_app_session_factory),
    _: User = Depends(deps.get_current_active_user),
):
    """Start a background full-market recommendation scan.

    Returns immediately; results appear incrementally as the scan progresses.
    The frontend polls ``GET /recommendations`` every few seconds to pick them up.
    """
    from titan_x.services.recommendation_scan_service import (
        run_background_scan,
        run_universe_load,
    )

    async def _background() -> None:
        try:
            await run_universe_load(session_factory)
            await run_background_scan(session_factory, max_age_minutes=max_age_minutes, limit=limit)
        except Exception as exc:  # noqa: BLE001
            import structlog

            structlog.get_logger("recommendation.scan").error("background_scan_failed", error=str(exc))

    background_tasks.add_task(_background)

    return {"started": True, "max_age_minutes": max_age_minutes, "limit": limit}


@router.get("/recommendations/history")
async def get_recommendation_history(
    symbol: str = Query(...),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_user),
):
    svc = RecommendationService(session)
    items = await svc.get_recommendation_history(
        symbol=symbol, limit=limit, offset=offset,
    )
    total = await svc.count_recommendations(symbol=symbol)
    return PaginatedResponse(
        items=[_rec_dict(r) for r in items],
        total=total, limit=limit, offset=offset,
    )


@router.get("/recommendations/{symbol}")
async def get_recommendations_by_symbol(
    symbol: str,
    status: str | None = "active",
    limit: int = Query(default=20, le=100),
    offset: int = Query(default=0, ge=0),
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_user),
):
    svc = RecommendationService(session)
    items = await svc.get_recommendations_by_symbol(
        symbol=symbol, status=status, limit=limit, offset=offset,
    )
    total = await svc.count_recommendations(symbol=symbol, status=status)
    return PaginatedResponse(
        items=[_rec_dict(r) for r in items],
        total=total, limit=limit, offset=offset,
    )


@router.patch("/recommendations/{rec_id}/decision")
async def set_decision(
    rec_id: int,
    decision: str = Query(...),
    decision_reason: str | None = None,
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_user),
):
    svc = RecommendationService(session)
    rec = await svc.set_decision(
        rec_id=rec_id, decision=decision, decision_reason=decision_reason,
    )
    if not rec:
        raise HTTPException(404, "Recommendation not found")
    return _rec_dict(rec)


@router.patch("/recommendations/{rec_id}/outcome")
async def set_outcome(
    rec_id: int,
    outcome: str = Query(...),
    actual_outcome_pnl: float | None = None,
    outcome_details: str | None = None,
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_user),
):
    svc = RecommendationService(session)
    rec = await svc.set_outcome(
        rec_id=rec_id, outcome=outcome,
        actual_outcome_pnl=actual_outcome_pnl,
        outcome_details=outcome_details,
    )
    if not rec:
        raise HTTPException(404, "Recommendation not found")
    return _rec_dict(rec)


def _rec_dict(r) -> dict:
    return {
        "id": r.id,
        "symbol": r.symbol,
        "direction": r.direction,
        "confidence": r.confidence,
        "price_target": r.price_target,
        "current_price": r.current_price,
        "timeframe": r.timeframe,
        "reasoning": r.reasoning,
        "recommendation_type": r.recommendation_type,
        "status": r.status,
        "score": r.score,
        "risk_level": r.risk_level,
        "predicted_return_pct": r.predicted_return_pct,
        "source": r.source,
        "metadata_json": r.metadata_json,
        "inputs_json": r.inputs_json,
        "model_version_id": r.model_version_id,
        "model_version_label": r.model_version_label,
        "decision": r.decision,
        "decision_reason": r.decision_reason,
        "decided_at": r.decided_at.isoformat() if r.decided_at else None,
        "outcome": r.outcome,
        "actual_outcome_pnl": r.actual_outcome_pnl,
        "outcome_details": r.outcome_details,
        "resolved_at": r.resolved_at.isoformat() if r.resolved_at else None,
        "generated_at": r.generated_at.isoformat() if r.generated_at else None,
        "expires_at": r.expires_at.isoformat() if r.expires_at else None,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }
