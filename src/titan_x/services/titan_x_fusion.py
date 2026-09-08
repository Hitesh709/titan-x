from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import Any, Sequence


@dataclass(frozen=True)
class FusionSignal:
    strategy: str
    signal: str
    timeframe: str
    entry: float | None
    stop_loss: float | None
    target: float | None
    reason: str
    regime: str
    confirmed: bool
    data_points: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "signal": self.signal,
            "timeframe": self.timeframe,
            "entry": self.entry,
            "stop_loss": self.stop_loss,
            "target": self.target,
            "reason": self.reason,
            "regime": self.regime,
            "confirmed": self.confirmed,
            "data_points": self.data_points,
        }


def _sma(values: Sequence[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if period <= 0:
        return out
    total = 0.0
    for i, value in enumerate(values):
        total += value
        if i >= period:
            total -= values[i - period]
        if i + 1 >= period:
            out[i] = total / period
    return out


def _ema(values: Sequence[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if len(values) < period or period <= 0:
        return out
    seed = sum(values[:period]) / period
    out[period - 1] = seed
    alpha = 2.0 / (period + 1.0)
    previous = seed
    for i in range(period, len(values)):
        previous = values[i] * alpha + previous * (1.0 - alpha)
        out[i] = previous
    return out


def _atr(high: Sequence[float], low: Sequence[float], close: Sequence[float], period: int = 14) -> list[float | None]:
    tr: list[float] = []
    for i in range(len(close)):
        if i == 0:
            tr.append(high[i] - low[i])
        else:
            tr.append(max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1])))
    return _sma(tr, period)


def _rsi(close: Sequence[float], period: int = 14) -> list[float | None]:
    gains = [0.0]
    losses = [0.0]
    for i in range(1, len(close)):
        delta = close[i] - close[i - 1]
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))
    avg_gain = _sma(gains, period)
    avg_loss = _sma(losses, period)
    out: list[float | None] = [None] * len(close)
    for i in range(len(close)):
        if avg_gain[i] is None or avg_loss[i] is None:
            continue
        if avg_loss[i] == 0:
            out[i] = 100.0
        else:
            rs = avg_gain[i] / avg_loss[i]
            out[i] = 100.0 - (100.0 / (1.0 + rs))
    return out


def _bollinger(close: Sequence[float], period: int = 20, multiplier: float = 2.0) -> tuple[list[float | None], list[float | None], list[float | None]]:
    mid = _sma(close, period)
    upper: list[float | None] = [None] * len(close)
    lower: list[float | None] = [None] * len(close)
    for i, mean in enumerate(mid):
        if mean is None:
            continue
        window = close[i + 1 - period : i + 1]
        variance = sum((x - mean) ** 2 for x in window) / period
        deviation = sqrt(max(variance, 0.0))
        upper[i] = mean + multiplier * deviation
        lower[i] = mean - multiplier * deviation
    return mid, upper, lower


def _macd(close: Sequence[float]) -> tuple[list[float | None], list[float | None], list[float | None]]:
    fast = _ema(close, 12)
    slow = _ema(close, 26)
    line: list[float | None] = [None] * len(close)
    values: list[float] = []
    indices: list[int] = []
    for i in range(len(close)):
        if fast[i] is not None and slow[i] is not None:
            line[i] = fast[i] - slow[i]
            values.append(line[i])
            indices.append(i)
    signal_values = _ema(values, 9)
    signal: list[float | None] = [None] * len(close)
    for idx, original_index in enumerate(indices):
        signal[original_index] = signal_values[idx]
    histogram: list[float | None] = [None] * len(close)
    for i in range(len(close)):
        if line[i] is not None and signal[i] is not None:
            histogram[i] = line[i] - signal[i]
    return line, signal, histogram


