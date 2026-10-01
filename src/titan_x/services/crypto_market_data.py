"""Provider-neutral public crypto market data.

Binance is preferred when reachable. OKX is the primary fallback and Bybit is the final fallback so the UI is not
coupled to a browser/client-region response from a single exchange.
No private keys are used by this service.
"""
from __future__ import annotations

from typing import Any
import httpx

BINANCE="https://api.binance.com"
OKX="https://www.okx.com"
BYBIT="https://api.bybit.com"

INTERVALS={"1m":"1","3m":"3","5m":"5","15m":"15","30m":"30","1h":"60","2h":"120","4h":"240","6h":"360","12h":"720","1d":"D","1w":"W","1M":"M"}

async def _get(url:str, params:dict[str,Any]|None=None, timeout:float=8) -> Any:
    async with httpx.AsyncClient(timeout=timeout, headers={"User-Agent":"Titan-X-Crypto/1.0"}) as c:
        r=await c.get(url,params=params)
        r.raise_for_status()
        return r.json()

def _rows(rows:list[list[Any]]) -> list[dict[str,float]]:
    return [{"time":float(x[0]),"open":float(x[1]),"high":float(x[2]),"low":float(x[3]),"close":float(x[4]),"volume":float(x[5])} for x in rows]

async def candles(symbol:str, interval:str="15m", limit:int=220) -> tuple[list[dict[str,float]],str]:
    symbol=symbol.upper()
    try:
        data=await _get(f"{BINANCE}/api/v3/klines",{"symbol":symbol,"interval":interval,"limit":limit})
        if isinstance(data,list) and data:
            return _rows(data),"binance"
    except Exception:
        pass
    okx_bar={"1m":"1m","3m":"3m","5m":"5m","15m":"15m","30m":"30m","1h":"1H","2h":"2H","4h":"4H","6h":"6H","12h":"12H","1d":"1D","1w":"1W","1M":"1M"}.get(interval,interval)
    try:
        data=await _get(f"{OKX}/api/v5/market/candles",{"instId":symbol.replace("USDT","-USDT"),"bar":okx_bar,"limit":min(limit,1440)})
        rows=list(reversed(data.get("data",[])))
        if rows:
            return [{"time":float(x[0]),"open":float(x[1]),"high":float(x[2]),"low":float(x[3]),"close":float(x[4]),"volume":float(x[5])} for x in rows],"okx"
    except Exception:
        pass
    bybit_interval=INTERVALS.get(interval,interval)
    data=await _get(f"{BYBIT}/v5/market/kline",{"category":"spot","symbol":symbol,"interval":bybit_interval,"limit":min(limit,1000)})
    rows=list(reversed(data.get("result",{}).get("list",[])))
    if not rows:
        raise RuntimeError(f"No market candles for {symbol}")
    return [{"time":float(x[0]),"open":float(x[1]),"high":float(x[2]),"low":float(x[3]),"close":float(x[4]),"volume":float(x[5])} for x in rows],"bybit"

async def ticker(symbol:str) -> tuple[dict[str,Any],str]:
    symbol=symbol.upper()
    try:
        data=await _get(f"{BINANCE}/api/v3/ticker/24hr",{"symbol":symbol})
        return {"symbol":symbol,"lastPrice":float(data["lastPrice"]),"priceChangePercent":float(data["priceChangePercent"]),"quoteVolume":float(data.get("quoteVolume",0)),"highPrice":float(data.get("highPrice",0)),"lowPrice":float(data.get("lowPrice",0))},"binance"
    except Exception:
        try:
            data=await _get(f"{OKX}/api/v5/market/ticker",{"instId":symbol.replace("USDT","-USDT")})
            row=(data.get("data") or [None])[0]
            if not row: raise RuntimeError("No OKX ticker")
            last=float(row["last"]); open24=float(row.get("open24h") or 0)
            return {"symbol":symbol,"lastPrice":last,"priceChangePercent":((last-open24)/open24*100 if open24 else 0),"quoteVolume":float(row.get("volCcy24h") or 0),"highPrice":float(row.get("high24h") or 0),"lowPrice":float(row.get("low24h") or 0)},"okx"
        except Exception:
            data=await _get(f"{BYBIT}/v5/market/tickers",{"category":"spot","symbol":symbol})
            row=(data.get("result",{}).get("list") or [None])[0]
            if not row: raise RuntimeError(f"No ticker for {symbol}")
            return {"symbol":symbol,"lastPrice":float(row["lastPrice"]),"priceChangePercent":float(row.get("price24hPcnt",0))*100,"quoteVolume":float(row.get("turnover24h",0)),"highPrice":float(row.get("highPrice24h",0)),"lowPrice":float(row.get("lowPrice24h",0))},"bybit"

