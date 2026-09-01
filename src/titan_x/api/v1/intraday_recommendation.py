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
async def _intraday(symbols,limit):
    provider=YahooFinanceProvider(); sem=asyncio.Semaphore(5); start=date.today()-timedelta(days=5); end=date.today()
    async def one(s):
        async with sem:
            try:
                p=await provider.get_historical_prices(s,interval="5m",start=start,end=end,synthetic_ok=False)
                if len(p)<30:return None
                t=await asyncio.to_thread(score_technical_strength,bars_from_records(p),mode="intraday"); q=await provider.get_quote(s)
                return {"symbol":s,"signal":t.label,"direction":t.direction,"score":round(t.score,2),"confidence":round(t.score,2),"current_price":q.get("last_price"),"change":q.get("change"),"change_percent":q.get("change_percent"),"factors":t.factors,"evidence":t.evidence,"data_points":len(p),"source":"yahoo"}
            except Exception:return None
    try:
        r=await asyncio.gather(*(one(s) for s in symbols)); r=[x for x in r if x]; r.sort(key=lambda x:x["score"],reverse=True); return r[:limit]
    finally:await provider.close()
async def _symbols(session):
    rows=(await session.execute(select(Company.symbol).where(Company.status=="active").where(Company.exchange.in_(["NSE","BSE"])).order_by(Company.symbol))).all()
    return [str(r[0]).upper() for r in rows if r[0]]
async def _full_universe(session):
    return await _symbols(session)
@router.get("/recommendations/intraday")
async def intraday_recommendations(segment:str=Query("equity",pattern=r"^(equity|fno)$"),limit:int=Query(20,ge=1,le=100),session=Depends(deps.get_session),_:User=Depends(deps.get_current_active_user)):
    symbols=await _full_universe(session)
    if not symbols:raise HTTPException(503,"No active Indian equity symbols available")
    r=await _intraday(symbols,limit); return {"recommendations":r,"count":len(r),"universe_scanned":len(symbols),"segment":segment,"provider":"yahoo","live":True}
@router.get("/recommendations/strict")
async def strict_recommendations(mode:str=Query("delivery",pattern=r"^(delivery|intraday)$"),segment:str=Query("equity",pattern=r"^(equity|fno)$"),limit:int=Query(20,ge=1,le=100),session_factory=Depends(get_app_session_factory),_:User=Depends(deps.get_current_active_user)):
    if mode=="intraday":
        async with session_factory() as s:symbols=await _full_universe(s)
        r=await _intraday(symbols,limit); return {"recommendations":r,"count":len(r),"universe_scanned":len(symbols),"mode":mode,"segment":segment,"provider":"yahoo","live":True}
    result=await run_background_scan(session_factory,max_age_minutes=0,limit=None)
    async with session_factory() as s:
        from titan_x.services.recommendation_service import RecommendationService
        items=await RecommendationService(s).get_top_recommendations(limit=limit,status="active")
        r=[{"id":x.id,"symbol":x.symbol,"direction":x.direction,"signal":x.signal,"score":x.score,"confidence":x.confidence,"current_price":x.current_price,"price_target":x.price_target,"risk_level":x.risk_level,"source":"yahoo"} for x in items]
    return {"recommendations":r,"count":len(r),"mode":mode,"segment":segment,"provider":"yahoo","scan":result}
@router.get("/recommendations/strict/status")
async def strict_scan_status(mode:str=Query("delivery",pattern=r"^(delivery|intraday)$"),segment:str=Query("equity",pattern=r"^(equity|fno)$"),_:User=Depends(deps.get_current_active_user)):
    return {"mode":mode,"segment":segment,"provider":"yahoo",**get_scan_status()}
