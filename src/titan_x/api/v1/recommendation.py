from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from starlette.background import BackgroundTasks

from titan_x.api import deps
from titan_x.api.deps import get_app_session_factory
from titan_x.api.schemas import PaginatedResponse
from titan_x.infrastructure.market_data_providers import YahooFinanceProvider
from titan_x.models.company import Company
from titan_x.models.fundamental import FundamentalMetric
from titan_x.models.market_breadth import MarketBreadth
from titan_x.models.sector import SectorPerformance
from titan_x.models.user import User
from titan_x.services.ai_recommendation_engine import (
    AIRecommendationEngine,
    bars_from_records,
    fundamentals_from_records,
)
from titan_x.services.recommendation_service import RecommendationService

router = APIRouter(tags=["recommendations"])

SORTABLE_COLUMNS = {
    "symbol",
    "direction",
    "signal",
    "confidence",
    "current_price",
    "price_target",
    "score",
    "risk_level",
    "predicted_return_pct",
    "generated_at",
}


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
    if sort_by not in SORTABLE_COLUMNS:
        raise HTTPException(422, f"Unsupported sort_by '{sort_by}'")
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
        total=total, skip=offset, limit=limit,
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
    background_tasks: BackgroundTasks,
    max_age_minutes: int | None = Query(default=60, ge=0),
    limit: int | None = Query(default=None, ge=1, le=2000),
    sync: bool = Query(default=False),
    session_factory=Depends(get_app_session_factory),
    _: User = Depends(deps.get_current_active_user),
):
    """Run a full-market recommendation scan.

    By default it runs as a background task and returns immediately; the
    frontend polls ``GET /recommendations/scan/status`` for progress.

    Pass ``sync=true`` to run the scan inline and return the result directly
    in the response (handy when background tasks are unreliable on the host).
    """
    from titan_x.services.recommendation_scan_service import (
        get_scan_status,
        run_background_scan,
        run_universe_load,
    )

    async def _run() -> None:
        await run_universe_load(session_factory)
        await run_background_scan(session_factory, max_age_minutes=max_age_minutes, limit=limit)

    if sync:
        was_running = get_scan_status().get("running", False)
        try:
            await _run()
        except Exception:  # noqa: BLE001
            # The error is already recorded in _scan_state["last_error"].
            pass
        # If another scan was already running, ours returned immediately
        # without results - wait for that one to finish instead.
        import asyncio as _asyncio

        for _ in range(150):
            if not get_scan_status().get("running", False):
                break
            await _asyncio.sleep(1)
        status = get_scan_status()
        # Ensure we always return a proper response structure with all required fields
        last = status.get("last")
        if last is None:
            last = {
                "started": True,
                "universe": 0,
                "scanned": 0,
                "stored": 0,
                "insufficient_data": 0,
                "no_trade": 0,
                "failed": 0,
                "skipped_fresh": 0,
                "used_fallback_universe": False,
                "finished_at": datetime.now(timezone.utc).isoformat(),
            }
        return {
            "last": last,
            "last_error": status.get("last_error"),
            "running": status.get("running", False),
        }

    async def _background() -> None:
        try:
            await _run()
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
        total=total, skip=offset, limit=limit,
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
        total=total, skip=offset, limit=limit,
    )


@router.get("/recommendations/analyze/{symbol}")
async def analyze_symbol(
    symbol: str,
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_user),
):
    """Run the full 6-pillar AI recommendation engine for a single symbol and
    return the complete, explainable analysis (signal, probability, entry /
    target / stop, model agreement and per-pillar breakdown)."""
    symbol = symbol.upper()
    engine = AIRecommendationEngine()

    provider = YahooFinanceProvider()
    try:
        points = await provider.get_historical_prices(symbol, synthetic_ok=False)
    except Exception:  # noqa: BLE001
        points = None
    finally:
        await provider.close()

    if not points:
        raise HTTPException(404, f"No price data available for symbol '{symbol}'")
    bars = bars_from_records(points)

    # Fundamentals (latest available metrics for the symbol)
    fund_rows = (
        await session.execute(
            select(FundamentalMetric).where(FundamentalMetric.symbol == symbol)
        )
    ).scalars().all()
    fundamentals = fundamentals_from_records(list(fund_rows))

    # Sector + breadth context
    sector_ctx: dict = {}
    breadth_ctx: dict = {}
    company = (
        await session.execute(select(Company).where(Company.symbol == symbol))
    ).scalar_one_or_none()
    if company and company.sector:
        sp = (
            await session.execute(
                select(SectorPerformance)
                .where(SectorPerformance.sector == company.sector)
                .order_by(SectorPerformance.as_of_date.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if sp:
            sector_ctx = {
                "momentum_score": sp.momentum_score or 50.0,
                "relative_strength": sp.relative_strength or 50.0,
            }
    breadth = (
        await session.execute(select(MarketBreadth).order_by(MarketBreadth.trade_date.desc()).limit(1))
    ).scalar_one_or_none()
    if breadth:
        adv = breadth.advancing / breadth.declining if breadth.declining and breadth.declining > 0 else 1.0
        breadth_ctx = {
            "index_strength_score": breadth.index_strength_score or 50.0,
            "adv_decl_ratio": adv,
        }

    rec = engine.build(
        symbol, bars,
        fundamentals=fundamentals,
        sector_ctx=sector_ctx, breadth_ctx=breadth_ctx,
    )
    rec["data_points"] = len(points)
    return {
        "symbol": symbol,
        "recommendation": {
            "signal": rec["signal"],
            "direction": rec["direction"],
            "score": rec["score"],
            "confidence": rec["confidence"],
            "calibrated_probability": rec["calibrated_probability"],
            "conviction": rec["conviction"],
            "entry_price": rec["entry_price"],
            "price_target": rec["price_target"],
            "stop_price": rec["stop_price"],
            "risk_reward": rec["risk_reward"],
            "holding_period_days": rec["holding_period_days"],
            "expected_return_pct": rec["expected_return_pct"],
            "risk_level": rec["risk_level"],
            "no_trade": rec["no_trade"],
            "rejection_reasons": rec["rejection_reasons"],
            "evidence": rec["evidence"],
            "caution": rec["caution"],
            "as_of_date": rec["as_of_date"],
            "data_points": rec["data_points"],
        },
        "explainability": rec["explainability"],
    }


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
        "signal": r.signal,
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
