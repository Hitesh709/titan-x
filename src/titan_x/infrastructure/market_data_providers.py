from __future__ import annotations
import asyncio
from abc import ABC, abstractmethod
from datetime import date, datetime, timedelta, time as dt_time, timezone
import httpx
YAHOO_USER_AGENT="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36"
class MarketDataPoint:
    def __init__(self,symbol:str,trade_date:date,open:float,high:float,low:float,close:float,volume:int): self.symbol=symbol; self.trade_date=trade_date; self.open=open; self.high=high; self.low=low; self.close=close; self.volume=volume
class MarketDataProvider(ABC):
    @abstractmethod
    async def get_historical_prices(self,symbol:str,interval:str="1d",start:date|None=None,end:date|None=None,synthetic_ok:bool=False)->list[MarketDataPoint]: ...
    @abstractmethod
    async def get_quote(self,symbol:str)->dict: ...
    @abstractmethod
    async def get_company_profile(self,symbol:str)->dict: ...
class YahooFinanceProvider(MarketDataProvider):
    BASE_URL="https://query1.finance.yahoo.com/v8/finance/chart"
    def __init__(self,api_key:str|None=None): self._client=httpx.AsyncClient(headers={"User-Agent":YAHOO_USER_AGENT},timeout=20,follow_redirects=True); self._sem=asyncio.Semaphore(5)
    @staticmethod
    def _normalize_symbol(symbol:str)->str:
        s=symbol.strip().upper()
        if "." in s or s.startswith("^"): return s
        return s+".NS"
    async def _get(self,symbol:str,params:dict)->dict:
        last=None
        for host in ("query1.finance.yahoo.com","query2.finance.yahoo.com"):
            try:
                async with self._sem:
                    r=await self._client.get(f"https://{host}/v8/finance/chart/{self._normalize_symbol(symbol)}",params=params); r.raise_for_status(); return r.json()
            except Exception as e:last=e
        raise last or RuntimeError("Yahoo request failed")
    async def get_historical_prices(self,symbol:str,interval:str="1d",start:date|None=None,end:date|None=None,synthetic_ok:bool=False)->list[MarketDataPoint]:
        p={"interval":interval}
        if start is not None:
            p["period1"]=int(datetime.combine(start,dt_time.min).replace(tzinfo=timezone.utc).timestamp()); p["period2"]=int(datetime.combine(end or date.today()+timedelta(days=1),dt_time.min).replace(tzinfo=timezone.utc).timestamp())
        else:p["range"]="5d" if interval in {"5m","15m","30m"} else "1y"
        data=await self._get(symbol,p); result=(data.get("chart") or {}).get("result")
        if not result: raise ValueError(f"No Yahoo data for {symbol}")
        c=result[0]; ts=c.get("timestamp") or []; q=((c.get("indicators") or {}).get("quote") or [{}])[0]; out=[]
        for i,t in enumerate(ts):
            a=q.get("close",[]); close=a[i] if i<len(a) else None
            if close is None:continue
            def val(k):
                x=q.get(k,[]); return float(x[i]) if i<len(x) and x[i] is not None else float(close)
            v=q.get("volume",[]); out.append(MarketDataPoint(symbol.upper(),datetime.fromtimestamp(t,timezone.utc).date(),val("open"),val("high"),val("low"),float(close),int(v[i] or 0) if i<len(v) else 0))
        return out
    async def get_quote(self,symbol:str)->dict:
        data=await self._get(symbol,{"range":"5d","interval":"1d"}); result=(data.get("chart") or {}).get("result")
        if not result:raise ValueError(f"No Yahoo quote for {symbol}")
        m=result[0].get("meta") or {}; return {"symbol":m.get("symbol",self._normalize_symbol(symbol)),"last_price":m.get("regularMarketPrice"),"prev_close":m.get("chartPreviousClose"),"change":None,"change_percent":None,"volume":m.get("regularMarketVolume"),"day_high":m.get("regularMarketDayHigh"),"day_low":m.get("regularMarketDayLow"),"currency":m.get("currency"),"name":m.get("longName") or m.get("shortName"),"exchange":m.get("fullExchangeName"),"timestamp":datetime.now(timezone.utc).isoformat()}
    async def get_company_profile(self,symbol:str)->dict:
        q=await self.get_quote(symbol); s=self._normalize_symbol(symbol); return {"symbol":symbol.upper(),"name":q.get("name") or symbol.upper(),"sector":None,"industry":None,"market_cap":None,"exchange":"NSE" if s.endswith(".NS") else "BSE" if s.endswith(".BO") else q.get("exchange"),"currency":q.get("currency") or "INR"}
    async def close(self):await self._client.aclose()
def get_market_data_provider(provider_name:str="yahoo",api_key:str|None=None)->MarketDataProvider:
    if provider_name.lower()!="yahoo":raise ValueError("Only Yahoo Finance is supported")
    return YahooFinanceProvider(api_key)
