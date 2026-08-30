from __future__ import annotations

import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from titan_x.infrastructure.jugaad_nse_provider import JugaadNSEProvider
from titan_x.services.intraday_recommendation_service import (
    EQUITY_UNIVERSE,
    FNO_UNIVERSE,
    _market_open,
    _round_strike,
    _score_intraday,
)

IST = ZoneInfo("Asia/Kolkata")
INDEX_SYMBOLS = {"NIFTY", "BANKNIFTY", "SENSEX", "FINNIFTY", "MIDCPNIFTY", "NIFTYNXT50"}


async def get_intraday_recommendations(
    segment: str,
    limit: int = 10,
    universe_symbols: list[str] | None = None,
) -> dict:
    """Run the intraday scanner on live NSE candles without Yahoo.

    The demo deployment intentionally bounds the scan because the public NSE
    feed is request-based rather than a broker WebSocket. Every actionable
    result is based on live Jugaad/NSE 5-minute candles and a fresh LTP.
    """
    segment = segment.lower().strip()
    if segment not in {"equity", "fno"}:
        raise ValueError("segment must be equity or fno")

    requested = list(dict.fromkeys(universe_symbols or (FNO_UNIVERSE if segment == "fno" else EQUITY_UNIVERSE)))
    # Index quote support is separate in NSELive; keep this first live scanner
    # on equity/F&O stock symbols rather than silently returning fake index data.
    universe = [s for s in requested if s not in INDEX_SYMBOLS][:100]
    if not universe:
        universe = [s for s in (FNO_UNIVERSE if segment == "fno" else EQUITY_UNIVERSE) if s not in INDEX_SYMBOLS][:100]

    limit = max(1, min(int(limit), 100))
    provider = JugaadNSEProvider()
    semaphore = asyncio.Semaphore(5)

    async def scan(display_symbol: str):
        async with semaphore:
            try:
                candles = await provider.get_candles(display_symbol, interval="5m", period="5d")
                scored = _score_intraday(candles)
                if not scored:
                    return None
                quote = await provider.get_quote(display_symbol)
                live_price = float(quote["last_price"])
                scored["symbol"] = display_symbol
                scored["current_price"] = round(live_price, 2)
                scored["entry_price"] = round(live_price, 2)
                scored["live_timestamp"] = quote.get("timestamp")
                scored["market_source"] = "jugaad-data/NSE"
                return scored
            except Exception:
                return None

    try:
        results = await asyncio.gather(*(scan(symbol) for symbol in universe))
    finally:
        await provider.close()

    scored = [r for r in results if r is not None]
    actionable = [r for r in scored if r["direction"] in {"BUY", "SELL"} and r["confidence"] >= 58]
    actionable.sort(
        key=lambda r: (
            r["confidence"],
            r["score"] if r["direction"] == "BUY" else 100 - r["score"],
        ),
        reverse=True,
    )

    recommendations = []
    generated = datetime.now(IST).isoformat()
    for item in actionable[:limit]:
        direction = item["direction"]
        item["segment"] = segment
        item["instrument"] = "FUTURES" if segment == "fno" else "EQUITY"
        item["option_bias"] = "CALL" if direction == "BUY" else "PUT" if direction == "SELL" else "NONE"
        item["option_strike"] = _round_strike(item["current_price"]) if segment == "fno" else None
        item["timeframe"] = "Intraday · 5m"
        item["generated_at"] = generated
        recommendations.append(item)

    return {
        "segment": segment,
        "generated_at": generated,
        "market_open": _market_open(),
        "universe_size": len(universe),
        "scanned": len(scored),
        "recommendations": recommendations,
        "provider": "jugaad",
        "source": "jugaad-data/NSE",
        "live": True,
        "note": "Index symbols are excluded from this public NSE stock scanner; no synthetic index prices are used.",
    }
