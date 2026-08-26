"""Public live index snapshot used by the unauthenticated TITAN X landing page."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter

router = APIRouter(prefix="/public-market", tags=["public-market"])

# Website Market feature is intentionally INDEX-ONLY.
# No individual stocks, commodities, FX or crypto are included.
_INDEXES = {
    "NIFTY 50": ("^NSEI", "India"),
    "SENSEX": ("^BSESN", "India"),
    "BANK NIFTY": ("^NSEBANK", "India"),
    "NIFTY IT": ("^CNXIT", "India"),
    "NIFTY FIN SERVICE": ("^CNXFIN", "India"),
    "NIFTY AUTO": ("^CNXAUTO", "India"),
    "NIFTY PHARMA": ("^CNXPHARMA", "India"),
    "NIFTY FMCG": ("^CNXFMCG", "India"),
    "NIFTY METAL": ("^CNXMETAL", "India"),
    "NIFTY ENERGY": ("^CNXENERGY", "India"),
    "NIFTY REALTY": ("^CNXREALTY", "India"),
    "S&P 500": ("^GSPC", "United States"),
    "NASDAQ COMPOSITE": ("^IXIC", "United States"),
    "DOW JONES": ("^DJI", "United States"),
    "RUSSELL 2000": ("^RUT", "United States"),
    "FTSE 100": ("^FTSE", "United Kingdom"),
    "DAX": ("^GDAXI", "Germany"),
    "CAC 40": ("^FCHI", "France"),
    "NIKKEI 225": ("^N225", "Japan"),
    "HANG SENG": ("^HSI", "Hong Kong"),
    "SHANGHAI COMPOSITE": ("000001.SS", "China"),
    "KOSPI": ("^KS11", "South Korea"),
    "ASX 200": ("^AXJO", "Australia"),
}


def _score(rows: list[dict]) -> tuple[int | None, str]:
    valid = [r for r in rows if isinstance(r.get("change_pct"), (int, float))]
    if not valid:
        return None, "Market data unavailable"
    avg = sum(float(r["change_pct"]) for r in valid) / len(valid)
    positive = sum(1 for r in valid if float(r["change_pct"]) > 0)
    breadth = (positive - (len(valid) - positive)) / len(valid)
    value = round(max(0, min(100, 50 + avg * 18 + breadth * 25)))
    if value >= 75:
        return value, "Very Bullish"
    if value >= 60:
        return value, "Bullish"
    if value <= 25:
        return value, "Very Bearish"
    if value <= 40:
        return value, "Bearish"
    return value, "Neutral"


async def _chart_quote(client: httpx.AsyncClient, symbol: str) -> tuple[float | None, float | None]:
    """Fallback to Yahoo's chart endpoint when the quote endpoint is unavailable."""
    try:
        response = await client.get(
            f"https://query2.finance.yahoo.com/v8/finance/chart/{symbol}",
            params={"range": "1d", "interval": "1m", "includePrePost": "true"},
        )
        response.raise_for_status()
        result = (response.json().get("chart") or {}).get("result") or []
        if not result:
            return None, None
        meta = result[0].get("meta") or {}
        price = meta.get("regularMarketPrice")
        previous = meta.get("previousClose") or meta.get("chartPreviousClose")
        if price is None:
            closes = (((result[0].get("indicators") or {}).get("quote") or [{}])[0].get("close") or [])
            price = next((v for v in reversed(closes) if isinstance(v, (int, float))), None)
        if not isinstance(price, (int, float)):
            return None, None
        return float(price), float(previous) if isinstance(previous, (int, float)) else None
    except Exception:
        return None, None


async def _load_markets() -> list[dict]:
    headers = {"User-Agent": "Mozilla/5.0 TITAN-X/1.0"}
    symbols = ",".join(symbol for symbol, _ in _INDEXES.values())

    async with httpx.AsyncClient(timeout=8.0, follow_redirects=True, headers=headers) as client:
        # Fast path: Yahoo quote endpoint can return the whole universe in one request.
        by_symbol: dict[str, dict] = {}
        try:
            response = await client.get(
                "https://query1.finance.yahoo.com/v7/finance/quote",
                params={"symbols": symbols},
            )
            response.raise_for_status()
            result = (response.json().get("quoteResponse") or {}).get("result") or []
            by_symbol = {str(row.get("symbol")): row for row in result if row.get("symbol")}
        except Exception:
            by_symbol = {}

        # Reliable fallback: fetch each index from Yahoo's chart endpoint concurrently.
        missing = [symbol for symbol in (value[0] for value in _INDEXES.values()) if symbol not in by_symbol]
        fallback = {}
        if missing:
            results = await asyncio.gather(*(_chart_quote(client, symbol) for symbol in missing))
            fallback = dict(zip(missing, results))

        markets: list[dict] = []
        for name, (yahoo_symbol, region) in _INDEXES.items():
            row = by_symbol.get(yahoo_symbol, {})
            price = row.get("regularMarketPrice")
            change = row.get("regularMarketChangePercent")
            if not isinstance(price, (int, float)):
                price, previous = fallback.get(yahoo_symbol, (None, None))
                if price is not None and previous not in (None, 0):
                    change = ((price - previous) / previous) * 100
            markets.append({
                "name": name,
                "symbol": yahoo_symbol,
                "region": region,
                "price": float(price) if isinstance(price, (int, float)) else None,
                "change_pct": float(change) if isinstance(change, (int, float)) else None,
            })
        return markets


@router.get("/snapshot")
async def public_market_snapshot():
    """Return current values for global market indices only."""
    try:
        markets = await _load_markets()
        live_count = sum(1 for row in markets if row.get("price") is not None)
        score, regime = _score(markets)
        return {
            "ok": live_count > 0,
            "source": "Yahoo Finance",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "score": score,
            "regime": regime,
            "live_count": live_count,
            "markets": markets,
        }
    except Exception as exc:
        return {
            "ok": False,
            "source": "Yahoo Finance",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "score": None,
            "regime": "Market data unavailable",
            "live_count": 0,
            "markets": [],
            "error": str(exc),
        }
