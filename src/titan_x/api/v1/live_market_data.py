from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from titan_x.api.dependencies import get_current_active_user
from titan_x.core.config import get_settings
from titan_x.infrastructure.market_data_providers import get_market_data_provider
from titan_x.models.user import User
from titan_x.services.live_market_data_engine import LiveMarketDataEngine

router = APIRouter(prefix="/live-market", tags=["live-market"])


def _engine() -> LiveMarketDataEngine:
    settings = get_settings()
    provider_name = settings.market_data_provider
    provider = get_market_data_provider(provider_name)

    async def fetch(symbol: str) -> dict:
        return await provider.get_quote(symbol, synthetic_ok=provider_name.lower() == "mock")

    return LiveMarketDataEngine(fetch)


@router.post("/poll")
async def poll_live_quotes(
    user: Annotated[User, Depends(get_current_active_user)],
    symbols: str = Query(..., description="Comma-separated symbols, maximum 100"),
):
    syms = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    if not syms or len(syms) > 100:
        raise HTTPException(status_code=400, detail="Provide 1-100 comma-separated symbols")
    return await _engine().poll_once(syms)


@router.get("/health")
async def live_market_health(
    user: Annotated[User, Depends(get_current_active_user)],
    symbols: str = Query(..., description="Comma-separated symbols, maximum 100"),
):
    syms = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    if not syms or len(syms) > 100:
        raise HTTPException(status_code=400, detail="Provide 1-100 comma-separated symbols")
    return _engine().health(syms)