def _supertrend(high: Sequence[float], low: Sequence[float], close: Sequence[float], atr: Sequence[float | None], multiplier: float = 3.0) -> list[bool | None]:
    n = len(close)
    bullish: list[bool | None] = [None] * n
    upper: list[float | None] = [None] * n
    lower: list[float | None] = [None] * n
    for i in range(n):
        if atr[i] is None:
            continue
        midpoint = (high[i] + low[i]) / 2.0
        basic_upper = midpoint + multiplier * atr[i]
        basic_lower = midpoint - multiplier * atr[i]
        if i == 0 or upper[i - 1] is None or lower[i - 1] is None:
            upper[i] = basic_upper
            lower[i] = basic_lower
            bullish[i] = close[i] >= midpoint
            continue
        upper[i] = basic_upper if basic_upper < upper[i - 1] or close[i - 1] > upper[i - 1] else upper[i - 1]
        lower[i] = basic_lower if basic_lower > lower[i - 1] or close[i - 1] < lower[i - 1] else lower[i - 1]
        previous = bullish[i - 1]
        if previous:
            bullish[i] = close[i] >= lower[i]
        else:
            bullish[i] = close[i] > upper[i]
    return bullish


def _vwap(points: Sequence[Any]) -> list[float | None]:
    out: list[float | None] = []
    current_day: Any = None
    pv = 0.0
    volume = 0.0
    for point in points:
        day = getattr(point, "trade_date", None)
        if day != current_day:
            current_day = day
            pv = 0.0
            volume = 0.0
        typical = (float(point.high) + float(point.low) + float(point.close)) / 3.0
        volume += max(float(point.volume), 0.0)
        pv += typical * max(float(point.volume), 0.0)
        out.append(pv / volume if volume > 0 else None)
    return out


def _safe_round(value: float | None) -> float | None:
    return round(value, 2) if value is not None else None


