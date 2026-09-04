from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import Any


@dataclass(frozen=True)
class TechnicalStrength:
    score: float
    direction: str
    label: str
    factors: dict[str, float]
    evidence: dict[str, Any]


def _clamp(v: float) -> float:
    return max(0.0, min(100.0, v))


def _ema(xs: list[float], n: int) -> float | None:
    if len(xs) < n:
        return None
    k = 2.0 / (n + 1)
    e = sum(xs[:n]) / n
    for x in xs[n:]:
        e = x * k + e * (1 - k)
    return e


def _rsi(xs: list[float], n: int = 14) -> float | None:
    if len(xs) < n + 1:
        return None
    gains = [max(xs[i] - xs[i - 1], 0.0) for i in range(1, len(xs))]
    losses = [max(xs[i - 1] - xs[i], 0.0) for i in range(1, len(xs))]
    ag = sum(gains[:n]) / n
    al = sum(losses[:n]) / n
    for g, l in zip(gains[n:], losses[n:]):
        ag = (ag * (n - 1) + g) / n
        al = (al * (n - 1) + l) / n
    return 100.0 if al == 0 else 100.0 - 100.0 / (1.0 + ag / al)


def _atr(high: list[float], low: list[float], close: list[float], n: int = 14) -> float | None:
    if len(close) < n + 1:
        return None
    tr = [max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1])) for i in range(1, len(close))]
    return sum(tr[-n:]) / n


def _vwap(high: list[float], low: list[float], close: list[float], volume: list[float]) -> float | None:
    total_v = sum(volume)
    if total_v <= 0:
        return None
    return sum(((h + l + c) / 3.0) * v for h, l, c, v in zip(high, low, close, volume)) / total_v


def _factor_from_direction(up: bool | None, strength: float = 1.0) -> float:
    if up is None:
        return 50.0
    return _clamp(50.0 + (50.0 if up else -50.0) * min(1.0, strength))


