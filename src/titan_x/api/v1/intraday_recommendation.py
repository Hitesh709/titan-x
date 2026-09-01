from __future__ import annotations
import asyncio
import json
from datetime import date, datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker
from titan_x.api import deps
from titan_x.api.deps import get_app_session_factory
from titan_x.models.company import Company
from titan_x.models.recommendation import Recommendation
from titan_x.models.user import User
from titan_x.services.ai_recommendation_engine import bars_from_records
from titan_x.services.recommendation_scan_service import get_scan_status, run_background_scan
from titan_x.services.recommendation_service import RecommendationService
from titan_x.services.technical_strength_engine import score_technical_strength
from titan_x.infrastructure.market_data_providers import YahooFinanceProvider

router=APIRouter(tags=["intraday-recommendations"])
SCAN_SEGMENTS=10
SYMBOL_CONCURRENCY_PER_SEGMENT=5
_cache_lock=asyncio.Lock()
_cache_state={"running":False,"started_at":None,"finished_at":None,"universe":0,"scanned":0,"successful":0,"failed":0,"segment_progress":{},"last_error":None}
_intraday_cache=[]

async def _intraday_segment(symbols, segment_id):
    provider=YahooFinanceProvider(); sem=asyncio.Semaphore(SYMBOL_CONCURRENCY_PER_SEGMENT)
    start=date.today()-timedelta(days=5); end=date.today()
    async def one(s):
        async with sem:
            try:
                p=await provider.get_historical_prices(s,interval="5m",start=start,end=end,synthetic_ok=False)
                if len(p)<30:return None
                t=await asyncio.to_thread(score_technical_strength,bars_from_records(p),mode="intraday")
                q=await provider.get_quote(s)
                return {"symbol":s.split(".")[0],"yahoo_symbol":s,"signal":t.label,"direction":t.direction,"score":round(t.score,2),"confidence":round(t.score,2),"current_price":q.get("last_price"),"change":q.get("change"),"change_percent":q.get("change_percent"),"factors":t.factors,"evidence":t.evidence,"data_points":len(p),"source":"yahoo","segment_id":segment_id}
            except Exception:return None
    try:return [x for x in await asyncio.gather(*(one(s) for s in symbols)) if x]
    finally:await provider.close()

async def _symbols(session):
    rows=(await session.execute(select(Company.symbol,Company.exchange).where(Company.status=="active").where(Company.exchange.in_(["NSE","BSE"])).order_by(Company.exchange,Company.symbol))).all()
    suffix={"NSE":"NS","BSE":"BO"}
    return [f"{str(symbol).upper()}.{suffix.get(str(exchange).upper(),'NS')}" for symbol,exchange in rows if symbol]

async def _full_universe(session):return await _symbols(session)

async def _load_persisted_cache(session, limit=100):
    rows=(await session.execute(select(Recommendation).where(Recommendation.status=="active",Recommendation.recommendation_type=="intraday",Recommendation.source=="yahoo").order_by(Recommendation.generated_at.desc(),Recommendation.score.desc()).limit(limit))).scalars().all()
    result=[]
    for r in rows:
        metadata={}
        try: metadata=json.loads(r.metadata_json or "{}")
        except Exception: pass
        result.append({"id":r.id,"symbol":r.symbol,"yahoo_symbol":metadata.get("yahoo_symbol"),"signal":r.signal,"direction":r.direction,"score":r.score,"confidence":r.confidence,"current_price":r.current_price,"price_target":r.price_target,"risk_level":r.risk_level,"timeframe":r.timeframe,"reasoning":r.reasoning,"source":"yahoo","generated_at":r.generated_at.isoformat() if r.generated_at else None,"factors":metadata.get("factors"),"evidence":metadata.get("evidence"),"data_points":metadata.get("data_points"),"segment_id":metadata.get("segment_id")})
    result.sort(key=lambda x:(x.get("score") or 0),reverse=True)
    return result

async def _persist_scan_results(session_factory:async_sessionmaker, results):
    async with session_factory() as session:
        await session.execute(update(Recommendation).where(Recommendation.status=="active",Recommendation.recommendation_type=="intraday",Recommendation.source=="yahoo").values(status="superseded"))
        service=RecommendationService(session)
        for item in results:
            metadata={"yahoo_symbol":item.get("yahoo_symbol"),"segment_id":item.get("segment_id"),"factors":item.get("factors"),"evidence":item.get("evidence"),"data_points":item.get("data_points")}
            await service.create_recommendation(symbol=item["symbol"],direction=item["direction"],signal=item["signal"],confidence=item["confidence"],current_price=item.get("current_price"),timeframe="intraday",reasoning="; ".join(item.get("evidence") or []),recommendation_type="intraday",score=item["score"],source="yahoo",metadata_json=json.dumps(metadata,default=str))
        await session.commit()

