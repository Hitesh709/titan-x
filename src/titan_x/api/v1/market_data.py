from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.api.dependencies import get_current_active_user, request_session
from titan_x.infrastructure.jugaad_nse_provider import JugaadNSEProvider
from titan_x.models.company import Company
from titan_x.models.user import User
from titan_x.services.market_data_service import MarketDataService

router = APIRouter(prefix="/market-data", tags=["market-data"])


async def get_market_data_service(
    session: Annotated[AsyncSession, Depends(request_session)],
) -> MarketDataService:
    return MarketDataService(session)


@router.get("/providers")
async def list_providers(svc: Annotated[MarketDataService, Depends(get_market_data_service)]):
    return {"providers": svc.get_available_providers(), "default": "jugaad"}


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
        return await svc.fetch_and_store_historical(symbol=symbol, provider_name=provider, api_key=api_key, start=start, end=end)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Market data fetch failed: {str(e)}") from e


@router.get("/quotes")
async def get_batch_quotes(
    symbols: str,
    user: Annotated[User, Depends(get_current_active_user)],
    svc: Annotated[MarketDataService, Depends(get_market_data_service)],
):
    syms = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    if not syms or len(syms) > 100:
        raise HTTPException(status_code=400, detail="Provide 1-100 comma-separated symbols")
    try:
        return await svc.get_quotes(syms)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Quote fetch failed: {str(e)}") from e


@router.get("/market-caps")
async def get_batch_market_caps(
    symbols: str,
    user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[AsyncSession, Depends(request_session)],
):
    """Return stored market caps only; never silently call a second provider."""
    syms = list(dict.fromkeys(s.strip().upper().replace(".NS", "") for s in symbols.split(",") if s.strip()))
    if not syms or len(syms) > 100:
        raise HTTPException(status_code=400, detail="Provide 1-100 comma-separated symbols")
    local_rows = await session.execute(select(Company.symbol, Company.market_cap).where(Company.symbol.in_(syms)))
    caps = {symbol.upper(): value for symbol, value in local_rows.all()}
    return {"caps": [{"symbol": symbol, "market_cap": caps.get(symbol)} for symbol in syms], "currency": "INR", "source": "titanx_company_data"}


@router.get("/candles/{symbol}")
async def get_candles(
    symbol: str,
    user: Annotated[User, Depends(get_current_active_user)],
    interval: str = Query("1d", description="5m, 15m, 30m, 1h, 4h, 1d, 1w, 1mo"),
    period: str = Query("5d", description="1d, 5d, 1mo, 3mo, 6mo, 1y, max"),
):
    """Real NSE OHLC/candle data. No Yahoo or synthetic fallback."""
    service = JugaadNSEProvider()
    try:
        source_interval = "60m" if interval == "4h" else interval
        candles = await service.get_candles(symbol, source_interval, period)
        if interval == "4h":
            from titan_x.services.candle_service import CandleService

            candles = CandleService.resample_4h(candles)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"NSE candle data unavailable for {symbol.upper()}: {exc}") from exc
    finally:
        await service.close()
    if not candles:
        raise HTTPException(status_code=404, detail=f"No real NSE candle data available for {symbol.upper()}")
    return {"symbol": symbol.strip().upper(), "interval": interval, "period": period, "source": "jugaad-data/NSE", "candles": candles}


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
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Quote fetch failed: {str(e)}") from e


@router.get("/history/{symbol}")
async def get_stock_history(symbol: str, user: Annotated[User, Depends(get_current_active_user)]):
    provider = JugaadNSEProvider()
    try:
        points = await provider.get_historical_prices(symbol.upper(), interval="1d", synthetic_ok=False, start=date.today().replace(year=date.today().year - 1), end=date.today())
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Live NSE historical market data unavailable for {symbol.upper()}: {exc}") from exc
    finally:
        await provider.close()
    if not points:
        raise HTTPException(status_code=404, detail=f"No real historical data available for {symbol.upper()}")
    return {"symbol": symbol.upper(), "source": "jugaad-data/NSE", "points": [{"trade_date": p.trade_date.isoformat(), "open": p.open, "high": p.high, "low": p.low, "close": p.close, "volume": p.volume} for p in points]}


@router.get("/profile/{symbol}")
async def get_company_profile(
    symbol: str,
    user: Annotated[User, Depends(get_current_active_user)],
    svc: Annotated[MarketDataService, Depends(get_market_data_service)],
    provider: str = Query(None),
    api_key: str | None = Query(None),
):
    try:
        return await svc.get_company_profile(symbol, provider_name=provider, api_key=api_key)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Profile fetch failed: {str(e)}") from e
