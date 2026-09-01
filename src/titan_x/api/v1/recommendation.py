from datetime import datetime, timezone
import json
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from starlette.background import BackgroundTasks

from titan_x.api import deps
from titan_x.api.deps import get_app_session_factory
from titan_x.api.schemas import PaginatedResponse
from titan_x.models.company import Company
from titan_x.models.fundamental import FundamentalMetric
from titan_x.models.market_breadth import MarketBreadth
from titan_x.models.sector import SectorPerformance
from titan_x.models.user import User
from titan_x.services.ai_recommendation_engine import AIRecommendationEngine, bars_from_records, fundamentals_from_records
from titan_x.services.market_data_service import MarketDataService
from titan_x.services.recommendation_service import RecommendationService

router = APIRouter(tags=["recommendations"])
SORTABLE_COLUMNS = {"symbol", "direction", "signal", "confidence", "current_price", "price_target", "score", "risk_level", "predicted_return_pct", "generated_at"}

async def _live_prices(session, items):
    symbols = list(dict.fromkeys(str(r.symbol).upper() for r in items if getattr(r, "symbol", None)))
    if not symbols:
        return {}
    try:
        response = await MarketDataService(session).get_quotes(symbols)
        return {str(q["symbol"]).upper(): float(q["last_price"]) for q in response.get("quotes", []) if q.get("last_price") is not None}
    except Exception:
        return {}

@router.get("/recommendations")
async def list_recommendations(symbol: str | None = None, direction: str | None = None, status: str | None = None, recommendation_type: str | None = None, timeframe: str | None = None, min_confidence: float | None = None, min_score: float | None = None, source: str | None = None, risk_level: str | None = None, decision: str | None = None, outcome: str | None = None, sort_by: str = "generated_at", sort_desc: bool = True, limit: int = Query(50, le=200), offset: int = Query(0, ge=0), session=Depends(deps.get_session), _: User = Depends(deps.get_current_active_user)):
    if sort_by not in SORTABLE_COLUMNS:
        raise HTTPException(422, f"Unsupported sort_by '{sort_by}'")
    svc = RecommendationService(session)
    items = await svc.list_recommendations(symbol=symbol, direction=direction, status=status, recommendation_type=recommendation_type, timeframe=timeframe, min_confidence=min_confidence, min_score=min_score, source=source, risk_level=risk_level, decision=decision, outcome=outcome, sort_by=sort_by, sort_desc=sort_desc, limit=limit, offset=offset)
    total = await svc.count_recommendations(symbol=symbol, direction=direction, status=status)
    live = await _live_prices(session, items)
    return PaginatedResponse(items=[_rec_dict(r, live.get(str(r.symbol).upper())) for r in items], total=total, skip=offset, limit=limit)

@router.get("/recommendations/top")
async def get_top_recommendations(limit: int = Query(10, le=50), status: str = "active", min_score: float | None = None, session=Depends(deps.get_session), _: User = Depends(deps.get_current_active_user)):
    items = await RecommendationService(session).get_top_recommendations(limit=limit, status=status, min_score=min_score)
    live = await _live_prices(session, items)
    return {"recommendations": [_rec_dict(r, live.get(str(r.symbol).upper())) for r in items], "count": len(items)}

@router.get("/recommendations/scan/status")
async def scan_status(_: User = Depends(deps.get_current_active_user)):
    from titan_x.services.recommendation_scan_service import get_scan_status
    return get_scan_status()

@router.post("/recommendations/scan")
async def trigger_scan(background_tasks: BackgroundTasks, max_age_minutes: int | None = Query(60, ge=0), limit: int | None = Query(None, ge=1, le=2302), sync: bool = Query(False), session_factory=Depends(get_app_session_factory), _: User = Depends(deps.get_current_active_user)):
    from titan_x.services.recommendation_scan_service import get_scan_status, run_background_scan, run_universe_load
    async def run():
        await run_universe_load(session_factory)
        return await run_background_scan(session_factory, max_age_minutes=max_age_minutes, limit=limit)
    if sync:
        try:
            result = await run()
        except Exception as exc:
            raise HTTPException(503, f"Recommendation scan failed: {exc}") from exc
        return {"last": result, "last_error": get_scan_status().get("last_error"), "running": False}
    async def background():
        try:
            await run()
        except Exception as exc:
            import structlog
            structlog.get_logger("recommendation.scan").error("background_scan_failed", error=str(exc))
    background_tasks.add_task(background)
    return {"started": True, "max_age_minutes": max_age_minutes, "limit": limit}

@router.get("/recommendations/history")
async def get_recommendation_history(symbol: str = Query(...), limit: int = Query(50, le=200), offset: int = Query(0, ge=0), session=Depends(deps.get_session), _: User = Depends(deps.get_current_active_user)):
    svc = RecommendationService(session)
    items = await svc.get_recommendation_history(symbol, limit, offset)
    total = await svc.count_recommendations(symbol=symbol)
    live = await _live_prices(session, items)
    return PaginatedResponse(items=[_rec_dict(r, live.get(str(r.symbol).upper())) for r in items], total=total, skip=offset, limit=limit)

