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

    Combines trend, momentum and volatility confirmations and emits risk-aware
    entry/exit metadata. The engine is stateless so the same calculations are
    reproducible in backtests, paper trading and future live execution.
    """

    SUPPORTED = {"advanced_multi_indicator", "trend_momentum", "custom_advanced"}

    @staticmethod
    def _sma(values: Sequence[float], period: int) -> list[float | None]:
        if period <= 0:
            raise ValueError("period must be positive")
        out: list[float | None] = [None] * len(values)
        for i in range(period - 1, len(values)):
            out[i] = sum(values[i - period + 1 : i + 1]) / period
        return out

    @staticmethod
    def _rsi(values: Sequence[float], period: int) -> list[float | None]:
        if period <= 0:
            raise ValueError("period must be positive")
        out: list[float | None] = [None] * len(values)
        if len(values) <= period:
            return out
        gains = [max(values[i] - values[i - 1], 0.0) for i in range(1, len(values))]
        losses = [max(values[i - 1] - values[i], 0.0) for i in range(1, len(values))]
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
        tr = []
        for i in range(len(close)):
            tr.append(high[i] - low[i] if i == 0 else max(
                high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1])
            ))
        out: list[float | None] = [None] * len(close)
        for i in range(period - 1, len(close)):
            out[i] = sum(tr[i - period + 1 : i + 1]) / period
        return out

    def generate_signals(self, prices: Sequence[dict[str, Any]], params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        params = self.validate_params(params)
        closes = [float(p["close"]) for p in prices]
        highs = [float(p.get("high", p["close"])) for p in prices]
        lows = [float(p.get("low", p["close"])) for p in prices]
        if not prices:
            return []
        fast = int(params.get("fast_period", 10))
        slow = int(params.get("slow_period", 30))
        rsi_period = int(params.get("rsi_period", 14))
        atr_period = int(params.get("atr_period", 14))
        min_confirmations = int(params.get("min_confirmations", 2))
        sma_fast, sma_slow = self._sma(closes, fast), self._sma(closes, slow)
        rsi, atr = self._rsi(closes, rsi_period), self._atr(highs, lows, closes, atr_period)
        result: list[dict[str, Any]] = []
        for i, price in enumerate(closes):
            if sma_fast[i] is None or sma_slow[i] is None or rsi[i] is None or atr[i] is None:
                continue
            trend = 1 if sma_fast[i] > sma_slow[i] else -1
            momentum = 1 if 50 <= rsi[i] <= 70 else (-1 if 30 <= rsi[i] < 50 else 0)
            volatility = 1 if atr[i] / price <= float(params.get("max_atr_pct", 5.0)) / 100 else 0
            confirmations = int(trend == 1) + int(momentum == 1) + int(volatility == 1)
            action = "buy" if confirmations >= min_confirmations else "hold"
            if trend < 0 and rsi[i] < 45:
                action = "sell"
            if action == "hold":
                continue
            result.append({
                "signal_date": prices[i].get("date"),
                "action": action,
                "price": price,
                "confidence": min(1.0, confirmations / 3.0),
                "signal_type": "advanced_multi_indicator",
                "stop_loss_pct": params["stop_loss_pct"] if action == "buy" else None,
                "take_profit_pct": params["take_profit_pct"] if action == "buy" else None,
                "trailing_stop_pct": params.get("trailing_stop_pct") if action == "buy" else None,
                "metadata": {"trend": trend, "rsi": rsi[i], "atr": atr[i], "confirmations": confirmations},
            })
        return result

    @staticmethod
    def trailing_stop(entry_price: float, highest_price: float, trailing_stop_pct: float) -> float:
        """Return the current long trailing-stop price."""
        if entry_price <= 0 or highest_price <= 0:
            raise ValueError("prices must be positive")
        if trailing_stop_pct <= 0:
            raise ValueError("trailing_stop_pct must be positive")
        peak = max(entry_price, highest_price)
        return peak * (1.0 - trailing_stop_pct / 100.0)

    @staticmethod
    def validate_params(params: dict[str, Any] | None) -> dict[str, Any]:
        params = dict(params or {})
        fast = int(params.get("fast_period", 10))
        slow = int(params.get("slow_period", 30))
        if fast <= 0 or slow <= fast:
            raise ValueError("fast_period must be positive and less than slow_period")
        if int(params.get("rsi_period", 14)) <= 0 or int(params.get("atr_period", 14)) <= 0:
            raise ValueError("rsi_period and atr_period must be positive")
        if not 1 <= int(params.get("min_confirmations", 2)) <= 3:
            raise ValueError("min_confirmations must be between 1 and 3")
        stop = float(params.get("stop_loss_pct", 2.0))
        target = float(params.get("take_profit_pct", 4.0))
        trailing = params.get("trailing_stop_pct")
        if stop <= 0 or target <= 0:
            raise ValueError("stop_loss_pct and take_profit_pct must be positive")
        if trailing is not None and float(trailing) <= 0:
            raise ValueError("trailing_stop_pct must be positive")
        params.update({"fast_period": fast, "slow_period": slow, "rsi_period": int(params.get("rsi_period", 14)), "atr_period": int(params.get("atr_period", 14)), "min_confirmations": int(params.get("min_confirmations", 2)), "stop_loss_pct": stop, "take_profit_pct": target})
        if trailing is not None:
            params["trailing_stop_pct"] = float(trailing)
        return params