async def _run_cached_scan(symbols, session_factory):
    global _intraday_cache
    if _cache_lock.locked():return {"started":False,"reason":"A full-market intraday scan is already running"}
    async with _cache_lock:
        _cache_state.update({"running":True,"started_at":datetime.now(timezone.utc).isoformat(),"finished_at":None,"universe":len(symbols),"scanned":0,"successful":0,"failed":0,"segment_progress":{str(i):"queued" for i in range(1,SCAN_SEGMENTS+1)},"last_error":None})
        try:
            segments=[symbols[i::SCAN_SEGMENTS] for i in range(SCAN_SEGMENTS)]
            async def run_segment(chunk,segment_id):
                try:
                    out=await _intraday_segment(chunk,segment_id); _cache_state["scanned"]+=len(chunk); _cache_state["successful"]+=len(out); _cache_state["segment_progress"][str(segment_id)]="completed"; return out
                except Exception as exc:
                    _cache_state["scanned"]+=len(chunk); _cache_state["failed"]+=len(chunk); _cache_state["segment_progress"][str(segment_id)]=f"failed: {exc}"; return []
            parts=await asyncio.gather(*(run_segment(chunk,i+1) for i,chunk in enumerate(segments)))
            results=[item for part in parts for item in part]; results.sort(key=lambda x:x["score"],reverse=True)
            await _persist_scan_results(session_factory,results)
            _intraday_cache=results; _cache_state["finished_at"]=datetime.now(timezone.utc).isoformat()
            return {"started":True,"universe":len(symbols),"scanned":len(symbols),"successful":len(results),"failed":_cache_state["failed"],"cache_count":len(results),"provider":"yahoo","persisted":True}
        except Exception as exc:_cache_state["last_error"]=str(exc); raise
        finally:_cache_state["running"]=False

@router.get("/recommendations/intraday")
async def intraday_recommendations(segment:str=Query("equity",pattern=r"^(equity|fno)$"),limit:int=Query(20,ge=1,le=100),session=Depends(deps.get_session),session_factory=Depends(get_app_session_factory),_:User=Depends(deps.get_current_active_user)):
    if segment=="fno":raise HTTPException(400,"F&O universe is not enabled yet; use equity")
    symbols=await _full_universe(session)
    if not symbols:raise HTTPException(503,"No active Indian equity symbols available")
    if not _intraday_cache:_intraday_cache.extend(await _load_persisted_cache(session,100))
    if not _intraday_cache and not _cache_state["running"]:asyncio.create_task(_run_cached_scan(symbols,session_factory))
    return {"recommendations":_intraday_cache[:limit],"count":min(limit,len(_intraday_cache)),"universe_scanned":len(symbols),"scan_segments":SCAN_SEGMENTS,"cache_ready":bool(_intraday_cache),"scan_running":_cache_state["running"],"persistent_cache":True,"provider":"yahoo","live":True}

@router.post("/recommendations/intraday/refresh")
async def refresh_intraday_recommendations(segment:str=Query("equity",pattern=r"^(equity|fno)$"),session=Depends(deps.get_session),session_factory=Depends(get_app_session_factory),_:User=Depends(deps.get_current_active_user)):
    if segment=="fno":raise HTTPException(400,"F&O universe is not enabled yet; use equity")
    symbols=await _full_universe(session)
    if not symbols:raise HTTPException(503,"No active Indian equity symbols available")
    if _cache_state["running"]:return {"started":False,"reason":"A full-market intraday scan is already running",**_cache_state}
    asyncio.create_task(_run_cached_scan(symbols,session_factory)); return {"started":True,"universe":len(symbols),"scan_segments":SCAN_SEGMENTS,"provider":"yahoo","persistent_cache":True,"message":"Full-market scan started in background; results will be persisted"}

@router.get("/recommendations/intraday/status")
async def intraday_scan_status(session=Depends(deps.get_session),_:User=Depends(deps.get_current_active_user)):
    if not _intraday_cache:_intraday_cache.extend(await _load_persisted_cache(session,100))
    return {"provider":"yahoo","scan_segments":SCAN_SEGMENTS,"cache_count":len(_intraday_cache),"persistent_cache":True,**_cache_state}

@router.get("/recommendations/strict")
async def strict_recommendations(mode:str=Query("delivery",pattern=r"^(delivery|intraday)$"),segment:str=Query("equity",pattern=r"^(equity|fno)$"),limit:int=Query(20,ge=1,le=100),session_factory=Depends(get_app_session_factory),_:User=Depends(deps.get_current_active_user)):
    if segment=="fno":raise HTTPException(400,"F&O universe is not enabled yet; use equity")
    if mode=="intraday":
        async with session_factory() as s:
            symbols=await _full_universe(s)
            if not _intraday_cache:_intraday_cache.extend(await _load_persisted_cache(s,100))
        if not _intraday_cache and not _cache_state["running"]:asyncio.create_task(_run_cached_scan(symbols,session_factory))
        return {"recommendations":_intraday_cache[:limit],"count":min(limit,len(_intraday_cache)),"universe_scanned":len(symbols),"scan_segments":SCAN_SEGMENTS,"mode":mode,"cache_ready":bool(_intraday_cache),"scan_running":_cache_state["running"],"persistent_cache":True,"provider":"yahoo","live":True}
    result=await run_background_scan(session_factory,max_age_minutes=0,limit=None)
    async with session_factory() as s:
        items=await RecommendationService(s).get_top_recommendations(limit=limit,status="active")
        r=[{"id":x.id,"symbol":x.symbol,"direction":x.direction,"signal":x.signal,"score":x.score,"confidence":x.confidence,"current_price":x.current_price,"price_target":x.price_target,"risk_level":x.risk_level,"source":"yahoo"} for x in items]
    return {"recommendations":r,"count":len(r),"mode":mode,"segment":segment,"provider":"yahoo","scan":result}

@router.get("/recommendations/strict/status")
async def strict_scan_status(mode:str=Query("delivery",pattern=r"^(delivery|intraday)$"),segment:str=Query("equity",pattern=r"^(equity|fno)$"),_:User=Depends(deps.get_current_active_user)):
    return {"mode":mode,"segment":segment,"provider":"yahoo","intraday_cache":_cache_state,"delivery_scan":get_scan_status()}
