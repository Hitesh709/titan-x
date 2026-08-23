from datetime import date
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.api.dependencies import get_current_active_user, request_session
from titan_x.infrastructure.market_data_providers import YahooFinanceProvider
from titan_x.models.company import Company
from titan_x.models.user import User
from titan_x.services.candle_service import CandleService
from titan_x.services.market_data_service import MarketDataService

router = APIRouter(prefix="/market-data", tags=["market-data"])


async def get_market_data_service(
    session: Annotated[AsyncSession, Depends(request_session)],
) -> MarketDataService:
    return MarketDataService(session)


@router.get("/providers")
async def list_providers(
    svc: Annotated[MarketDataService, Depends(get_market_data_service)],
):
    return {"providers": svc.get_available_providers()}


@router.post("/fetch/{symbol}")
async def fetch_historical(
    symbol: str,
    user: Annotated[User, Depends(get_current_active_user)],
    svc: Annotated[MarketDataService, Depends(get_market_data_service)],
    provider: str = Query(None),
    api_key: str | None = Query(None),
    start: date | None = Query(None),
    end: date | None = Query(None),
):
    try:
        result = await svc.fetch_and_store_historical(
            symbol=symbol,
            provider_name=provider,
            api_key=api_key,
            start=start,
            end=end,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Market data fetch failed: {str(e)}")
    return result


@router.get("/quotes")
async def get_batch_quotes(
    symbols: str,
    user: Annotated[User, Depends(get_current_active_user)],
    svc: Annotated[MarketDataService, Depends(get_market_data_service)],
):
    syms = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    if not syms or len(syms) > 100:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Provide 1-100 comma-separated symbols")
    try:
        return await svc.get_quotes(syms)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Quote fetch failed: {str(e)}")


@router.get("/market-caps")
async def get_batch_market_caps(
    symbols: str,
    user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[AsyncSession, Depends(request_session)],
):
    """Return market capitalisation in INR for up to 100 NSE symbols."""
    syms = [s.strip().upper().replace(".NS", "") for s in symbols.split(",") if s.strip()]
    syms = list(dict.fromkeys(syms))
    if not syms or len(syms) > 100:
        raise HTTPException(status_code=400, detail="Provide 1-100 comma-separated symbols")

    local_rows = await session.execute(select(Company.symbol, Company.market_cap).where(Company.symbol.in_(syms)))
    caps: dict[str, float | None] = {symbol.upper(): value for symbol, value in local_rows.all()}

    yahoo_symbols = ",".join(f"{symbol}.NS" for symbol in syms)
    headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126 Safari/537.36"}
    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True, headers=headers) as client:
            response = await client.get(
                "https://query1.finance.yahoo.com/v7/finance/quote",
                params={"symbols": yahoo_symbols},
            )
            response.raise_for_status()
            payload = response.json()
            rows = ((payload.get("quoteResponse") or {}).get("result") or [])
            for row in rows:
                yahoo_symbol = str(row.get("symbol", ""))
                symbol = yahoo_symbol.replace(".NS", "").replace(".BO", "").upper()
                market_cap = row.get("marketCap")
                if symbol in caps and isinstance(market_cap, (int, float)) and market_cap > 0:
                    caps[symbol] = float(market_cap)
    except Exception:
        pass

    return {
        "caps": [{"symbol": symbol, "market_cap": caps.get(symbol)} for symbol in syms],
        "currency": "INR",
        "source": "yahoo_finance_or_local_company",
    }


@router.get("/candles/{symbol}")
async def get_candles(
    symbol: str,
    interval: str = Query("1d", description="5m, 15m, 30m, 1h, 4h, 1d, 1w, 1mo"),
    period: str = Query("max", description="1d, 5d, 1mo, 3mo, 6mo, ytd, 1y, 5y, 10y, max"),
    user: Annotated[User, Depends(get_current_active_user)] = None,
):
    """Return real OHLCV candles for the selected interval and history window."""
    service = CandleService()
    try:
        source_interval = "60m" if interval == "4h" else interval
        candles = await service.get_candles(symbol, source_interval, period)
        if interval == "4h":
            candles = service.resample_4h(candles)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Candle data unavailable for {symbol.upper()}: {exc}") from exc

    return {
        "symbol": service.normalize_symbol(symbol),
        "interval": interval,
        "period": period,
        "source": "yahoo_finance",
        "candles": candles,
    }


@router.get("/quote/{symbol}")
async def get_quote(
    symbol: str,
    user: Annotated[User, Depends(get_current_active_user)],
    svc: Annotated[MarketDataService, Depends(get_market_data_service)],
    provider: str = Query(None),
    api_key: str | None = Query(None),
):
    try:
        return await svc.get_quote(symbol, provider_name=provider, api_key=api_key)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Quote fetch failed: {str(e)}")


@router.get("/history/{symbol}")
async def get_stock_history(
    symbol: str,
    user: Annotated[User, Depends(get_current_active_user)],
):
    """Return real historical daily prices; never demo/synthetic prices."""
    provider = YahooFinanceProvider()
    try:
        points = await provider.get_historical_prices(symbol.upper(), synthetic_ok=False)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Live historical market data unavailable for {symbol.upper()}: {exc}",
        )
    finally:
        await provider.close()

    if not points:
        raise HTTPException(status_code=404, detail=f"No real historical data available for {symbol.upper()}")

    return {
        "symbol": symbol.upper(),
        "source": "yahoo_finance",
        "points": [
            {
                "trade_date": p.trade_date.isoformat(),
                "open": p.open,
                "high": p.high,
                "low": p.low,
                "close": p.close,
                "volume": p.volume,
            }
            for p in points
        ],
    }


@router.get("/profile/{symbol}")
async def get_company_profile(
    symbol: str,
    user: Annotated[User, Depends(get_current_active_user)],
    svc: Annotated[MarketDataService, Depends(get_market_data_service)],
    provider: str = Query(None),
    api_key: str | None = Query(None),
):
    try:
        result = await svc.get_company_profile(symbol, provider_name=provider, api_key=api_key)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return result
