"""Crypto recommendation engine for Titan X.

Provides two distinct research modes:
- intraday: 5m / 15m / 30m confirmation
- delivery: 4h / 1d / 1w positional confirmation

This is a rule-based market analysis endpoint, not a guarantee of returns.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import httpx
from titan_x.services.crypto_market_data import candles as market_candles
from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/crypto-recommendation", tags=["crypto-recommendation"])

INTRADAY_TFS = ("5m", "15m", "30m")
DELIVERY_TFS = ("4h", "1d", "1w")


async def _candles(symbol: str, interval: str, limit: int = 220) -> list[dict[str, float]]:
    rows, _provider = await market_candles(symbol, interval, limit)
    return rows


def _ema(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    k = 2 / (period + 1)
    result = [values[0]]
    for value in values[1:]:
        result.append(result[-1] + (value - result[-1]) * k)
    return result


def _rsi(values: list[float], period: int = 14) -> float:
    if len(values) <= period:
        return 50.0
    gains = []
    losses = []
    for i in range(len(values) - period, len(values)):
        change = values[i] - values[i - 1]
        gains.append(max(change, 0))
        losses.append(max(-change, 0))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0 if avg_gain else 50.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _atr(candles: list[dict[str, float]], period: int = 14) -> float:
    if len(candles) < period + 1:
        return 0.0
    tr = []
    for i in range(1, len(candles)):
        c, prev = candles[i], candles[i - 1]
        tr.append(max(c["high"] - c["low"], abs(c["high"] - prev["close"]), abs(c["low"] - prev["close"])))
    return sum(tr[-period:]) / period


def _evaluate(candles: list[dict[str, float]], timeframe: str) -> dict[str, Any]:
    close = [x["close"] for x in candles]
    volume = [x["volume"] for x in candles]
    price = close[-1]
    e9, e20, e50 = _ema(close, 9)[-1], _ema(close, 20)[-1], _ema(close, 50)[-1]
    rsi = _rsi(close)
    fast, slow = _ema(close, 12), _ema(close, 26)
    macd = fast[-1] - slow[-1]
    macd_signal = _ema([a - b for a, b in zip(fast, slow)], 9)[-1]
    atr = _atr(candles)
    avg_volume = sum(volume[-20:]) / min(20, len(volume))
    volume_ok = volume[-1] >= avg_volume
    bullish = e9 > e20 > e50 and price > e20 and rsi >= 52 and macd >= macd_signal
    bearish = e9 < e20 < e50 and price < e20 and rsi <= 48 and macd <= macd_signal

    if bullish and volume_ok:
        decision = "BUY"
    elif bearish and volume_ok:
        decision = "SELL"
    else:
        decision = "HOLD"

    if decision == "BUY":
        stop = price - max(atr * 1.5, price * 0.01)
        target = price + max(atr * 3.0, price * 0.02)
    elif decision == "SELL":
        stop = price + max(atr * 1.5, price * 0.01)
        target = price - max(atr * 3.0, price * 0.02)
    else:
        stop = target = None

    reasons = []
    reasons.append("EMA trend aligned" if bullish or bearish else "EMA trend not fully aligned")
    reasons.append("Momentum aligned" if (rsi >= 52 and macd >= macd_signal) or (rsi <= 48 and macd <= macd_signal) else "Momentum mixed")
    reasons.append("Volume confirmation" if volume_ok else "Volume below 20-period average")

    return {
        "timeframe": timeframe,
        "decision": decision,
        "price": price,
        "rsi": rsi,
        "atr": atr,
        "entry": price if decision != "HOLD" else None,
        "stop_loss": stop,
        "target": target,
        "reason": "; ".join(reasons),
    }


async def _recommend(symbol: str, mode: str) -> dict[str, Any]:
    timeframes = INTRADAY_TFS if mode == "intraday" else DELIVERY_TFS
    results = []
    for timeframe in timeframes:
        try:
            results.append(_evaluate(await _candles(symbol, timeframe), timeframe))
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            raise HTTPException(status_code=502, detail=f"Market data unavailable for {symbol}: {exc}") from exc

    buys = sum(x["decision"] == "BUY" for x in results)
    sells = sum(x["decision"] == "SELL" for x in results)

    if buys == len(results):
        action = "BUY"
    elif sells == len(results):
        action = "SELL"
    else:
        action = "HOLD"

    latest = results[-1]
    entry = latest["entry"] if action != "HOLD" else None
    stop = latest["stop_loss"] if action != "HOLD" else None
    target = latest["target"] if action != "HOLD" else None

    return {
        "symbol": symbol,
        "mode": mode,
        "action": action,
        "horizon": "same-day intraday" if mode == "intraday" else "multi-day / positional",
        "entry": entry,
        "stop_loss": stop,
        "target": target,
        "rule": "All selected timeframes must agree; otherwise HOLD",
        "timeframes": results,
        "confidence": round(max(buys, sells) / len(results) * 100, 1),
        "summary": (
            f"{buys}/{len(results)} timeframes bullish, {sells}/{len(results)} bearish"
        ),
    }


@router.get("", response_model=dict[str, Any])
async def recommendation(
    symbol: str = Query(..., min_length=5, max_length=20),
    mode: str = Query("intraday", pattern=r"^(intraday|delivery)$"),
) -> dict[str, Any]:
    symbol = symbol.strip().upper()
    if not symbol.endswith("USDT"):
        raise HTTPException(status_code=400, detail="Crypto symbols must use the USDT pair, e.g. BTCUSDT")
    return await _recommend(symbol, mode)


@router.get("/both", response_model=dict[str, Any])
async def both_recommendations(
    symbol: str = Query(..., min_length=5, max_length=20),
) -> dict[str, Any]:
    symbol = symbol.strip().upper()
    if not symbol.endswith("USDT"):
        raise HTTPException(status_code=400, detail="Crypto symbols must use the USDT pair, e.g. BTCUSDT")
    intraday, delivery = await __import__("asyncio").gather(
        _recommend(symbol, "intraday"),
        _recommend(symbol, "delivery"),
    )
    return {"symbol": symbol, "intraday": intraday, "delivery": delivery}
