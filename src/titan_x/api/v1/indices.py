from datetime import datetime, timezone
import asyncio
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query
from titan_x.api.dependencies import get_current_active_user
from titan_x.infrastructure.market_data_providers import YahooFinanceProvider
from titan_x.models.user import User

router = APIRouter(prefix="/indices", tags=["indices"])
INDEXES = [("NIFTY","NIFTY 50","^NSEI"),("BANKNIFTY","NIFTY Bank","^NSEBANK"),("NIFTYNEXT50","NIFTY Next 50","^NSMIDCP"),("NIFTY100","NIFTY 100","^CNX100"),("NIFTYAUTO","NIFTY Auto","^CNXAUTO"),("NIFTYPHARMA","NIFTY Pharma","^CNXPHARMA"),("NIFTYFMCG","NIFTY FMCG","^CNXFMCG"),("NIFTYIT","NIFTY IT","^CNXIT"),("NIFTYMETAL","NIFTY Metal","^CNXMETAL"),("NIFTYREALTY","NIFTY Realty","^CNXREALTY"),("NIFTYFIN","NIFTY Financial Services","^CNXFIN"),("INDIAVIX","India VIX","^INDIAVIX")]

async def _one(provider, item):
    symbol,name,yahoo = item
    try:
        q = await provider.get_quote(yahoo)
        if q.get("last_price") is None: return None
        return {"symbol":symbol,"name":name,"trade_date":datetime.now(timezone.utc).date().isoformat(),"open":q.get("day_open"),"high":q.get("day_high"),"low":q.get("day_low"),"close":q.get("last_price"),"prev_close":q.get("prev_close"),"change":q.get("change"),"change_pct":q.get("change_percent"),"volume":q.get("volume"),"source":"yahoo"}
    except Exception: return None

@router.get("")
async def list_indices(_: Annotated[User, Depends(get_current_active_user)]):
    provider = YahooFinanceProvider()
    try:
        rows = await asyncio.gather(*[_one(provider,x) for x in INDEXES])
        items = [x for x in rows if x]
        if not items: raise HTTPException(503,"Yahoo index data temporarily unavailable")
        return {"items":items,"source":"yahoo","provider":"yahoo","live":True}
    finally: await provider.close()

@router.get("/{symbol}/history")
async def get_index_history(symbol: str, _: Annotated[User, Depends(get_current_active_user)], range: str = Query("1W", pattern=r"^(1W|1M|3M|6M|YTD|1Y)$")):
    item = next((x for x in INDEXES if x[0] == symbol.upper()), None)
    if not item: raise HTTPException(404,f"Unknown index {symbol}")
    provider = YahooFinanceProvider()
    try:
        points = await provider.get_historical_prices(item[2], interval="1d", synthetic_ok=False)
        return {"symbol":item[0],"range":range,"source":"yahoo","points":[{"trade_date":p.trade_date.isoformat(),"open":p.open,"high":p.high,"low":p.low,"close":p.close,"volume":p.volume} for p in points]}
    except Exception as e: raise HTTPException(502,f"Yahoo index history unavailable: {e}") from e
    finally: await provider.close()

@router.get("/{symbol}/performance")
async def get_index_performance(symbol: str, _: Annotated[User, Depends(get_current_active_user)]):
    item = next((x for x in INDEXES if x[0] == symbol.upper()), None)
    if not item: raise HTTPException(404,f"Unknown index {symbol}")
    provider = YahooFinanceProvider()
    try:
        points = await provider.get_historical_prices(item[2], interval="1d", synthetic_ok=False)
        if not points: raise HTTPException(503,"No Yahoo index history")
        last=points[-1].close
        def pct(n): return round((last/points[-n].close-1)*100,2) if len(points)>=n else None
        return {"symbol":item[0],"trade_date":points[-1].trade_date.isoformat(),"close":last,"periods":{"1M":pct(22),"1Y":pct(252)},"source":"yahoo"}
    except HTTPException: raise
    except Exception as e: raise HTTPException(502,f"Yahoo index performance unavailable: {e}") from e
    finally: await provider.close()