@router.get("/recommendations/{symbol}")
async def get_recommendations_by_symbol(symbol: str, status: str | None = "active", limit: int = Query(20, le=100), offset: int = Query(0, ge=0), session=Depends(deps.get_session), _: User = Depends(deps.get_current_active_user)):
    svc = RecommendationService(session)
    items = await svc.get_recommendations_by_symbol(symbol, status, limit, offset)
    total = await svc.count_recommendations(symbol=symbol, status=status)
    live = await _live_prices(session, items)
    return PaginatedResponse(items=[_rec_dict(r, live.get(str(r.symbol).upper())) for r in items], total=total, skip=offset, limit=limit)

@router.get("/recommendations/analyze/{symbol}")
async def analyze_symbol(symbol: str, session=Depends(deps.get_session), _: User = Depends(deps.get_current_active_user)):
    symbol = symbol.upper()
    provider = None
    try:
        from titan_x.infrastructure.market_data_providers import YahooFinanceProvider
        provider = YahooFinanceProvider()
        points = await provider.get_historical_prices(symbol, interval="1d", synthetic_ok=False)
        if not points:
            raise HTTPException(404, f"No Yahoo historical data for '{symbol}'")
        bars = bars_from_records(points)
        fund_rows = (await session.execute(select(FundamentalMetric).where(FundamentalMetric.symbol == symbol))).scalars().all()
        fundamentals = fundamentals_from_records(list(fund_rows))
        company = (await session.execute(select(Company).where(Company.symbol == symbol))).scalar_one_or_none()
        sector_ctx = {}
        if company and company.sector:
            sp = (await session.execute(select(SectorPerformance).where(SectorPerformance.sector == company.sector).order_by(SectorPerformance.as_of_date.desc()).limit(1))).scalar_one_or_none()
            if sp:
                sector_ctx = {"momentum_score": sp.momentum_score or 50.0, "relative_strength": sp.relative_strength or 50.0}
        breadth_ctx = {}
        breadth = (await session.execute(select(MarketBreadth).order_by(MarketBreadth.trade_date.desc()).limit(1))).scalar_one_or_none()
        if breadth:
            breadth_ctx = {"index_strength_score": breadth.index_strength_score or 50.0, "adv_decl_ratio": breadth.advancing / breadth.declining if breadth.declining else 1.0}
        rec = AIRecommendationEngine().build(symbol, bars, fundamentals=fundamentals, sector_ctx=sector_ctx, breadth_ctx=breadth_ctx)
        quote = await MarketDataService(session).get_quote(symbol)
        live_price = float(quote["last_price"])
        rec["entry_price"] = live_price
        return {"symbol": symbol, "recommendation": {k: rec.get(k) for k in ("signal", "direction", "score", "confidence", "calibrated_probability", "conviction", "price_target", "stop_price", "risk_reward", "holding_period_days", "expected_return_pct", "risk_level", "no_trade", "rejection_reasons", "evidence", "caution", "as_of_date") } | {"entry_price": live_price, "data_points": len(points)}, "explainability": rec.get("explainability")}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, f"Yahoo recommendation analysis unavailable: {exc}") from exc
    finally:
        if provider is not None:
            await provider.close()

@router.patch("/recommendations/{rec_id}/decision")
async def set_decision(rec_id: int, decision: str = Query(...), decision_reason: str | None = None, session=Depends(deps.get_session), _: User = Depends(deps.get_current_active_user)):
    rec = await RecommendationService(session).set_decision(rec_id, decision, decision_reason)
    if not rec: raise HTTPException(404, "Recommendation not found")
    return _rec_dict(rec)

@router.patch("/recommendations/{rec_id}/outcome")
async def set_outcome(rec_id: int, outcome: str = Query(...), actual_outcome_pnl: float | None = None, outcome_details: str | None = None, session=Depends(deps.get_session), _: User = Depends(deps.get_current_active_user)):
    rec = await RecommendationService(session).set_outcome(rec_id, outcome, actual_outcome_pnl, outcome_details)
    if not rec: raise HTTPException(404, "Recommendation not found")
    return _rec_dict(rec)

def _rec_dict(r, live_price=None):
    return {"id": r.id, "symbol": r.symbol, "direction": r.direction, "signal": r.signal, "confidence": r.confidence, "price_target": r.price_target, "current_price": live_price if live_price is not None else r.current_price, "timeframe": r.timeframe, "reasoning": r.reasoning, "recommendation_type": r.recommendation_type, "status": r.status, "score": r.score, "risk_level": r.risk_level, "predicted_return_pct": r.predicted_return_pct, "source": r.source, "metadata_json": r.metadata_json, "inputs_json": r.inputs_json, "model_version_id": r.model_version_id, "model_version_label": r.model_version_label, "decision": r.decision, "decision_reason": r.decision_reason, "decided_at": r.decided_at.isoformat() if r.decided_at else None, "outcome": r.outcome, "actual_outcome_pnl": r.actual_outcome_pnl, "outcome_details": r.outcome_details, "resolved_at": r.resolved_at.isoformat() if r.resolved_at else None, "generated_at": r.generated_at.isoformat() if r.generated_at else None, "expires_at": r.expires_at.isoformat() if r.expires_at else None, "created_at": r.created_at.isoformat() if r.created_at else None}
