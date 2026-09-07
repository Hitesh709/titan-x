from __future__ import annotations

import asyncio
from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from titan_x.api.dependencies import get_current_active_user
from titan_x.infrastructure.market_data_providers import YahooFinanceProvider
from titan_x.models.user import User

router = APIRouter(prefix="/live-market", tags=["live-market"])


async def _fetch_live_quote(symbol: str) -> dict:
    provider = YahooFinanceProvider()
    try:
        quote = await provider.get_quote(symbol)
        end = date.today() + timedelta(days=1)
        points = await provider.get_historical_prices(
            symbol,
            interval="1m",
            start=date.today(),
            end=end,
            synthetic_ok=False,
        )
        valid = [p for p in points if p.close and float(p.close) > 0]
        if valid:
            latest = valid[-1]
            quote["last_price"] = float(latest.close)
            quote["source"] = "YAHOO_INTRADAY_1M"
            quote["live"] = True
        else:
            quote["source"] = "YAHOO_QUOTE"
            quote["live"] = False
        return quote
    finally:
        await provider.close()


@router.get("/quotes")
async def live_quotes(
    _user: Annotated[User, Depends(get_current_active_user)],
    symbols: str = Query(..., description="Comma-separated NSE symbols, maximum 20"),
):
    syms = list(dict.fromkeys(s.strip().upper().replace(".NS", "") for s in symbols.split(",") if s.strip()))
    if not syms or len(syms) > 20:
        raise HTTPException(status_code=400, detail="Provide 1-20 comma-separated symbols")

    results = await asyncio.gather(
        *(_fetch_live_quote(symbol) for symbol in syms),
        return_exceptions=True,
    )
    quotes: list[dict] = []
    errors: list[dict[str, str]] = []
    for symbol, result in zip(syms, results):
        if isinstance(result, Exception):
            errors.append({"symbol": symbol, "error": str(result)})
        elif result.get("last_price") is not None:
            quotes.append(result)
        else:
            errors.append({"symbol": symbol, "error": "No live price returned"})

    return {
        "quotes": quotes,
        "count": len(quotes),
        "requested": len(syms),
        "live": all(q.get("source") == "YAHOO_INTRADAY_1M" for q in quotes) if quotes else False,
        "provider": "yahoo",
        "source": "yahoo_intraday_1m",
        "errors": errors,
    }
