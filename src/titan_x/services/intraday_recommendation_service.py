from __future__ import annotations

import asyncio
import math
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from titan_x.infrastructure.market_data_providers import YahooFinanceProvider
from titan_x.services.ai_recommendation_engine import bars_from_records

# Fallback/liquid equity universe. The API normally replaces this with the
# active company universe from the database so the recommendation screen is
# not limited to the original 30 symbols.
EQUITY_UNIVERSE = [
    "RELIANCE", "HDFCBANK", "ICICIBANK", "SBIN", "TCS", "INFY", "BHARTIARTL",
    "LT", "AXISBANK", "KOTAKBANK", "ITC", "MARUTI", "M&M", "SUNPHARMA",
    "HINDUNILVR", "TATAMOTORS", "TATASTEEL", "NTPC", "POWERGRID", "ADANIENT",
    "ADANIPORTS", "BAJFINANCE", "BAJAJFINSV", "HCLTECH", "WIPRO", "TECHM",
    "TITAN", "ONGC", "COALINDIA", "BEL",
]

# Common liquid NSE F&O underlyings plus major Indian indices. Contract
# eligibility/lot/expiry data should still come from a licensed derivatives
# feed before any real order is placed.
FNO_UNIVERSE = [
    "NIFTY", "BANKNIFTY", "SENSEX", "FINNIFTY", "MIDCPNIFTY", "NIFTYNXT50",
    "RELIANCE", "HDFCBANK", "ICICIBANK", "SBIN", "AXISBANK", "KOTAKBANK",
    "BAJFINANCE", "BAJAJFINSV", "BHARTIARTL", "TCS", "INFY", "HCLTECH",
    "ITC", "LT", "MARUTI", "M&M", "SUNPHARMA", "HINDUNILVR", "TATAMOTORS",
    "TATASTEEL", "ADANIENT", "ADANIPORTS", "BEL", "NTPC", "POWERGRID",
    "ONGC", "COALINDIA", "JSWSTEEL", "VEDL", "JINDALSTEL",
]

# Yahoo Finance ticker mapping for the index names shown in Titan X.
YAHOO_INDEX_TICKERS = {
    "NIFTY": "^NSEI",
    "BANKNIFTY": "^NSEBANK",
    "SENSEX": "^BSESN",
    "FINNIFTY": "NIFTY_FIN_SERVICE.NS",
    "MIDCPNIFTY": "NIFTY_MID_SELECT.NS",
    "NIFTYNXT50": "^NSEMDCP50",
}

IST = ZoneInfo("Asia/Kolkata")


def _ema(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    k = 2.0 / (period + 1)
    value = sum(values[:period]) / period
    for price in values[period:]:
        value = price * k + value * (1.0 - k)
    return value


def _rsi(values: list[float], period: int = 14) -> float | None:
    if len(values) < period + 1:
        return None
    gains = []
    losses = []
    for i in range(1, len(values)):
        delta = values[i] - values[i - 1]
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for gain, loss in zip(gains[period:], losses[period:]):
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
    if avg_loss == 0:
        return 100.0
    return 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))


def _atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    trs = []
    for i in range(1, len(closes)):
        trs.append(max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        ))
    return sum(trs[-period:]) / period


def _round_strike(price: float) -> int:
    if price < 200:
        step = 5
    elif price < 500:
        step = 10
    elif price < 1000:
        step = 20
    elif price < 2000:
        step = 50
    else:
        step = 100
    return int(round(price / step) * step)


def _market_open() -> bool:
    now = datetime.now(IST)
    if now.weekday() >= 5:
        return False
    minutes = now.hour * 60 + now.minute
    return 9 * 60 + 15 <= minutes <= 15 * 60 + 30


