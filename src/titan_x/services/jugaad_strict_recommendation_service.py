from __future__ import annotations

import asyncio
from typing import Any

from sqlalchemy import select

from titan_x.infrastructure.jugaad_nse_provider import JugaadNSEProvider
from titan_x.models.company import Company
from titan_x.models.price import DailyPrice
from titan_x.services.ai_recommendation_engine import _technical_pillar, bars_from_records
from titan_x.services.intraday_recommendation_service import FNO_UNIVERSE

STRICT_TECHNICAL_THRESHOLD = 95.0
MAX_SCAN = 100
_state: dict[tuple[str, str], dict[str, Any]] = {}
_tasks: dict[tuple[str, str], asyncio.Task] = {}


def get_strict_scan_status(mode: str, segment: str) -> dict[str, Any]:
    key = (mode, segment)
    state = _state.get(key)
    if state is None:
        return {"status": "idle", "mode": mode, "segment": segment, "scanned": 0, "universe_size": 0, "progress_pct": 0, "recommendations": []}
    return dict(state)


async def _universe(session, segment: str) -> list[str]:
    if segment == "fno":
        return [s for s in dict.fromkeys(FNO_UNIVERSE) if s not in {"NIFTY", "BANKNIFTY", "SENSEX", "FINNIFTY", "MIDCPNIFTY", "NIFTYNXT50"}][:MAX_SCAN]
    rows = (await session.execute(select(Company.symbol).where(Company.status == "active").where(Company.exchange == "NSE").order_by(Company.symbol.asc()).limit(MAX_SCAN))).all()
    return [str(row[0]).upper() for row in rows if row[0]]


async def _delivery_scan(session_factory, symbols: list[str], state: dict[str, Any]) -> list[dict[str, Any]]:
    provider = JugaadNSEProvider()
    results: list[dict[str, Any]] = []
    try:
        async with session_factory() as session:
            for index, symbol in enumerate(symbols, 1):
                try:
                    rows = (await session.execute(select(DailyPrice).where(DailyPrice.symbol == symbol).order_by(DailyPrice.trade_date.asc()).limit(400))).scalars().all()
                    bars = bars_from_records(rows)
                    if len(bars) < 60:
                        continue
                    pillar = _technical_pillar(bars)
                    if float(pillar.score) < STRICT_TECHNICAL_THRESHOLD or pillar.direction == 0:
                        continue
                    quote = await provider.get_quote(symbol)
                    live_price = float(quote["last_price"])
                    results.append({
                        "id": f"strict-delivery-{symbol}", "symbol": symbol, "display_name": symbol,
                        "direction": "BUY" if pillar.direction > 0 else "SELL", "signal": f"TECHNICAL_{'BUY' if pillar.direction > 0 else 'SELL'}",
                        "confidence": round(float(pillar.confidence) * 100, 2), "current_price": live_price, "price_target": None,
                        "timeframe": "Delivery / Short Term", "reasoning": "Delivery Technical Pillar passed the strict threshold using stored historical bars and a live NSE price.",
                        "recommendation_type": "STRICT_DELIVERY", "status": "active", "score": round(float(pillar.score), 2),
                        "technical_score": round(float(pillar.score), 2), "technical_pillar_score": round(float(pillar.score), 2), "strict_technical_gate": True,
                        "delivery_technical_score": round(float(pillar.score), 2), "delivery_technical_pillar_score": round(float(pillar.score), 2),
                        "generated_at": quote.get("timestamp"), "source": "jugaad-data/NSE",
                    })
                except Exception:
                    continue
                state["scanned"] = index
                state["progress_pct"] = round(index * 100 / max(len(symbols), 1), 1)
    finally:
        await provider.close()
    return results


async def _intraday_scan(symbols: list[str], state: dict[str, Any]) -> list[dict[str, Any]]:
    provider = JugaadNSEProvider()
    semaphore = asyncio.Semaphore(5)

    async def scan(symbol: str):
        async with semaphore:
            try:
                candles = await provider.get_candles(symbol, "5m", "5d")
                bars = bars_from_records(candles)
                if len(bars) < 60:
                    return None
                pillar = _technical_pillar(bars)
                if float(pillar.score) < STRICT_TECHNICAL_THRESHOLD or pillar.direction == 0:
                    return None
                quote = await provider.get_quote(symbol)
                live_price = float(quote["last_price"])
                direction = "BUY" if pillar.direction > 0 else "SELL"
                return {
                    "id": f"strict-intraday-{symbol}", "symbol": symbol, "display_name": symbol, "direction": direction,
                    "signal": f"TECHNICAL_{direction}", "confidence": round(float(pillar.confidence) * 100, 2), "current_price": live_price,
                    "entry_price": live_price, "price_target": None, "stop_price": None, "timeframe": "Intraday · 5m",
                    "recommendation_type": "STRICT_INTRADAY", "status": "active", "score": round(float(pillar.score), 2),
                    "technical_score": round(float(pillar.score), 2), "technical_pillar_score": round(float(pillar.score), 2),
                    "strict_technical_gate": True, "source": "jugaad-data/NSE", "generated_at": quote.get("timestamp"),
                }
            except Exception:
                return None

    try:
        scanned = await asyncio.gather(*(scan(s) for s in symbols))
        results = [item for item in scanned if item is not None]
        state["scanned"] = len(symbols)
        state["progress_pct"] = 100
        return results
    finally:
        await provider.close()


async def _run(session_factory, mode: str, segment: str, limit: int) -> None:
    key = (mode, segment)
    state = _state[key]
    try:
        async with session_factory() as session:
            symbols = await _universe(session, segment)
        state["universe_size"] = len(symbols)
        state["status"] = "running"
        recommendations = await _intraday_scan(symbols, state) if mode == "intraday" else await _delivery_scan(session_factory, symbols, state)
        recommendations.sort(key=lambda x: (x.get("technical_pillar_score", 0), x.get("confidence", 0)), reverse=True)
        state["recommendations"] = recommendations[:limit]
        state["status"] = "completed"
    except Exception as exc:
        state["status"] = "failed"
        state["error"] = str(exc)


async def get_strict_recommendations(session_factory, mode: str = "delivery", segment: str = "equity", limit: int = 100) -> dict[str, Any]:
    if mode not in {"delivery", "intraday"}:
        raise ValueError("mode must be delivery or intraday")
    if segment not in {"equity", "fno"}:
        raise ValueError("segment must be equity or fno")
    limit = max(1, min(int(limit), MAX_SCAN))
    key = (mode, segment)
    current = _tasks.get(key)
    if current is None or current.done():
        _state[key] = {"status": "starting", "mode": mode, "segment": segment, "scanned": 0, "universe_size": 0, "progress_pct": 0, "recommendations": []}
        _tasks[key] = asyncio.create_task(_run(session_factory, mode, segment, limit))
    state = _state[key]
    return {**state, "limit": limit, "live": True, "provider": "jugaad", "source": "jugaad-data/NSE"}