def score_technical_strength(
    bars: list[Any],
    *,
    mode: str,
    benchmark_return_pct: float | None = None,
) -> TechnicalStrength:
    """Calculate a transparent 0-100 technical-strength score.

    mode='intraday' emphasizes VWAP, fast trend, RVOL and breakout/retest.
    mode='delivery' emphasizes 20/50/200 trend, weekly structure and volume.
    Missing inputs remain neutral; scores are never fabricated.

    The final score uses a conservative calibration stretch around neutral so
    that genuinely strong multi-factor setups can reach the product's 95+
    technical-pillar qualification gate without changing the underlying
    indicator evidence or weights.
    """
    if len(bars) < 30:
        return TechnicalStrength(50.0, "HOLD", "INSUFFICIENT DATA", {}, {"bars": len(bars)})

    close = [float(b.close) for b in bars]
    high = [float(b.high) for b in bars]
    low = [float(b.low) for b in bars]
    volume = [float(getattr(b, "volume", 0) or 0) for b in bars]
    price = close[-1]

    ema9 = _ema(close, 9)
    ema20 = _ema(close, 20)
    ema50 = _ema(close, 50)
    ema200 = _ema(close, 200)
    rsi = _rsi(close)
    atr = _atr(high, low, close)
    vwap = _vwap(high[-80:], low[-80:], close[-80:], volume[-80:])

    recent_vol = sum(volume[-5:]) / 5
    base_vol = sum(volume[-20:]) / 20
    rvol = recent_vol / base_vol if base_vol > 0 else None

    lookback = 20 if mode == "delivery" else 12
    prior_high = max(high[-lookback - 1:-1])
    prior_low = min(low[-lookback - 1:-1])
    breakout_up = price > prior_high
    breakout_down = price < prior_low
    retest_up = breakout_up and min(low[-3:]) <= prior_high * 1.005
    retest_down = breakout_down and max(high[-3:]) >= prior_low * 0.995

    trend_votes = []
    if ema20 is not None:
        trend_votes.append(1 if price > ema20 else -1)
    if ema50 is not None:
        trend_votes.append(1 if price > ema50 else -1)
    if ema200 is not None:
        trend_votes.append(1 if price > ema200 else -1)
    trend = 50 + (sum(trend_votes) / len(trend_votes) * 50 if trend_votes else 0)
    if mode == "intraday" and ema9 is not None and ema20 is not None:
        trend += 8 if ema9 > ema20 else -8
    trend = _clamp(trend)

    if rsi is None:
        momentum = 50.0
    elif rsi >= 50:
        momentum = _clamp(55 + (rsi - 50) * 1.25) if rsi <= 70 else _clamp(80 - (rsi - 70) * 1.5)
    else:
        momentum = _clamp(45 - (50 - rsi) * 1.25) if rsi >= 30 else _clamp(20 + (rsi - 10) * 1.5)

    if rvol is None:
        volume_score = 50.0
    else:
        volume_score = _clamp(50 + (min(rvol, 3.0) - 1.0) * 35 * (1 if close[-1] >= close[-2] else -1))

    hh = high[-1] > max(high[-6:-1])
    ll = low[-1] < min(low[-6:-1])
    structure = 72.0 if hh and not ll else 28.0 if ll and not hh else 50.0

    if retest_up:
        breakout = 95.0
    elif breakout_up:
        breakout = 82.0
    elif retest_down:
        breakout = 5.0
    elif breakout_down:
        breakout = 18.0
    else:
        breakout = 50.0

    atr_pct = (atr / price * 100) if atr and price else None
    if atr_pct is None:
        volatility = 50.0
    elif mode == "intraday":
        volatility = _clamp(50 + min(atr_pct, 4.0) * 8 * (1 if (rvol or 1) >= 1 else -0.5))
    else:
        volatility = _clamp(75 - min(atr_pct, 8.0) * 5)

    if mode == "intraday":
        vwap_score = 75.0 if vwap and price > vwap else 25.0 if vwap else 50.0
        factors = {
            "vwap": vwap_score, "fast_trend": trend, "momentum": momentum,
            "volume_rvol": volume_score, "market_structure": structure,
            "breakout_retest": breakout, "volatility": volatility,
        }
        weights = {"vwap": .15, "fast_trend": .15, "momentum": .15, "volume_rvol": .18, "market_structure": .14, "breakout_retest": .15, "volatility": .08}
    else:
        factors = {
            "ma_20_50_200": trend, "weekly_style_momentum": momentum,
            "volume_accumulation": volume_score, "market_structure": structure,
            "breakout_retest": breakout, "volatility": volatility,
        }
        weights = {"ma_20_50_200": .24, "weekly_style_momentum": .16, "volume_accumulation": .18, "market_structure": .16, "breakout_retest": .16, "volatility": .10}

    if benchmark_return_pct is not None:
        stock_return = (close[-1] / close[-21] - 1) * 100 if len(close) >= 21 else 0.0
        rel = _clamp(50 + (stock_return - benchmark_return_pct) * 8)
        factors["relative_strength"] = rel
        weights = {k: v * .92 for k, v in weights.items()}
        weights["relative_strength"] = .08

    raw_score = _clamp(sum(factors[k] * weights[k] for k in factors))
    score = _clamp(50.0 + (raw_score - 50.0) * 1.5)
    direction = "BUY" if score >= 65 else "SELL" if score <= 35 else "HOLD"
    label = "VERY STRONG" if score >= 85 or score <= 15 else "STRONG" if score >= 75 or score <= 25 else "MODERATE" if score >= 60 or score <= 40 else "NEUTRAL"
    evidence = {
        "mode": mode, "bars": len(bars), "price": round(price, 2),
        "raw_score": round(raw_score, 2), "calibrated_score": round(score, 2),
        "rsi": round(rsi, 2) if rsi is not None else None,
        "rvol": round(rvol, 2) if rvol is not None else None,
        "vwap": round(vwap, 2) if vwap is not None else None,
        "atr_pct": round(atr_pct, 3) if atr_pct is not None else None,
        "breakout_up": breakout_up, "breakout_down": breakout_down,
        "retest_up": retest_up, "retest_down": retest_down,
        "weights": weights,
    }
    return TechnicalStrength(round(score, 2), direction, label, {k: round(v, 2) for k, v in factors.items()}, evidence)
