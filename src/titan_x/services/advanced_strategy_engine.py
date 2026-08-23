from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence


@dataclass(frozen=True)
class StrategySignal:
    action: str
    confidence: float
    price: float
    stop_loss_pct: float | None = None
    take_profit_pct: float | None = None
    signal_type: str = "advanced"
    metadata: dict[str, Any] | None = None


class AdvancedStrategyEngine:
    """Deterministic multi-indicator strategy layer for backtesting.

    The engine combines trend, momentum and volatility confirmations and
    produces risk-aware entry/exit metadata. It is deliberately stateless so
    it can be used by both batch backtests and future live/paper execution.
    """

    SUPPORTED = {"advanced_multi_indicator", "trend_momentum", "custom_advanced"}

    @staticmethod
    def _sma(values: Sequence[float], period: int) -> list[float | None]:
        if period <= 0:
            raise ValueError("period must be positive")
        out: list[float | None] = [None] * len(values)
        for i in range(period - 1, len(values)):
            window = values[i - period + 1 : i + 1]
            out[i] = sum(window) / period
        return out

    @staticmethod
    def _rsi(values: Sequence[float], period: int) -> list[float | None]:
        if period <= 0:
            raise ValueError("period must be positive")
        out: list[float | None] = [None] * len(values)
        if len(values) <= period:
            return out
        gains: list[float] = []
        losses: list[float] = []
        for i in range(1, len(values)):
            delta = values[i] - values[i - 1]
            gains.append(max(delta, 0.0))
            losses.append(max(-delta, 0.0))
        for i in range(period, len(values)):
            avg_gain = sum(gains[i - period : i]) / period
            avg_loss = sum(losses[i - period : i]) / period
            out[i] = 100.0 if avg_loss == 0 else 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)
        return out

    @staticmethod
    def _atr(high: Sequence[float], low: Sequence[float], close: Sequence[float], period: int) -> list[float | None]:
        if not (len(high) == len(low) == len(close)):
            raise ValueError("OHLC series must have equal lengths")
        if period <= 0:
            raise ValueError("period must be positive")
        tr: list[float] = []
        for i in range(len(close)):
            if i == 0:
                tr.append(high[i] - low[i])
            else:
                tr.append(max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1])))
        out: list[float | None] = [None] * len(close)
        for i in range(period - 1, len(close)):
            out[i] = sum(tr[i - period + 1 : i + 1]) / period
        return out

    def generate_signals(self, prices: Sequence[dict[str, float]], params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        params = params or {}
        closes = [float(p["close"]) for p in prices]
        highs = [float(p.get("high", p["close"])) for p in prices]
        lows = [float(p.get("low", p["close"])) for p in prices]
        if len(closes) != len(prices):
            raise ValueError("price series is invalid")
        fast = int(params.get("fast_period", 10))
        slow = int(params.get("slow_period", 30))
        rsi_period = int(params.get("rsi_period", 14))
        atr_period = int(params.get("atr_period", 14))
        min_confirmations = int(params.get("min_confirmations", 2))
        stop_loss_pct = float(params.get("stop_loss_pct", 2.0))
        take_profit_pct = float(params.get("take_profit_pct", 4.0))
        if fast <= 0 or slow <= fast or rsi_period <= 0 or atr_period <= 0:
            raise ValueError("period parameters are invalid")
        if not 1 <= min_confirmations <= 3:
            raise ValueError("min_confirmations must be between 1 and 3")
        sma_fast = self._sma(closes, fast)
        sma_slow = self._sma(closes, slow)
        rsi = self._rsi(closes, rsi_period)
        atr = self._atr(highs, lows, closes, atr_period)
        result: list[dict[str, Any]] = []
        for i, price in enumerate(closes):
            if sma_fast[i] is None or sma_slow[i] is None or rsi[i] is None or atr[i] is None:
                continue
            trend = 1 if sma_fast[i] > sma_slow[i] else -1
            momentum = 1 if 50 <= rsi[i] <= 70 else (-1 if 30 <= rsi[i] < 50 else 0)
            volatility = 1 if atr[i] / price <= float(params.get("max_atr_pct", 5.0)) / 100 else 0
            confirmations = sum((trend == 1, momentum == 1, volatility == 1))
            action = "buy" if confirmations >= min_confirmations else "hold"
            if trend < 0 and rsi[i] < 45:
                action = "sell"
            if action == "hold":
                continue
            confidence = min(1.0, confirmations / 3.0)
            result.append({
                "signal_date": prices[i].get("date"),
                "action": action,
                "price": price,
                "confidence": confidence,
                "signal_type": "advanced_multi_indicator",
                "stop_loss_pct": stop_loss_pct if action == "buy" else None,
                "take_profit_pct": take_profit_pct if action == "buy" else None,
                "metadata": {"trend": trend, "rsi": rsi[i], "atr": atr[i], "confirmations": confirmations},
            })
        return result

    @staticmethod
    def validate_params(params: dict[str, Any] | None) -> dict[str, Any]:
        params = dict(params or {})
        if params.get("trailing_stop_pct") is not None and float(params["trailing_stop_pct"]) <= 0:
            raise ValueError("trailing_stop_pct must be positive")
        if params.get("stop_loss_pct", 2.0) <= 0 or params.get("take_profit_pct", 4.0) <= 0:
            raise ValueError("stop_loss_pct and take_profit_pct must be positive")
        params["stop_loss_pct"] = float(params.get("stop_loss_pct", 2.0))
        params["take_profit_pct"] = float(params.get("take_profit_pct", 4.0))
        return params
