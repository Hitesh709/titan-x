from __future__ import annotations

import asyncio
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select

from titan_x.api import deps
from titan_x.api.deps import get_app_session_factory
from titan_x.models.company import Company
from titan_x.models.user import User
from titan_x.services.ai_recommendation_engine import AIRecommendationEngine, bars_from_records
from titan_x.services.market_data_service import MarketDataService
from titan_x.services.recommendation_scan_service import get_scan_status, run_background_scan
from titan_x.services.technical_strength_engine import score_technical_strength

router = APIRouter(tags=["intraday-recommendations"])

@router.get("/recommendations/intraday")
async def intraday_recommendations(segment: str = Query("equity", pattern=r"^(equity|fno)$"), limit: int = Query(20, ge=1, le=100), session=Depends(deps.get_session), _: User = Depends(deps.get_current_active_user)):
    rows = (await session.execute(select(Company.symbol).where(Company.status == "active").where(Company.exchange.in_(["NSE", "BSE"])).order_by(Company.symbol).limit(limit))).all()
    symbols = [str(r[0]).upper() for r in rows if r[0]]
    if not symbols:
        raise HTTPException(503, "No active Indian equity symbols available")
    from titan_x.infrastructure.market_data_providers import YahooFinanceProvider
    provider = YahooFinanceProvider()
    results = []
    try:
        sem = asyncio.Semaphore(5)
        async def one(symbol):
            async with sem:
                try:
                    points = await provider.get_historical_prices(symbol, interval="5m", synthetic_ok=False)
                    if len(points) < 30:
                        return None
                    bars = bars_from_records(points)
                    tech = await asyncio.to_thread(score_technical_strength, bars, mode="intraday")
                    quote = await provider.get_quote(symbol)
                    return {"symbol": symbol, "signal": tech.label, "direction": tech.direction, "score": round(tech.score, 2), "confidence": round(tech.score, 2), "current_price": quote.get("last_price"), "change": quote.get("change"), "change_percent": quote.get("change_percent"), "factors": tech.factors, "evidence": tech.evidence, "data_points": len(points), "source": "yahoo"}
                except Exception as exc:
                    return {"symbol": symbol, "error": str(exc), "source": "yahoo"}
        raw = await asyncio.gather(*(one(s) for s in symbols))
        results = [r for r in raw if r and "error" not in r]
    finally:
        await provider.close()
    results.sort(key=lambda x: x["score"], reverse=True)
    return {"recommendations": results, "count": len(results), "segment": segment, "provider": "yahoo", "live": True}

@router.get("/recommendations/strict")
async def strict_recommendations(mode: str = Query("delivery", pattern=r"^(delivery|intraday)$"), segment: str = Query("equity", pattern=r"^(equity|fno)$"), limit: int = Query(20, ge=1, le=100), session_factory=Depends(get_app_session_factory), _: User = Depends(deps.get_current_active_user)):
    if mode == "intraday":
        # The intraday endpoint is the live 5-minute Yahoo engine; keep strict
        # as a compatibility endpoint and return the same live result shape.
        async with session_factory() as session:
            rows = (await session.execute(select(Company.symbol).where(Company.status == "active").where(Company.exchange.in_(["NSE", "BSE"])).order_by(Company.symbol).limit(limit))).all()
            symbols = [str(r[0]).upper() for r in rows if r[0]]
        from titan_x.infrastructure.market_data_providers import YahooFinanceProvider
        provider = YahooFinanceProvider()
        try:
            out = []
            for symbol in symbols:
                try:
                    points = await provider.get_historical_prices(symbol, interval="5m", synthetic_ok=False)
                    if len(points) < 30: continue
                    tech = await asyncio.to_thread(score_technical_strength, bars_from_records(points), mode="intraday")
                    if tech.score < 70: continue
                    quote = await provider.get_quote(symbol)
                    out.append({"symbol": symbol, "direction": tech.direction, "signal": tech.label, "score": round(tech.score,2), "confidence": round(tech.score,2), "current_price": quote.get("last_price"), "source": "yahoo", "data_points": len(points)})
                except Exception:
                    continue
            out.sort(key=lambda x: x["score"], reverse=True)
            return {"recommendations": out[:limit], "count": len(out[:limit]), "mode": mode, "segment": segment, "provider": "yahoo", "live": True}
        finally:
            await provider.close()
    # Delivery strict scan uses the full Yahoo-only recommendation scanner.
    result = await run_background_scan(session_factory, max_age_minutes=0, limit=None)
    async with session_factory() as session:
        from titan_x.services.recommendation_service import RecommendationService
        items = await RecommendationService(session).get_top_recommendations(limit=limit, status="active")
        return {"recommendations": [{"id": r.id, "symbol": r.symbol, "direction": r.direction, "signal": r.signal, "score": r.score, "confidence": r.confidence, "current_price": r.current_price, "price_target": r.price_target, "risk_level": r.risk_level, "source": r.source} for r in items], "count": len(items), "mode": mode, "segment": segment, "provider": "yahoo", "scan": result}

@router.get("/recommendations/strict/status")
async def strict_scan_status(mode: str = Query("delivery", pattern=r"^(delivery|intraday)$"), segment: str = Query("equity", pattern=r"^(equity|fno)$"), _: User = Depends(deps.get_current_active_user)):
    return {"mode": mode, "segment": segment, "provider": "yahoo", **get_scan_status()}
