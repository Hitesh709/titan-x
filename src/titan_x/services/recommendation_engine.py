"""Live stock recommendation engine.

Computes a full recommendation (signal, confidence, expected return, holding
period, risk, supporting evidence and reasons for caution) from a sequence of
real daily price bars plus optional sector and market-breadth context.

Pure computation - no I/O. All inputs are passed in so it is trivially
testable and cheap to run over a full market universe.
"""
from __future__ import annotations

import math
from datetime import date
from typing import Any

HORIZONS = [5, 10, 15, 20, 30]
DEFAULT_HOLDING = 15
MOMENTUM_WINDOWS = {5: 0.1, 20: 0.35, 60: 0.3, 120: 0.15, 250: 0.1}


def _ema(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    k = 2.0 / (period + 1)
    out: list[float] = []
    ema = values[0]
    for v in values:
        ema = v * k + ema * (1 - k)
        out.append(ema)
    return out


def _sma(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def _rsi(closes: list[float], period: int = 14) -> float | None:
    if len(closes) <= period:
        return None
    gains: list[float] = []
    losses: list[float] = []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0.0))
        losses.append(max(-diff, 0.0))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _macd(closes: list[float], fast: int = 12, slow: int = 26, signal: int = 9) -> dict[str, float | None]:
    if len(closes) < slow + signal:
        return {"macd": None, "signal": None, "histogram": None}
    ema_fast = _ema(closes, fast)
    ema_slow = _ema(closes, slow)
    macd_line = [f - s for f, s in zip(ema_fast, ema_slow)]
    signal_line = _ema(macd_line, signal)
    return {
        "macd": macd_line[-1],
        "signal": signal_line[-1],
        "histogram": macd_line[-1] - signal_line[-1],
    }


def _annualized_volatility(closes: list[float]) -> float | None:
    if len(closes) < 30:
        return None
    returns = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes)) if closes[i - 1] > 0]
    if len(returns) < 20:
        return None
    mean = sum(returns) / len(returns)
    var = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    return math.sqrt(var) * math.sqrt(252) * 100


def _max_drawdown(closes: list[float]) -> float:
    peak = closes[0]
    max_dd = 0.0
    for c in closes:
        if c > peak:
            peak = c
        if peak > 0:
            dd = (peak - c) / peak * 100
            if dd > max_dd:
                max_dd = dd
    return max_dd


def _period_return(closes: list[float], days: int) -> float | None:
    if len(closes) <= days or closes[-1 - days] <= 0:
        return None
    return (closes[-1] / closes[-1 - days] - 1) * 100


def _avg_volume(volumes: list[float], window: int) -> float | None:
    if len(volumes) < window:
        return None
    return sum(volumes[-window:]) / window


