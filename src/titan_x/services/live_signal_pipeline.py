from __future__ import annotations

import inspect
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable


@dataclass(frozen=True, slots=True)
class LiveSignal:
    symbol: str
    action: str
    confidence: float
    price: float
    timestamp: str
    strategy: str = "default"
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


SignalScorer = Callable[[str, dict[str, Any]], dict[str, Any] | Awaitable[dict[str, Any]]]
SignalSubscriber = Callable[[LiveSignal], None | Awaitable[None]]


class LiveSignalPipeline:
    """Provider-neutral live quote -> signal pipeline.

    The pipeline consumes normalized quotes, invokes a strategy/scoring function,
    validates the resulting decision, deduplicates repeated decisions, and emits
    signals to subscribers. It never submits broker orders.
    """

    VALID_ACTIONS = {"BUY", "SELL", "HOLD"}

    def __init__(self, scorer: SignalScorer, *, min_confidence: float = 0.0):
        if not 0 <= min_confidence <= 100:
            raise ValueError("min_confidence must be between 0 and 100")
        self._scorer = scorer
        self.min_confidence = min_confidence
        self._subscribers: set[SignalSubscriber] = set()
        self._last_action: dict[str, str] = {}
        self._latest: dict[str, LiveSignal] = {}

    def subscribe(self, callback: SignalSubscriber) -> None:
        self._subscribers.add(callback)

    def unsubscribe(self, callback: SignalSubscriber) -> None:
        self._subscribers.discard(callback)

    def latest(self, symbol: str) -> LiveSignal | None:
        return self._latest.get(symbol.strip().upper())

    async def process_quote(self, quote: dict[str, Any]) -> LiveSignal | None:
        symbol = str(quote.get("symbol", "")).strip().upper()
        if not symbol:
            raise ValueError("quote symbol is required")
        price = float(quote.get("last_price", quote.get("price", 0)))
        if price <= 0:
            raise ValueError("quote price must be positive")

        result = self._scorer(symbol, quote)
        if inspect.isawaitable(result):
            result = await result
        if not isinstance(result, dict):
            raise ValueError("signal scorer must return a dictionary")

        action = str(result.get("action", "HOLD")).upper()
        confidence = float(result.get("confidence", 0))
        if action not in self.VALID_ACTIONS:
            raise ValueError(f"invalid signal action: {action}")
        if not 0 <= confidence <= 100:
            raise ValueError("signal confidence must be between 0 and 100")
        if confidence < self.min_confidence:
            return None

        # HOLD is retained as a signal but repeated identical actions are suppressed.
        if self._last_action.get(symbol) == action:
            return None

        signal = LiveSignal(
            symbol=symbol,
            action=action,
            confidence=confidence,
            price=price,
            timestamp=datetime.now(timezone.utc).isoformat(),
            strategy=str(result.get("strategy", "default")),
            reason=str(result["reason"]) if result.get("reason") is not None else None,
        )
        self._last_action[symbol] = action
        self._latest[symbol] = signal
        await self._publish(signal)
        return signal

    async def _publish(self, signal: LiveSignal) -> None:
        for subscriber in tuple(self._subscribers):
            try:
                result = subscriber(signal)
                if inspect.isawaitable(result):
                    await result
            except Exception:
                continue

    def snapshot(self) -> dict[str, dict[str, Any]]:
        return {symbol: signal.to_dict() for symbol, signal in self._latest.items()}
