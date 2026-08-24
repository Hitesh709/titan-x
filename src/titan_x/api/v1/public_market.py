"""Public live index snapshot used by the unauthenticated TITAN X landing page."""

from __future__ import annotations

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


def _score(rows: list[dict]) -> tuple[int, str]:
    valid = [r for r in rows if isinstance(r.get("change_pct"), (int, float))]
    if not valid:
        return 50, "Neutral"
    avg = sum(float(r["change_pct"]) for r in valid) / len(valid)
    positive = sum(1 for r in valid if float(r["change_pct"]) > 0)
    value = round(max(0, min(100, 50 + avg * 12 + (positive - len(valid) / 2) * 5)))
    if value >= 75:
        return value, "Very Bullish"
    if value >= 60:
        return value, "Bullish"
    if value <= 25:
        return value, "Very Bearish"
    if value <= 40:
        return value, "Bearish"
    return value, "Neutral"


@router.get("/snapshot")
async def public_market_snapshot():
    """Return current values for global market indices only."""
    headers = {"User-Agent": "Mozilla/5.0 TITAN-X/1.0"}
    symbols = ",".join(symbol for symbol, _ in _INDEXES.values())
    url = "https://query1.finance.yahoo.com/v7/finance/quote"
    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True, headers=headers) as client:
            response = await client.get(url, params={"symbols": symbols})
            response.raise_for_status()
            result = (response.json().get("quoteResponse") or {}).get("result") or []

        by_symbol = {str(row.get("symbol")): row for row in result}
        markets: list[dict] = []
        for name, (yahoo_symbol, region) in _INDEXES.items():
            row = by_symbol.get(yahoo_symbol, {})
            price = row.get("regularMarketPrice")
            change = row.get("regularMarketChangePercent")
            markets.append({
                "name": name,
                "symbol": yahoo_symbol,
                "region": region,
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