class RecommendationEngine:
    """Build a recommendation dict from price bars + context."""

    def build(
        self,
        symbol: str,
        points: list[dict[str, Any]],
        sector_ctx: dict[str, Any] | None = None,
        breadth_ctx: dict[str, Any] | None = None,
        as_of_date: date | None = None,
    ) -> dict[str, Any]:
        if len(points) < 30:
            return {"symbol": symbol, "insufficient_data": True, "error": "Not enough price history"}

        closes = [float(p["close"]) for p in points]
        volumes = [float(p.get("volume") or 0) for p in points]
        last_close = closes[-1]

        returns = {
            "1W": _period_return(closes, 5),
            "1M": _period_return(closes, 20),
            "3M": _period_return(closes, 60),
            "6M": _period_return(closes, 120),
            "1Y": _period_return(closes, 250),
        }

        sma20 = _sma(closes, 20)
        sma50 = _sma(closes, 50)
        ema12 = _ema(closes, 12)[-1] if len(closes) >= 12 else None
        rsi = _rsi(closes)
        macd = _macd(closes)
        vol = _annualized_volatility(closes)
        max_dd = _max_drawdown(closes)
        avg_vol_5 = _avg_volume(volumes, 5)
        avg_vol_60 = _avg_volume(volumes, 60)
        volume_ratio = avg_vol_5 / avg_vol_60 if avg_vol_5 and avg_vol_60 and avg_vol_60 > 0 else None

        highest = max(closes)
        lowest = min(closes)
        pct_from_high = (last_close / highest - 1) * 100 if highest > 0 else 0.0
        pct_from_low = (last_close / lowest - 1) * 100 if lowest > 0 else 0.0

        momentum_score = self._momentum_score(returns)
        trend_score = self._trend_score(last_close, sma20, sma50, ema12, macd)
        rsi_score = self._rsi_score(rsi)
        volume_score = self._volume_score(volume_ratio, avg_vol_60)
        sector_score = self._sector_score(sector_ctx)
        breadth_score = self._breadth_score(breadth_ctx)

        factors: list[dict[str, Any]] = []
        for label, value, weight in [
            ("momentum", momentum_score, 0.30),
            ("trend", trend_score, 0.25),
            ("rsi", rsi_score, 0.15),
            ("volume", volume_score, 0.10),
            ("sector", sector_score, 0.12),
            ("breadth", breadth_score, 0.08),
        ]:
            if value is not None:
                factors.append({"type": label, "value": value, "weight": weight})

        total_weight = sum(f["weight"] for f in factors)
        if total_weight <= 0:
            return {"symbol": symbol, "insufficient_data": True, "error": "No usable factors"}

        composite = sum(f["value"] * f["weight"] for f in factors) / total_weight
        agreement = self._agreement(factors)

        signal = self._signal(composite)
        best_horizon, expected_return = self._best_horizon(returns, closes, signal)
        holding = self._holding_period(best_horizon, returns)
        confidence = self._confidence(composite, agreement, factors, signal)
        risk_level = self._risk_level(vol, max_dd)
        price_target = round(last_close * (1 + expected_return / 100), 2) if expected_return is not None else None

        evidence = self._evidence(
            returns, trend_score, rsi, volume_ratio, sector_score, breadth_score, composite,
        )
        caution = self._caution(
            returns, rsi, vol, max_dd, pct_from_high, sector_score, breadth_score, composite,
        )

        return {
            "symbol": symbol.upper(),
            "as_of_date": (as_of_date or date.today()).isoformat(),
            "signal": signal,
            "score": round(composite, 2),
            "confidence": round(confidence, 1),
            "expected_return_pct": round(expected_return, 2) if expected_return is not None else None,
            "holding_period_days": holding,
            "risk_level": risk_level,
            "current_price": round(last_close, 2),
            "price_target": price_target,
            "returns": {k: (round(v, 2) if v is not None else None) for k, v in returns.items()},
            "indicators": {
                "sma20": round(sma20, 2) if sma20 else None,
                "sma50": round(sma50, 2) if sma50 else None,
                "ema12": round(ema12, 2) if ema12 else None,
                "rsi": round(rsi, 1) if rsi is not None else None,
                "macd": macd,
                "volatility_annualized": round(vol, 2) if vol is not None else None,
                "max_drawdown": round(max_dd, 2),
                "volume_ratio": round(volume_ratio, 2) if volume_ratio is not None else None,
                "pct_from_52w_high": round(pct_from_high, 2),
                "pct_from_52w_low": round(pct_from_low, 2),
            },
            "factors": factors,
            "evidence": evidence,
            "caution": caution,
        }

    def _momentum_score(self, returns: dict[str, float | None]) -> float | None:
        score = 0.0
        weight_sum = 0.0
        for days, weight in MOMENTUM_WINDOWS.items():
            key = {5: "1W", 20: "1M", 60: "3M", 120: "6M", 250: "1Y"}[days]
            r = returns.get(key)
            if r is not None:
                score += max(-10, min(10, r)) * weight
                weight_sum += weight
        if weight_sum == 0:
            return None
        return max(-10, min(10, score / weight_sum))

    def _trend_score(self, price: float, sma20: float | None, sma50: float | None, ema12: float | None, macd: dict[str, float | None]) -> float | None:
        score = 0.0
        parts = 0
        if sma20 is not None and sma50 is not None and sma50 > 0:
            score += 1 if sma20 > sma50 else -1
            parts += 1
        if sma20 is not None and sma20 > 0:
            score += 1 if price > sma20 else -1
            parts += 1
        if ema12 is not None and sma20 is not None and sma20 > 0:
            score += 1 if ema12 > sma20 else -1
            parts += 1
        if macd.get("histogram") is not None:
            score += 1 if macd["histogram"] > 0 else -1
            parts += 1
        if parts == 0:
            return None
        return (score / parts) * 10

    def _rsi_score(self, rsi: float | None) -> float | None:
        if rsi is None:
            return None
        if rsi >= 55 and rsi <= 70:
            return 8.0
        if rsi >= 45 and rsi < 55:
            return 3.0
        if rsi < 30:
            return 4.0  # oversold - potential bounce but risky
        if rsi > 70:
            return -6.0  # overbought
        if rsi >= 30 and rsi < 45:
            return -2.0
        return 0.0

    def _volume_score(self, volume_ratio: float | None, avg_vol_60: float | None) -> float | None:
        if volume_ratio is None:
            return None
        if volume_ratio > 1.5:
            return 6.0
        if volume_ratio > 1.1:
            return 3.0
        if volume_ratio < 0.6:
            return -4.0
        return 0.0

    def _sector_score(self, ctx: dict[str, Any] | None) -> float | None:
        if not ctx:
            return None
        momentum = ctx.get("momentum_score")
        strength = ctx.get("relative_strength")
        score = 0.0
        parts = 0
        if momentum is not None:
            score += max(-10, min(10, (momentum - 50) * 0.4))
            parts += 1
        if strength is not None:
            score += max(-10, min(10, (strength - 50) * 0.3))
            parts += 1
        if parts == 0:
            return None
        return score / parts

    def _breadth_score(self, ctx: dict[str, Any] | None) -> float | None:
        if not ctx:
            return None
        strength = ctx.get("index_strength_score")
        adv_ratio = ctx.get("adv_decl_ratio")
        score = 0.0
        parts = 0
        if strength is not None:
            score += max(-10, min(10, (strength - 50) * 0.5))
            parts += 1
        if adv_ratio is not None:
            score += max(-5, min(5, (adv_ratio - 1) * 4))
            parts += 1
        if parts == 0:
            return None
        return score / parts

    def _agreement(self, factors: list[dict[str, Any]]) -> float:
        directions = [1 if f["value"] > 0.5 else (-1 if f["value"] < -0.5 else 0) for f in factors]
        pos = sum(1 for d in directions if d > 0)
        neg = sum(1 for d in directions if d < 0)
        if pos + neg == 0:
            return 50.0
        majority = max(pos, neg)
        return majority / (pos + neg) * 100

    def _signal(self, composite: float) -> str:
        if composite > 6:
            return "strong_buy"
        if composite > 3:
            return "buy"
        if composite < -6:
            return "strong_sell"
        if composite < -3:
            return "sell"
        return "hold"

    def _best_horizon(self, returns: dict[str, float | None], closes: list[float], signal: str) -> tuple[int, float | None]:
        if signal in ("buy", "strong_buy"):
            expected = returns.get("1M") or returns.get("3M") or returns.get("6M")
            if expected is None:
                return DEFAULT_HOLDING, None
            expected = min(max(expected, 0.5), 25)
            holding = 10 if returns.get("1M") is not None and (returns["1M"] or 0) > 3 else 15
            return holding, expected
        if signal in ("sell", "strong_sell"):
            expected = -(abs(returns.get("1M") or 0) or 2.0)
            return 10, min(max(expected, -20), 0)
        best = DEFAULT_HOLDING
        best_abs = 0.0
        for h, key in ((5, "1W"), (10, "1M"), (15, "1M"), (20, "3M"), (30, "6M")):
            r = returns.get(key)
            if r is not None and abs(r) > best_abs:
                best_abs = abs(r)
                best = h
        return best, (returns.get("3M") or 0.0) * 0.5

    def _holding_period(self, best_horizon: int, returns: dict[str, float | None]) -> int:
        if best_horizon == DEFAULT_HOLDING:
            return DEFAULT_HOLDING
        return best_horizon

    def _confidence(self, composite: float, agreement: float, factors: list[dict[str, Any]], signal: str) -> float:
        base = 50 + abs(composite) * 3.5
        base = base * 0.6 + agreement * 0.4
        coverage = len(factors) / 6.0
        base = base * (0.6 + coverage * 0.4)
        base = max(45.0, min(94.0, base))
        return round(base, 1)

    def _risk_level(self, vol: float | None, max_dd: float) -> str:
        if vol is None:
            if max_dd > 45:
                return "High"
            return "Medium"
        if vol > 38 or max_dd > 50:
            return "High"
        if vol < 22 and max_dd < 25:
            return "Low"
        return "Medium"

    def _evidence(self, returns, trend_score, rsi, volume_ratio, sector_score, breadth_score, composite) -> list[str]:
        evidence: list[str] = []
        r1m = returns.get("1M")
        r3m = returns.get("3M")
        if r1m is not None and r1m > 1 and r3m is not None and r3m > 0:
            evidence.append("Positive price trend across the 1M and 3M horizons")
        elif r1m is not None and r1m > 2:
            evidence.append("Strong short-term price momentum")
        if trend_score is not None and trend_score > 0:
            evidence.append("Price above key moving averages (SMA20/SMA50) with bullish alignment")
        if rsi is not None and 50 <= rsi <= 70:
            evidence.append("RSI in the healthy bullish zone")
        if rsi is not None and rsi < 30:
            evidence.append("Oversold condition may offer a mean-reversion setup")
        if volume_ratio is not None and volume_ratio > 1.1:
            evidence.append("Healthy liquidity with above-average recent volume")
        if sector_score is not None and sector_score > 0:
            evidence.append("Favorable sector trend")
        if breadth_score is not None and breadth_score > 0:
            evidence.append("Broad market breadth supportive")
        if composite > 0:
            evidence.append("Overall technical composite is positive")
        if not evidence:
            evidence.append("No strong bullish factors currently aligned")
        return evidence

    def _caution(self, returns, rsi, vol, max_dd, pct_from_high, sector_score, breadth_score, composite) -> list[str]:
        caution: list[str] = []
        r1m = returns.get("1M")
        r3m = returns.get("3M")
        if r1m is not None and r1m < 0 and (r3m is None or r3m < 0):
            caution.append("Falling price trend across recent horizons")
        if rsi is not None and rsi > 70:
            caution.append("RSI overbought - elevated risk of a pullback")
        if pct_from_high < -25:
            caution.append("Trading well below 52-week high - lingering weakness")
        if vol is not None and vol > 38:
            caution.append("High volatility increases drawdown risk")
        elif vol is not None and vol > 28:
            caution.append("Elevated volatility - position sizing matters")
        if max_dd > 45:
            caution.append("Large historical drawdowns from peak")
        if sector_score is not None and sector_score < 0:
            caution.append("Sector trend is lagging the market")
        if breadth_score is not None and breadth_score < 0:
            caution.append("Weak market breadth may cap upside")
        if r1m is not None and r1m > 12:
            caution.append("Sharp recent run-up raises near-term correction risk")
        if not caution:
            caution.append("Monitor macro events for sudden market shifts")
        return caution