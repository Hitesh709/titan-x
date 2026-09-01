from __future__ import annotations
import asyncio
from datetime import date, datetime, timedelta, timezone
from typing import Any
import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from titan_x.models.company import Company
from titan_x.models.market_breadth import MarketBreadth
from titan_x.models.recommendation import Recommendation
from titan_x.models.sector import SectorPerformance
from titan_x.services.ai_recommendation_engine import AIRecommendationEngine, bars_from_records
from titan_x.services.recommendation_service import RecommendationService
from titan_x.services.technical_strength_engine import score_technical_strength
from titan_x.infrastructure.market_data_providers import YahooFinanceProvider

logger=structlog.get_logger(__name__)
FAST_GATE_SCORE=70.0
SOURCE="yahoo"
RECOMMENDATION_TYPE="LIVE_SCAN"
_scan_lock=asyncio.Lock()
_scan_state={"running":False,"last":None,"last_error":None,"last_universe":None}

def get_scan_status(): return dict(_scan_state)

class RecommendationScanService:
    def __init__(self,session:AsyncSession): self.session=session; self.engine=AIRecommendationEngine()
    async def get_active_symbols(self,limit=None):
        rows=(await self.session.execute(select(Company.symbol,Company.exchange).where(Company.status=="active").order_by(Company.symbol))).all(); seen=set(); out=[]
        for symbol,exchange in rows:
            s=str(symbol).upper() if symbol else ""
            if s and s not in seen and str(exchange or "NSE").upper() in {"NSE","BSE"}: seen.add(s); out.append(s)
        return out[:limit] if limit else out
    async def _sector_ctx(self):
        rows=(await self.session.execute(select(SectorPerformance.sector,SectorPerformance.momentum_score,SectorPerformance.relative_strength).order_by(SectorPerformance.sector,SectorPerformance.as_of_date.desc()))).all(); out={}
        for sec,m,r in rows:
            if sec not in out: out[sec]={"momentum_score":m if m is not None else 50.0,"relative_strength":r if r is not None else 50.0}
        return out
    async def _breadth_ctx(self):
        b=(await self.session.execute(select(MarketBreadth).order_by(MarketBreadth.trade_date.desc()).limit(1))).scalar_one_or_none()
        return {"index_strength_score":b.index_strength_score or 50.0,"adv_decl_ratio":b.advancing/b.declining if b and b.declining else 1.0} if b else None
    async def _stale(self,symbols,max_age):
        if max_age is None or max_age<=0:return set(symbols)
        cutoff=datetime.now(timezone.utc).replace(tzinfo=None)-timedelta(minutes=max_age)
        rows=(await self.session.execute(select(Recommendation.symbol).where(Recommendation.symbol.in_(symbols),Recommendation.status=="active",Recommendation.generated_at>=cutoff))).all()
        return {s for s in symbols if s not in {r[0] for r in rows}}
    async def scan_all(self,max_age_minutes=60,concurrency=8,chunk_size=50,limit=None):
        if _scan_lock.locked(): return {"started":False,"reason":"A scan is already running"}
        async with _scan_lock:
            _scan_state.update(running=True,last_error=None)
            started=time.perf_counter() if False else None
            try:return await self._scan(max_age_minutes,concurrency,limit)
            except Exception as e:_scan_state["last_error"]=str(e); logger.exception("scan_failed",error=str(e)); raise
            finally:_scan_state["running"]=False
    async def _scan(self,max_age_minutes,concurrency,limit):
        symbols=await self.get_active_symbols(limit); stale=sorted(await self._stale(symbols,max_age_minutes)); sector=await self._sector_ctx(); breadth=await self._breadth_ctx(); exchange={}
        rows=(await self.session.execute(select(Company.symbol,Company.exchange).where(Company.symbol.in_(stale)))).all(); exchange={str(s).upper():str(e or "NSE").upper() for s,e in rows}
        provider=YahooFinanceProvider(); sem=asyncio.Semaphore(max(1,min(concurrency,8))); market={}; errors=[]
        async def one(s):
            async with sem:
                try:
                    points=await provider.get_historical_prices(s,interval="1d",start=date.today()-timedelta(days=400),synthetic_ok=False)
                    if len(points)>=30: market[s]=points
                    else: errors.append(f"{s}: insufficient Yahoo history")
                except Exception as e: errors.append(f"{s}: Yahoo data unavailable ({e})")
        try: await asyncio.gather(*(one(s) for s in stale))
        finally: await provider.close()
        fast_passed=stored=no_trade=failed=0; svc=RecommendationService(self.session); engine=self.engine
        for s,points in market.items():
            try:
                bars=bars_from_records(points); intraday,delivery=await asyncio.gather(asyncio.to_thread(score_technical_strength,bars,mode="intraday"),asyncio.to_thread(score_technical_strength,bars,mode="delivery")); score=max(intraday.score,delivery.score)
                if score<FAST_GATE_SCORE: no_trade+=1; continue
                fast_passed+=1
                rec=engine.build(s,bars,sector_ctx=sector.get(next((c[1] for c in rows if str(c[0]).upper()==s),"") or ""),breadth_ctx=breadth); rec["data_points"]=len(points); rec["fast_technical_gate"]={"threshold":FAST_GATE_SCORE,"intraday_score":intraday.score,"delivery_score":delivery.score,"selected_score":score}
                if rec.get("insufficient_data") or rec.get("no_trade"): no_trade+=1; continue
                await self._store(rec,svc); stored+=1
            except Exception as e: failed+=1; logger.warning("scan_symbol_failed",symbol=s,error=str(e))
        await self.session.commit()
        result={"started":True,"universe":len(symbols),"scanned":len(stale),"live_data_symbols":len(market),"fast_gate":FAST_GATE_SCORE,"fast_passed":fast_passed,"deep_scanned":fast_passed,"stored":stored,"insufficient_data":len(stale)-len(market),"no_trade":no_trade,"failed":failed,"batch_failed":0,"skipped_fresh":len(symbols)-len(stale),"first_error":errors[0] if errors else None,"data_quality":{"synthetic_data_used":False,"live_only_fast_gate":True,"provider":"Yahoo Finance"}}
        _scan_state["last"]={**result,"finished_at":datetime.now(timezone.utc).isoformat()}; return result
    async def _store(self,rec,svc):
        await self.session.execute(delete(Recommendation).where(Recommendation.symbol==rec["symbol"]))
        signal=rec["signal"]; direction="BUY" if signal in ("strong_buy","buy") else "SELL" if signal in ("strong_sell","sell") else "HOLD"; now=datetime.now(timezone.utc).replace(tzinfo=None)
        metadata={"signal":signal,"as_of_date":rec.get("as_of_date"),"data_points":rec.get("data_points",0),"evidence":rec.get("evidence"),"caution":rec.get("caution"),"returns":rec.get("returns"),"indicators":rec.get("indicators"),"fast_technical_gate":rec.get("fast_technical_gate")}
        await svc.create_recommendation(symbol=rec["symbol"],direction=direction,signal=signal,confidence=rec["confidence"],price_target=rec["price_target"],current_price=rec["current_price"],timeframe=f"{rec['holding_period_days']} days",reasoning=f"{signal.upper()} recommendation for {rec['symbol']}",recommendation_type=RECOMMENDATION_TYPE,score=rec["score"],risk_level=rec["risk_level"],predicted_return_pct=rec["expected_return_pct"],source=SOURCE,metadata_json=__import__('json').dumps(metadata),status="active",expires_at=now+timedelta(days=1),inputs_json=__import__('json').dumps(rec["factors"]),model_version_label="yahoo-live-v1")

async def run_universe_load(session_factory:async_sessionmaker)->dict[str,Any]:
    async with session_factory() as session:
        rows=(await session.execute(select(Company.symbol).where(Company.status=="active"))).all(); result={"loaded":True,"active_symbols":len(rows)}; _scan_state["last_universe"]=result; return result

async def run_background_scan(session_factory:async_sessionmaker,max_age_minutes=60,limit=None)->dict[str,Any]:
    async with session_factory() as session: return await RecommendationScanService(session).scan_all(max_age_minutes=max_age_minutes,limit=limit)