def _score_intraday(points: list) -> dict | None:
    bars = bars_from_records(points)
    if len(bars) < 60:
        return None
    closes = [b.close for b in bars]
    highs = [b.high for b in bars]
    lows = [b.low for b in bars]
    volumes = [b.volume for b in bars]
    price = closes[-1]
    if price <= 0:
        return None

    ema20 = _ema(closes, 20)
    ema50 = _ema(closes, 50)
    rsi = _rsi(closes, 14)
    atr = _atr(highs, lows, closes, 14)
    if ema20 is None or ema50 is None or rsi is None or atr is None:
        return None

    lookback = min(12, len(closes) - 1)
    momentum = (price / closes[-lookback - 1] - 1.0) * 100.0
    avg_volume = sum(volumes[-21:-1]) / max(1, len(volumes[-21:-1]))
    volume_ratio = volumes[-1] / avg_volume if avg_volume > 0 else 1.0

    score = 50.0
    score += max(-15.0, min(15.0, momentum * 8.0))
    if price > ema20:
        score += 8
    else:
        score -= 8
    if ema20 > ema50:
        score += 8
    else:
        score -= 8
    if 52 <= rsi <= 72:
        score += 7
    elif 28 <= rsi < 48:
        score -= 7
    elif rsi > 78:
        score -= 4
    elif rsi < 22:
        score += 4
    if volume_ratio >= 1.5:
        score += 8 if momentum >= 0 else -8
    elif volume_ratio >= 1.15:
        score += 4 if momentum >= 0 else -4

    candle_range = max(highs[-1] - lows[-1], price * 0.0001)
    candle_body = closes[-1] - bars[-1].open
    body_strength = candle_body / candle_range
    score += max(-6.0, min(6.0, body_strength * 6.0))
    score = max(0.0, min(100.0, score))

    if score >= 62:
        direction = "BUY"
        signal = "INTRADAY_BUY"
    elif score <= 38:
        direction = "SELL"
        signal = "INTRADAY_SELL"
    else:
        direction = "HOLD"
        signal = "NO_TRADE"

    confidence = min(95.0, 50.0 + abs(score - 50.0) * 1.45)
    if volume_ratio < 0.8:
        confidence *= 0.90
    if 45 <= rsi <= 55:
        confidence *= 0.92

    risk_per_share = max(atr * 1.5, price * 0.0025)
    if direction == "BUY":
        target = price + risk_per_share * 2.0
        stop = price - risk_per_share
    elif direction == "SELL":
        target = price - risk_per_share * 2.0
        stop = price + risk_per_share
    else:
        target = price
        stop = price

    evidence = [
        f"5m momentum {momentum:+.2f}%",
        f"EMA20 {'above' if price > ema20 else 'below'} current price",
        f"EMA20 {'above' if ema20 > ema50 else 'below'} EMA50",
        f"Volume {volume_ratio:.1f}x 20-bar average",
    ]
    caution = []
    if volume_ratio < 1.0:
        caution.append("Participation is below the recent average.")
    if rsi > 75 or rsi < 25:
        caution.append("RSI is in an extreme zone; avoid chasing the move.")
    if direction == "HOLD":
        caution.append("No clear intraday direction — TitanX is avoiding a weak trade.")

    return {
        "direction": direction,
        "signal": signal,
        "score": round(score, 2),
        "confidence": round(confidence, 2),
        "current_price": round(price, 2),
        "entry_price": round(price, 2),
        "target_price": round(target, 2),
        "stop_price": round(stop, 2),
        "risk_reward": 2.0 if direction != "HOLD" else 0.0,
        "expected_return_pct": round(abs(target - price) / price * 100.0, 2) if direction != "HOLD" else 0.0,
        "volume_ratio": round(volume_ratio, 2),
        "rsi": round(rsi, 2),
        "ema20": round(ema20, 2),
        "ema50": round(ema50, 2),
        "momentum_pct": round(momentum, 3),
        "evidence": evidence,
        "caution": caution,
    }


async def get_intraday_recommendations(
    segment: str,
    limit: int = 10,
    universe_symbols: list[str] | None = None,
) -> dict:
    segment = segment.lower().strip()
    if segment not in {"equity", "fno"}:
        raise ValueError("segment must be equity or fno")

    universe = list(dict.fromkeys(universe_symbols or (FNO_UNIVERSE if segment == "fno" else EQUITY_UNIVERSE)))
    if not universe:
        universe = FNO_UNIVERSE if segment == "fno" else EQUITY_UNIVERSE

    # Do not allow an accidental enormous request to create an unbounded scan.
    # Titan X currently has ~2.3k active NSE symbols, so 3000 is a safe upper bound.
    limit = max(1, min(int(limit), 3000))
    provider = YahooFinanceProvider()
    start = date.today() - timedelta(days=30)
    end = date.today() + timedelta(days=1)

    # Yahoo/Render can become unstable when hundreds of requests are opened at
    # once. A bounded worker pool lets the full universe be scanned without the
    # old all-at-once gather fan-out.
    semaphore = asyncio.Semaphore(8)

    async def scan(display_symbol: str):
        ticker = YAHOO_INDEX_TICKERS.get(display_symbol, display_symbol)
        async with semaphore:
            try:
                points = await provider.get_historical_prices(
                    ticker,
                    interval="5m",
                    start=start,
                    end=end,
                    synthetic_ok=False,
                )
                scored = _score_intraday(points)
                if not scored:
                    return None
                scored["symbol"] = display_symbol
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
        item["instrument"] = "INDEX" if item["symbol"] in YAHOO_INDEX_TICKERS else ("FUTURES" if segment == "fno" else "EQUITY")
        item["option_bias"] = "CALL" if direction == "BUY" else "PUT" if direction == "SELL" else "NONE"
        item["option_strike"] = _round_strike(item["current_price"]) if segment == "fno" else None
        item["timeframe"] = "Intraday · 5m"
        item["generated_at"] = generated
        recommendations.append(item)

    # Keep major indices first in the F&O response, then rank all other
    # derivatives by confidence.
    if segment == "fno":
        priority = {name: i for i, name in enumerate(FNO_UNIVERSE[:6])}
        recommendations.sort(key=lambda r: (priority.get(r["symbol"], 999), -r["confidence"]))

    return {
        "segment": segment,
        "generated_at": generated,
        "market_open": _market_open(),
        "universe_size": len(universe),
        "scanned": len(scored),
        "recommendations": recommendations,
    }