async def tickers(limit:int=250) -> tuple[list[dict[str,Any]],str]:
    try:
        data=await _get(f"{BINANCE}/api/v3/ticker/24hr")
        rows=[x for x in data if x.get("symbol","").endswith("USDT")]
        rows.sort(key=lambda x:float(x.get("quoteVolume",0)),reverse=True)
        return [{"symbol":x["symbol"],"lastPrice":float(x["lastPrice"]),"priceChangePercent":float(x["priceChangePercent"]),"quoteVolume":float(x.get("quoteVolume",0)),"highPrice":float(x.get("highPrice",0)),"lowPrice":float(x.get("lowPrice",0))} for x in rows[:limit]],"binance"
    except Exception:
        try:
            data=await _get(f"{OKX}/api/v5/market/tickers",{"instType":"SPOT"})
            rows=[]
            for x in data.get("data",[]):
                inst=str(x.get("instId",""))
                if not inst.endswith("-USDT"): continue
                last=float(x.get("last") or 0); open24=float(x.get("open24h") or 0)
                rows.append({"symbol":inst.replace("-USDT","USDT"),"lastPrice":last,"priceChangePercent":((last-open24)/open24*100 if open24 else 0),"quoteVolume":float(x.get("volCcy24h") or 0),"highPrice":float(x.get("high24h") or 0),"lowPrice":float(x.get("low24h") or 0)})
            rows.sort(key=lambda x:x["quoteVolume"],reverse=True)
            if rows: return rows[:limit],"okx"
        except Exception:
            pass
        data=await _get(f"{BYBIT}/v5/market/tickers",{"category":"spot"})
        rows=[]
        for x in data.get("result",{}).get("list",[]):
            if not x.get("symbol","").endswith("USDT"): continue
            rows.append({"symbol":x["symbol"],"lastPrice":float(x["lastPrice"]),"priceChangePercent":float(x.get("price24hPcnt",0))*100,"quoteVolume":float(x.get("turnover24h",0)),"highPrice":float(x.get("highPrice24h",0)),"lowPrice":float(x.get("lowPrice24h",0))})
        rows.sort(key=lambda x:x["quoteVolume"],reverse=True)
        return rows[:limit],"bybit"

async def universe(search:str="",limit:int=250) -> dict[str,Any]:
    rows,provider=await tickers(limit=1000)
    q=search.strip().upper()
    if q: rows=[x for x in rows if q in x["symbol"]]
    return {"provider":provider,"count":len(rows[:limit]),"symbols":rows[:limit]}

async def market_overview() -> dict[str,Any]:
    rows,provider=await tickers(limit=500)
    active=[x for x in rows if x["quoteVolume"]>0]
    gainers=sorted(active,key=lambda x:x["priceChangePercent"],reverse=True)[:10]
    losers=sorted(active,key=lambda x:x["priceChangePercent"])[:10]
    breadth={"up":sum(x["priceChangePercent"]>0 for x in active),"down":sum(x["priceChangePercent"]<0 for x in active),"flat":sum(x["priceChangePercent"]==0 for x in active)}
    return {"provider":provider,"assets":len(active),"gainers":gainers,"losers":losers,"breadth":breadth,"volume":sum(x["quoteVolume"] for x in active)}


async def derivatives_overview(limit:int=100) -> dict[str,Any]:
    data=await _get(f"{BYBIT}/v5/market/tickers",{"category":"linear"})
    rows=[]
    for x in data.get("result",{}).get("list",[]):
        if not x.get("symbol","").endswith("USDT"): continue
        rows.append({"symbol":x["symbol"],"lastPrice":float(x["lastPrice"]),"priceChangePercent":float(x.get("price24hPcnt",0))*100,"volume24h":float(x.get("turnover24h",0)),"fundingRate":float(x.get("fundingRate",0) or 0),"openInterest":float(x.get("openInterestValue",0) or 0)})
    rows.sort(key=lambda x:x["volume24h"],reverse=True)
    return {"provider":"bybit","category":"linear","contracts":len(rows),"contracts_top":rows[:limit]}
