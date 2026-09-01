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
SCAN_SEGMENTS=10
SYMBOL_CONCURRENCY_PER_SEGMENT=5

def _yahoo_ticker(symbol:str,exchange:str|None)->str:
    s=str(symbol).strip().upper()
    if "." in s or s.startswith("^"): return s
    return f"{s}.BO" if str(exchange or "NSE").upper()=="BSE" else f"{s}.NS"

def _base_symbol(symbol:str)->str:
    return str(symbol).upper().split(".",1)[0]

async def _intraday_segment(securities, segment_id):
    provider=YahooFinanceProvider()
    async def one(item):
        symbol,exchange=item; ticker=_yahoo_ticker(symbol,exchange)
        try:
            p=await provider.get_historical_prices(ticker,interval="5m",start=date.today()-timedelta(days=5),end=date.today(),synthetic_ok=False)
            if len(p)<30:return None
            t=await asyncio.to_thread(score_technical_strength,bars_from_records(p),mode="intraday")
            q=await provider.get_quote(ticker)
            return {"symbol":_base_symbol(symbol),"exchange":str(exchange).upper(),"yahoo_symbol":ticker,"signal":t.label,"direction":t.direction,"score":round(t.score,2),"confidence":round(t.score,2),"current_price":q.get("last_price"),"change":q.get("change"),"change_percent":q.get("change_percent"),"factors":t.factors,"evidence":t.evidence,"data_points":len(p),"source":"yahoo","segment_id":segment_id}
        except Exception:return None
    return [x for x in await asyncio.gather(*(one(item) for item in securities)) if x]

async def _intraday(securities,limit):
    if not securities:return []
    segments=[securities[i::SCAN_SEGMENTS] for i in range(SCAN_SEGMENTS)]
    results=await asyncio.gather(*(_intraday_segment(chunk,i+1) for i,chunk in enumerate(segments)))
    r=[item for segment in results for item in segment]
    r.sort(key=lambda x:x["score"],reverse=True)
    return r[:limit]

async def _symbols(session):
    rows=(await session.execute(select(Company.symbol,Company.exchange).where(Company.status=="active").where(Company.exchange.in_(["NSE","BSE"])).order_by(Company.symbol,Company.exchange))).all()
    seen=set(); out=[]
    for symbol,exchange in rows:
        key=(_base_symbol(symbol),str(exchange or "NSE").upper())
        if symbol and key not in seen: seen.add(key); out.append((str(symbol).upper(),str(exchange or "NSE").upper()))
    return out

async def _full_universe(session):
    return await _symbols(session)

@router.get("/recommendations/intraday")
async def intraday_recommendations(segment:str=Query("equity",pattern=r"^(equity|fno)$"),limit:int=Query(20,ge=1,le=100),session=Depends(deps.get_session),_:User=Depends(deps.get_current_active_user)):
    if segment=="fno": raise HTTPException(400,"F&O universe is not configured yet; use equity until the official F&O master is added")
    securities=await _full_universe(session)
    if not securities:raise HTTPException(503,"No active Indian equity symbols available")
    r=await _intraday(securities,limit)
    return {"recommendations":r,"count":len(r),"universe_scanned":len(securities),"scan_segments":SCAN_SEGMENTS,"segment":segment,"provider":"yahoo","live":True}

@router.get("/recommendations/strict")
async def strict_recommendations(mode:str=Query("delivery",pattern=r"^(delivery|intraday)$"),segment:str=Query("equity",pattern=r"^(equity|fno)$"),limit:int=Query(20,ge=1,le=100),session_factory=Depends(get_app_session_factory),_:User=Depends(deps.get_current_active_user)):
    if segment=="fno": raise HTTPException(400,"F&O universe is not configured yet; use equity until the official F&O master is added")
    if mode=="intraday":
        async with session_factory() as s:securities=await _full_universe(s)
        r=await _intraday(securities,limit)
        return {"recommendations":r,"count":len(r),"universe_scanned":len(securities),"scan_segments":SCAN_SEGMENTS,"mode":mode,"segment":segment,"provider":"yahoo","live":True}
    result=await run_background_scan(session_factory,max_age_minutes=0,limit=None)
    async with session_factory() as s:
        from titan_x.services.recommendation_service import RecommendationService
        items=await RecommendationService(s).get_top_recommendations(limit=limit,status="active")
        r=[{"id":x.id,"symbol":x.symbol,"direction":x.direction,"signal":x.signal,"score":x.score,"confidence":x.confidence,"current_price":x.current_price,"price_target":x.price_target,"risk_level":x.risk_level,"source":"yahoo"} for x in items]
    return {"recommendations":r,"count":len(r),"mode":mode,"segment":segment,"provider":"yahoo","scan":result}

@router.get("/recommendations/strict/status")
async def strict_scan_status(mode:str=Query("delivery",pattern=r"^(delivery|intraday)$"),segment:str=Query("equity",pattern=r"^(equity|fno)$"),_:User=Depends(deps.get_current_active_user)):
    return {"mode":mode,"segment":segment,"provider":"yahoo",**get_scan_status()}
