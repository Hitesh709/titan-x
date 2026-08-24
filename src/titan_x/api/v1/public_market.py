"""Public live market snapshot used by the unauthenticated TITAN X landing page."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter

router = APIRouter(prefix="/public-market", tags=["public-market"])

_SYMBOLS = {
    "NIFTY 50": "^NSEI",
    "SENSEX": "^BSESN",
    "BANK NIFTY": "^NSEBANK",
    "FINNIFTY": "^CNXFIN",
    "GOLD": "GC=F",
}


def _score(rows: list[dict]) -> tuple[int, str]:
    valid = [r for r in rows if isinstance(r.get("change_pct"), (int, float))]
    if not valid:
        return 50, "Neutral"
    avg = sum(float(r["change_pct"]) for r in valid) / len(valid)
    positive = sum(1 for r in valid if float(r["change_pct"]) > 0)
    # Transparent live momentum score: not a prediction and not a trade signal.
    value = round(max(0, min(100, 50 + avg * 12 + (positive - len(valid) / 2) * 5)))
    if value >= 75:
        regime = "Very Bullish"
    elif value >= 60:
        regime = "Bullish"
    elif value <= 25:
        regime = "Very Bearish"
    elif value <= 40:
        regime = "Bearish"
    else:
        regime = "Neutral"
    return value, regime


@router.get("/snapshot")
async def public_market_snapshot():
    headers = {"User-Agent": "Mozilla/5.0 TITAN-X/1.0"}
    symbols = ",".join(_SYMBOLS.values())
    url = "https://query1.finance.yahoo.com/v7/finance/quote"
    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True, headers=headers) as client:
            response = await client.get(url, params={"symbols": symbols})
            response.raise_for_status()
            result = (response.json().get("quoteResponse") or {}).get("result") or []
        by_symbol = {str(row.get("symbol")): row for row in result}
        markets: list[dict] = []
        for name, yahoo_symbol in _SYMBOLS.items():
            row = by_symbol.get(yahoo_symbol, {})
            price = row.get("regularMarketPrice")
            change = row.get("regularMarketChangePercent")
            markets.append({
                "name": name,
                "symbol": yahoo_symbol,
                "price": float(price) if isinstance(price, (int, float)) else None,
                "change_pct": float(change) if isinstance(change, (int, float)) else None,
            })
        score, regime = _score(markets)
        return {
            "ok": True,
            "source": "Yahoo Finance",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "score": score,
            "regime": regime,
            "markets": markets,
        }
    except Exception as exc:
        return {
            "ok": False,
            "source": "Yahoo Finance",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "score": None,
            "regime": "Market data unavailable",
            "markets": [],
            "error": str(exc),
        }
