from __future__ import annotations
import asyncio
from datetime import date, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from titan_x.api import deps
from titan_x.api.deps import get_app_session_factory
from titan_x.models.company import Company
from titan_x.models.user import User
from titan_x.services.ai_recommendation_engine import bars_from_records
from titan_x.services.recommendation_scan_service import get_scan_status, run_background_scan
from titan_x.services.technical_strength_engine import score_technical_strength
from titan_x.infrastructure.market_data_providers import YahooFinanceProvider

router=APIRouter(tags=["intraday-recommendations"])

async def _intraday(symbols, limit):
    provider=YahooFinanceProvider(); out=[]; sem=asyncio.Semaphore(5); start=date.today()-timedelta(days=5); end=date.today()
    async def one(symbol):
        async with sem:
            try:
                points=await provider.get_historical_prices(symbol,interval="5m",start=start,end=end,synthetic_ok=False)
                if len(points)<30:return None
                tech=await asyncio.to_thread(score_technical_strength,bars_from_records(points),mode="intraday")
                q=await provider.get_quote(symbol)
                return {"symbol":symbol,"signal":tech.label,"direction":tech.direction,"score":round(tech.score,2),"confidence":round(tech.score,2),"current_price":q.get("last_price"),"change":q.get("change"),"change_percent":q.get("change_percent"),"factors":tech.factors,"evidence":tech.evidence,"data_points":len(points),"source":"yahoo"}
            except Exception as e:return None
    try:
        rows=await asyncio.gather(*(one(s) for s in symbols)); out=[r for r in rows if r]; out.sort(key=lambda x:x["score"],reverse=True); return out[:limit]
    finally: await provider.close()

async def _symbols(session,limit):
    rows=(await session.execute(select(Company.symbol).where(Company.status=="active").where(Company.exchange.in_(["NSE","BSE"])).order_by(Company.symbol).limit(limit))).all()
    return [str(r[0]).upper() for r in rows if r[0]]

@router.get("/recommendations/intraday")
async def intraday_recommendations(segment:str=Query("equity",pattern=r"^(equity|fno)$"),limit:int=Query(20,ge=1,le=100),session=Depends(deps.get_session),_:User=Depends(deps.get_current_active_user)):
    symbols=await _symbols(session,limit)
    if not symbols: raise HTTPException(503,"No active Indian equity symbols available")
    return {"recommendations":await _intraday(symbols,limit),"segment":segment,"provider":"yahoo","live":True}

@router.get("/recommendations/strict")
async def strict_recommendations(mode:str=Query("delivery",pattern=r"^(delivery|intraday)$"),segment:str=Query("equity",pattern=r"^(equity|fno)$"),limit:int=Query(20,ge=1,le=100),session_factory=Depends(get_app_session_factory),_:User=Depends(deps.get_current_active_user)):
    if mode=="intraday":
        async with session_factory() as session: symbols=await _symbols(session,limit)
        return {"recommendations":await _intraday(symbols,limit),"mode":mode,"segment":segment,"provider":"yahoo","live":True}
    result=await run_background_scan(session_factory,max_age_minutes=0,limit=None)
    async with session_factory() as session:
        from titan_x.services.recommendation_service import RecommendationService
        items=await RecommendationService(session).get_top_recommendations(limit=limit,status="active")
        return {"recommendations":[{"id":r.id,"symbol":r.symbol,"direction":r.direction,"signal":r.signal,"score":r.score,"confidence":r.confidence,"current_price":r.current_price,"price_target":r.price_target,"risk_level":r.risk_level,"source":"yahoo"} for r in items],"count":len(items),"mode":mode,"segment":segment,"provider":"yahoo","scan":result}

@router.get("/recommendations/strict/status")
async def strict_scan_status(mode:str=Query("delivery",pattern=r"^(delivery|intraday)$"),segment:str=Query("equity",pattern=r"^(equity|fno)$"),_:User=Depends(deps.get_current_active_user)):
    return {"mode":mode,"segment":segment,"provider":"yahoo",**get_scan_status()}
