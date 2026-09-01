import asyncio
import time
from datetime import date, timedelta
from typing import Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from titan_x.infrastructure.market_data_providers import get_market_data_provider
from titan_x.models.company import Company
from titan_x.models.price import DailyPrice

_quote_cache: dict[str, tuple[float, dict]] = {}
_QUOTE_CACHE_TTL_SECONDS = 4.0

class MarketDataService:
    def __init__(self, session: AsyncSession): self.session = session
    def _resolve_provider(self, provider_name: str | None) -> str:
        if provider_name and provider_name.lower().strip() not in {"default", "yahoo"}: raise ValueError("Only Yahoo Finance is supported")
        return "yahoo"
    def _provider(self, provider_name: str = "yahoo", api_key: str | None = None): return get_market_data_provider("yahoo", api_key)
    async def fetch_and_store_historical(self, symbol: str, provider_name: str | None = None, api_key: str | None = None, start: date | None = None, end: date | None = None) -> dict:
        provider=self._provider(); symbol=symbol.upper()
        try: points=await provider.get_historical_prices(symbol, interval="1d", start=start, end=end, synthetic_ok=False)
        finally: await provider.close()
        company=(await self.session.execute(select(Company).where(Company.symbol==symbol))).scalar_one_or_none(); inserted=skipped=0
        for p in points:
            exists=(await self.session.execute(select(DailyPrice).where(DailyPrice.symbol==symbol,DailyPrice.trade_date==p.trade_date))).scalar_one_or_none()
            if exists: skipped+=1; continue
            self.session.add(DailyPrice(symbol=symbol,trade_date=p.trade_date,open=p.open,high=p.high,low=p.low,close=p.close,volume=p.volume)); inserted+=1
        if company is None:
            self.session.add(Company(symbol=symbol,company_name=symbol,isin="IN"+symbol[:10],exchange="NSE",sector="Unknown",status="active"))
        await self.session.flush()
        return {"symbol":symbol,"provider":"yahoo","inserted":inserted,"skipped":skipped,"total_fetched":len(points)}
    async def ingest_universe(self,symbols:list[str],provider_name:str|None=None,api_key:str|None=None,start:date|None=None,end:date|None=None,max_concurrency:int=1)->dict:
        results=[]
        for s in symbols:
            try: results.append(await self.fetch_and_store_historical(s,"yahoo",start=start,end=end))
            except Exception as e: results.append({"symbol":s.upper(),"provider":"yahoo","error":str(e)})
        errors=[r for r in results if "error" in r]
        return {"provider":"yahoo","symbols_requested":len(symbols),"symbols_ok":len(results)-len(errors),"symbols_failed":len(errors),"inserted_total":sum(r.get("inserted",0) for r in results),"errors":errors}
    async def get_quote(self,symbol:str,provider_name:str|None=None,api_key:str|None=None)->dict:
        p=self._provider()
        try:
            q=await p.get_quote(symbol.upper()); return self._normalize_quote_change(q)
        finally: await p.close()
    @staticmethod
    def _normalize_quote_change(q:dict)->dict:
        last,prev=q.get("last_price"),q.get("prev_close")
        if q.get("change") is None and last is not None and prev not in (None,0): q["change"]=float(last)-float(prev)
        if q.get("change_percent") is None and q.get("change") is not None and prev not in (None,0): q["change_percent"]=float(q["change"])/float(prev)*100
        return q
    async def get_quotes(self,symbols:list[str])->dict:
        symbols=list(dict.fromkeys(s.upper().replace(".NS","").replace(".BO","") for s in symbols if s.strip()))[:100]; now=time.monotonic(); out=[]; todo=[]
        for s in symbols:
            hit=_quote_cache.get(s)
            if hit and now-hit[0]<_QUOTE_CACHE_TTL_SECONDS and hit[1].get("last_price") is not None: out.append(hit[1])
            else: todo.append(s)
        p=self._provider()
        try:
            for start in range(0,len(todo),10):
                batch=todo[start:start+10]; results=await asyncio.gather(*(self._fetch_quote_with_retry(p,s) for s in batch),return_exceptions=True)
                for s,r in zip(batch,results):
                    if isinstance(r,dict) and r.get("last_price") is not None: self._normalize_quote_change(r); _quote_cache[s]=(time.monotonic(),r); out.append(r)
                if start+10<len(todo): await asyncio.sleep(.4)
        finally: await p.close()
        order={s:i for i,s in enumerate(symbols)}; out.sort(key=lambda q:order.get(str(q.get("symbol","")).replace(".NS","").replace(".BO",""),9999))
        return {"quotes":out,"count":len(out),"requested":len(symbols),"live":True,"provider":"yahoo","source":"yahoo"}
    async def _fetch_quote_with_retry(self,p,s):
        for i in range(3):
            try:return await p.get_quote(s)
            except Exception:
                if i<2: await asyncio.sleep(.8*(i+1))
        return None
    async def get_company_profile(self,symbol:str,provider_name:str|None=None,api_key:str|None=None)->dict:
        symbol=symbol.upper(); c=(await self.session.execute(select(Company).where(Company.symbol==symbol))).scalar_one_or_none()
        if c:return {"symbol":c.symbol,"name":c.company_name,"isin":c.isin,"exchange":c.exchange,"sector":c.sector,"industry":c.industry,"market_cap":c.market_cap,"currency":"INR","description":c.description,"website":c.website,"listing_date":c.listing_date.isoformat() if c.listing_date else None}
        p=self._provider()
        try:return await p.get_company_profile(symbol)
        finally:await p.close()
    async def get_history(self,symbol:str,provider_name:str|None=None,api_key:str|None=None)->dict:
        rows=(await self.session.execute(select(DailyPrice).where(DailyPrice.symbol==symbol.upper()).order_by(DailyPrice.trade_date.asc()))).scalars().all()
        return {"symbol":symbol.upper(),"points":[{"trade_date":p.trade_date.isoformat(),"open":p.open,"high":p.high,"low":p.low,"close":p.close,"volume":p.volume} for p in rows]}
    def get_available_providers(self)->list[str]: return ["yahoo"]

async def load_active_symbols(session:AsyncSession,symbol:str|None=None,limit:int=100)->list[str]:
    if symbol:return [symbol.strip().upper()]
    result=await session.execute(select(Company.symbol).where(Company.status=="active").limit(limit)); return [r[0] for r in result.all()]

async def run_market_data_ingestion(session_factory:Any,symbol:str|None=None,provider_name:str|None=None,max_symbols:int=100,lookback_days:int=365)->dict:
    async with session_factory() as session:
        symbols=await load_active_symbols(session,symbol=symbol,limit=max_symbols); result=await MarketDataService(session).ingest_universe(symbols,"yahoo",start=date.today()-timedelta(days=lookback_days)); await session.commit(); return result
