from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from titan_x.api import deps
from titan_x.api.deps import get_app_session_factory
from titan_x.models.recommendation import Recommendation
from titan_x.models.user import User
from titan_x.services.recommendation_scan_service import get_scan_status

router = APIRouter(tags=["recommendations"])


@router.get("/recommendations/intraday")
async def intraday_recommendations(
    segment: str = Query("equity", pattern=r"^(equity|fno)$"),
    limit: int = Query(100, ge=1, le=3000),
    session=Depends(deps.get_session),
    session_factory=Depends(get_app_session_factory),
    _: User = Depends(deps.get_current_active_user),
):
    """Route the static intraday endpoint before the symbol catch-all route."""
    from titan_x.api.v1.intraday_recommendation import intraday_recommendations as handler

    return await handler(segment=segment, limit=limit, session=session, session_factory=session_factory, _=None)


@router.get("/recommendations/strict")
async def strict_recommendations(
    mode: str = Query("delivery", pattern=r"^(delivery|intraday)$"),
    segment: str = Query("equity", pattern=r"^(equity|fno)$"),
    limit: int = Query(100, ge=1, le=3000),
    session=Depends(deps.get_session),
    session_factory=Depends(get_app_session_factory),
    _: User = Depends(deps.get_current_active_user),
):
    """Compatibility/read model for the Recommendations dashboard.

    Keep this static route registered before /recommendations/{symbol}. For
    intraday mode, delegate to the dedicated multi-timeframe scanner. For
    delivery mode, read the persisted LIVE_SCAN records produced by the live
    full-market delivery scanner.
    """
    if segment == "fno":
        from fastapi import HTTPException

        raise HTTPException(400, "F&O universe is not enabled yet; use equity")

    if mode == "intraday":
        from titan_x.api.v1.intraday_recommendation import strict_recommendations as handler

        return await handler(
            mode=mode,
            segment=segment,
            limit=limit,
            session=session,
            session_factory=session_factory,
            _=None,
        )

    scan = get_scan_status()
    result = (
        await session.execute(
            select(Recommendation)
            .where(
                Recommendation.status == "active",
                Recommendation.recommendation_type == "LIVE_SCAN",
                Recommendation.source == "yahoo",
            )
            .order_by(Recommendation.score.desc(), Recommendation.generated_at.desc())
            .limit(limit)
        )
    ).scalars().all()

    recommendations = []
    for rec in result:
        try:
            metadata = json.loads(rec.metadata_json or "{}")
        except Exception:
            metadata = {}
        gate = metadata.get("fast_technical_gate") or {}
        technical_score = gate.get("selected_score", gate.get("delivery_score", rec.score or 0))
        item = {
            "id": rec.id,
            "symbol": rec.symbol,
            "direction": rec.direction,
            "signal": rec.signal,
            "confidence": rec.confidence,
            "price_target": rec.price_target,
            "current_price": rec.current_price,
            "timeframe": rec.timeframe,
            "reasoning": rec.reasoning,
            "recommendation_type": rec.recommendation_type,
            "status": rec.status,
            "score": rec.score,
            "technical_pillar_score": technical_score,
            "technical_score": technical_score,
            "risk_level": rec.risk_level,
            "predicted_return_pct": rec.predicted_return_pct,
            "source": rec.source,
            "model_version_label": rec.model_version_label,
            "generated_at": rec.generated_at.isoformat() if rec.generated_at else None,
            "expires_at": rec.expires_at.isoformat() if rec.expires_at else None,
            "metadata_json": rec.metadata_json,
        }
        recommendations.append(item)

    running = bool(scan.get("running"))
    last = scan.get("last") or {}
    universe_size = int(last.get("universe") or scan.get("last_universe", {}).get("nse", {}).get("total_active") or 0)
    scanned = int(last.get("scanned") or 0)
    progress = (scanned / universe_size * 100.0) if universe_size else 0.0
    return {
        "recommendations": recommendations,
        "strict_technical_threshold": 80,
        "strict_gate": "live_delivery_technical_pillar_ge_80",
        "scanning": running,
        "scan_status": {
            "scanned": scanned,
            "universe_size": universe_size,
            "progress_pct": progress,
            "error": scan.get("last_error"),
        },
        "mode": mode,
        "segment": segment,
    }
