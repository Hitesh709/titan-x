from datetime import date
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from titan_x.api.dependencies import get_current_active_user, request_session
from titan_x.models.company import Company
from titan_x.models.user import User
from titan_x.services.market_data_service import MarketDataService
from titan_x.infrastructure.market_data_providers import YahooFinanceProvider

router = APIRouter(prefix="/market-data", tags=["market-data"])

async def get_market_data_service(session: Annotated[AsyncSession, Depends(request_session)]) -> MarketDataService:
    return MarketDataService(session)

@router.get("/providers")
async def list_providers(_ : Annotated[User, Depends(get_current_active_user)]):
    return {"providers": ["yahoo"], "default": "yahoo"}

@router.post("/fetch/{symbol}")
async def fetch_historical(symbol: str, _ : Annotated[User, Depends(get_current_active_user)], svc: Annotated[MarketDataService, Depends(get_market_data_service)], provider: str = Query("yahoo"), api_key: str | None = Query(None), start: date | None = Query(None), end: date | None = Query(None)):
    if provider.lower() != "yahoo": raise HTTPException(400, "Only Yahoo Finance is supported")
    try: return await svc.fetch_and_store_historical(symbol, provider_name="yahoo", start=start, end=end)
    except Exception as e: raise HTTPException(502, f"Yahoo market data fetch failed: {e}") from e

@router.get("/quotes")
async def get_batch_quotes(symbols: str, _ : Annotated[User, Depends(get_current_active_user)], svc: Annotated[MarketDataService, Depends(get_market_data_service)]):
    syms = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    if not syms or len(syms) > 100: raise HTTPException(400, "Provide 1-100 comma-separated symbols")
    try: return await svc.get_quotes(syms)
    except Exception as e: raise HTTPException(502, f"Yahoo quote fetch failed: {e}") from e

@router.get("/market-caps")
async def get_batch_market_caps(symbols: str, _ : Annotated[User, Depends(get_current_active_user)], session: Annotated[AsyncSession, Depends(request_session)]):
    syms = list(dict.fromkeys(s.strip().upper().replace(".NS", "") for s in symbols.split(",") if s.strip()))
    if not syms or len(syms) > 100: raise HTTPException(400, "Provide 1-100 comma-separated symbols")
    rows = await session.execute(select(Company.symbol, Company.market_cap).where(Company.symbol.in_(syms)))
    caps = {s.upper(): v for s, v in rows.all()}
    return {"caps": [{"symbol": s, "market_cap": caps.get(s)} for s in syms], "currency": "INR", "source": "titanx_company_data"}

@router.get("/candles/{symbol}")
async def get_candles(symbol: str, _ : Annotated[User, Depends(get_current_active_user)], interval: str = Query("1d", pattern=r"^(5m|15m|30m|1h|4h|1d|1wk|1mo)$")):
    provider = YahooFinanceProvider()
    try:
        points = await provider.get_historical_prices(symbol, interval=interval, synthetic_ok=False)
        return {"symbol": symbol.upper(), "interval": interval, "provider": "yahoo", "live": True, "points": [{"trade_date": p.trade_date.isoformat(), "open": p.open, "high": p.high, "low": p.low, "close": p.close, "volume": p.volume} for p in points]}
    except Exception as e: raise HTTPException(502, f"Yahoo candle fetch failed: {e}") from e
    finally: await provider.close()

@router.get("/history/{symbol}")
async def get_history(symbol: str, _ : Annotated[User, Depends(get_current_active_user)], interval: str = Query("1d", pattern=r"^(1d|1wk|1mo)$")):
    provider = YahooFinanceProvider()
    try:
        points = await provider.get_historical_prices(symbol, interval=interval, synthetic_ok=False)
        return {"symbol": symbol.upper(), "interval": interval, "provider": "yahoo", "points": [{"trade_date": p.trade_date.isoformat(), "open": p.open, "high": p.high, "low": p.low, "close": p.close, "volume": p.volume} for p in points]}
    except Exception as e: raise HTTPException(502, f"Yahoo history fetch failed: {e}") from e
    finally: await provider.close()