def evaluate_fusion(points: Sequence[Any], timeframe: str = "5m") -> FusionSignal:
    """Evaluate the single, deterministic Titan X Fusion intraday strategy.

    The engine intentionally has no score or confidence percentage. BUY/SELL are
    only emitted when all critical gates align on the latest CLOSED candle.
    """
    strategy = "Titan X Fusion"
    clean = [p for p in points if all(getattr(p, field, None) is not None for field in ("open", "high", "low", "close", "volume"))]
    if len(clean) < 60:
        return FusionSignal(strategy, "HOLD", timeframe, None, None, None, "Insufficient intraday data", "UNKNOWN", False, len(clean))

    close = [float(p.close) for p in clean]
    high = [float(p.high) for p in clean]
    low = [float(p.low) for p in clean]
    volume = [max(float(p.volume), 0.0) for p in clean]

    e9 = _ema(close, 9)
    e20 = _ema(close, 20)
    e50 = _ema(close, 50)
    atr = _atr(high, low, close, 14)
    rsi = _rsi(close, 14)
    bb_mid, bb_upper, bb_lower = _bollinger(close, 20, 2.0)
    macd_line, macd_signal, macd_hist = _macd(close)
    supertrend = _supertrend(high, low, close, atr, 3.0)
    vwap = _vwap(clean)
    volume_avg = _sma(volume, 20)

    i = len(clean) - 1
    prev = i - 1
    required = (e9[i], e20[i], e50[i], atr[i], rsi[i], bb_mid[i], bb_upper[i], bb_lower[i], macd_line[i], macd_signal[i], macd_hist[i], vwap[i], volume_avg[i], supertrend[i])
    if any(value is None for value in required):
        return FusionSignal(strategy, "HOLD", timeframe, None, None, None, "Indicators are not fully warmed up", "UNKNOWN", False, len(clean))

    price = close[i]
    a = float(atr[i])
    rv = float(rsi[i])
    vol_ok = volume[i] >= float(volume_avg[i]) * 1.10
    recent_high = max(high[max(0, i - 20):i])
    recent_low = min(low[max(0, i - 20):i])
    breakout_up = price > recent_high and close[prev] <= recent_high
    breakout_down = price < recent_low and close[prev] >= recent_low
    pullback_up = low[i] <= float(e20[i]) * 1.002 and price > float(e20[i]) and price > float(vwap[i])
    pullback_down = high[i] >= float(e20[i]) * 0.998 and price < float(e20[i]) and price < float(vwap[i])
    bullish = bool(supertrend[i])
    bearish = not bullish
    trend_up = float(e9[i]) > float(e20[i]) > float(e50[i]) and price > float(e20[i])
    trend_down = float(e9[i]) < float(e20[i]) < float(e50[i]) and price < float(e20[i])
    macd_up = float(macd_line[i]) > float(macd_signal[i]) and float(macd_hist[i]) > 0
    macd_down = float(macd_line[i]) < float(macd_signal[i]) and float(macd_hist[i]) < 0
    not_overextended_up = price <= float(vwap[i]) + max(1.8 * a, price * 0.012)
    not_overextended_down = price >= float(vwap[i]) - max(1.8 * a, price * 0.012)
    reversal_up_warning = rv > 74 or (price >= float(bb_upper[i]) and rv > 68)
    reversal_down_warning = rv < 26 or (price <= float(bb_lower[i]) and rv < 32)
    atr_ok = a > 0 and a / max(price, 0.000001) >= 0.001

    # A quiet/flat VWAP plus repeated EMA crossings is treated as choppy.
    vwap_slope = abs(float(vwap[i]) - float(vwap[max(0, i - 5)]))
    recent_crosses = sum(
        1 for j in range(max(1, i - 8), i + 1)
        if (float(e9[j]) - float(e20[j])) * (float(e9[j - 1]) - float(e20[j - 1])) <= 0
    )
    choppy = vwap_slope <= max(a * 0.20, price * 0.0005) and recent_crosses >= 3

    bullish_entry = breakout_up or pullback_up
    bearish_entry = breakout_down or pullback_down

    buy_ok = (
        not choppy
        and trend_up
        and bullish
        and price > float(vwap[i])
        and rv > 52
        and macd_up
        and vol_ok
        and bullish_entry
        and not_overextended_up
        and not reversal_up_warning
        and atr_ok
    )
    sell_ok = (
        not choppy
        and trend_down
        and bearish
        and price < float(vwap[i])
        and rv < 48
        and macd_down
        and vol_ok
        and bearish_entry
        and not_overextended_down
        and not reversal_down_warning
        and atr_ok
    )

    if buy_ok:
        entry = price
        stop = min(float(e20[i]), float(vwap[i]), low[i]) - max(a * 0.25, price * 0.001)
        risk = max(entry - stop, a * 0.5)
        target = entry + 2.0 * risk
        return FusionSignal(strategy, "BUY", timeframe, _safe_round(entry), _safe_round(stop), _safe_round(target), "Bullish trend confirmed above VWAP with momentum, volume and valid breakout/pullback entry", "UPTREND", True, len(clean))

    if sell_ok:
        entry = price
        stop = max(float(e20[i]), float(vwap[i]), high[i]) + max(a * 0.25, price * 0.001)
        risk = max(stop - entry, a * 0.5)
        target = entry - 2.0 * risk
        return FusionSignal(strategy, "SELL", timeframe, _safe_round(entry), _safe_round(stop), _safe_round(target), "Bearish trend confirmed below VWAP with momentum, volume and valid breakdown/pullback entry", "DOWNTREND", True, len(clean))

    if choppy:
        reason = "Choppy market: VWAP is flat and short-term trend structure is unstable"
        regime = "CHOPPY"
    elif trend_up and bullish and price > float(vwap[i]):
        regime = "UPTREND"
        reason = "Bullish structure present, but entry confirmation is incomplete"
    elif trend_down and bearish and price < float(vwap[i]):
        regime = "DOWNTREND"
        reason = "Bearish structure present, but entry confirmation is incomplete"
    elif breakout_up or breakout_down:
        regime = "BREAKOUT"
        reason = "Breakout detected without complete volume/trend confirmation"
    else:
        regime = "SIDEWAYS"
        reason = "Market structure is not sufficiently confirmed"

    return FusionSignal(strategy, "HOLD", timeframe, None, None, None, reason, regime, False, len(clean))
