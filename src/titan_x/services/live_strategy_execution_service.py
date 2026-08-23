from __future__ import annotations

import inspect
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable


@dataclass(frozen=True, slots=True)
class ExecutionDecision:
    symbol: str
    action: str
    confidence: float
    price: float
    quantity: int
    strategy: str
    timestamp: str
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


DecisionHandler = Callable[[ExecutionDecision], None | Awaitable[None]]


class LiveStrategyExecutionService:
    """Turns approved live signals into execution decisions.

    This layer deliberately does not submit broker orders. It validates sizing,
    applies cooldown/deduplication, and hands an approved decision to the order
    management layer introduced in the next Sprint 4 item.
    """

    def __init__(self, *, max_quantity: int = 100_000, min_confidence: float = 70.0, cooldown_seconds: float = 0.0):
        if max_quantity <= 0:
            raise ValueError("max_quantity must be positive")
        if not 0 <= min_confidence <= 100:
            raise ValueError("min_confidence must be between 0 and 100")
        if cooldown_seconds < 0:
            raise ValueError("cooldown_seconds cannot be negative")
        self.max_quantity = max_quantity
        self.min_confidence = min_confidence
        self.cooldown_seconds = cooldown_seconds
        self._last_action: dict[str, tuple[str, float]] = {}
        self._handler: DecisionHandler | None = None

    def set_handler(self, handler: DecisionHandler) -> None:
        self._handler = handler

    async def execute(self, signal: dict[str, Any], *, quantity: int | None = None) -> ExecutionDecision | None:
        symbol = str(signal.get("symbol", "")).strip().upper()
        action = str(signal.get("action", "")).strip().upper()
        confidence = float(signal.get("confidence", 0))
        price = float(signal.get("price", 0))
        strategy = str(signal.get("strategy", "default"))
        now = datetime.now(timezone.utc)
        if not symbol:
            raise ValueError("signal symbol is required")
        if action not in {"BUY", "SELL"}:
            return None
        if not 0 <= confidence <= 100:
            raise ValueError("signal confidence must be between 0 and 100")
        if confidence < self.min_confidence:
            return None
        if price <= 0:
            raise ValueError("signal price must be positive")
        qty = int(quantity if quantity is not None else signal.get("quantity", 1))
        if qty <= 0 or qty > self.max_quantity:
            raise ValueError(f"quantity must be between 1 and {self.max_quantity}")

        previous = self._last_action.get(symbol)
        now_epoch = now.timestamp()
        if previous and previous[0] == action and now_epoch - previous[1] < self.cooldown_seconds:
            return None

        decision = ExecutionDecision(symbol, action, confidence, price, qty, strategy, now.isoformat(), signal.get("reason"))
        self._last_action[symbol] = (action, now_epoch)
        if self._handler:
            result = self._handler(decision)
            if inspect.isawaitable(result):
                await result
        return decision
