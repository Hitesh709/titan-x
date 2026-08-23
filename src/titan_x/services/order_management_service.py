from __future__ import annotations

import inspect
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable


@dataclass(frozen=True, slots=True)
class Order:
    order_id: str
    symbol: str
    side: str
    quantity: int
    order_type: str
    limit_price: float | None
    status: str
    created_at: str
    strategy: str = "default"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


OrderHandler = Callable[[Order], None | Awaitable[None]]


class OrderManagementService:
    """Validates and tracks orders before broker submission.

    Default mode is SIMULATION. A broker handler can be injected later; this
    service never assumes that an order was submitted merely because it was
    accepted internally.
    """

    VALID_SIDES = {"BUY", "SELL"}
    VALID_TYPES = {"MARKET", "LIMIT"}

    def __init__(self, *, max_quantity: int = 100_000, max_open_orders: int = 1000, mode: str = "SIMULATION"):
        if max_quantity <= 0 or max_open_orders <= 0:
            raise ValueError("order limits must be positive")
        mode = mode.upper()
        if mode not in {"SIMULATION", "BROKER"}:
            raise ValueError("mode must be SIMULATION or BROKER")
        self.max_quantity = max_quantity
        self.max_open_orders = max_open_orders
        self.mode = mode
        self._orders: dict[str, Order] = {}
        self._handler: OrderHandler | None = None

    def set_handler(self, handler: OrderHandler) -> None:
        self._handler = handler

    async def submit(self, *, symbol: str, side: str, quantity: int, order_type: str = "MARKET", limit_price: float | None = None, strategy: str = "default") -> Order:
        symbol = symbol.strip().upper()
        side = side.upper()
        order_type = order_type.upper()
        if not symbol:
            raise ValueError("symbol is required")
        if side not in self.VALID_SIDES:
            raise ValueError("side must be BUY or SELL")
        if order_type not in self.VALID_TYPES:
            raise ValueError("order_type must be MARKET or LIMIT")
        if not 1 <= int(quantity) <= self.max_quantity:
            raise ValueError(f"quantity must be between 1 and {self.max_quantity}")
        if order_type == "LIMIT" and (limit_price is None or float(limit_price) <= 0):
            raise ValueError("limit_price must be positive for LIMIT orders")
        if len([o for o in self._orders.values() if o.status in {"ACCEPTED", "SUBMITTED"}]) >= self.max_open_orders:
            raise RuntimeError("maximum open-order limit reached")

        now = datetime.now(timezone.utc).isoformat()
        status = "ACCEPTED" if self.mode == "SIMULATION" else "SUBMITTED"
        order = Order(str(uuid.uuid4()), symbol, side, int(quantity), order_type, float(limit_price) if limit_price is not None else None, status, now, strategy)
        self._orders[order.order_id] = order
        if self._handler:
            result = self._handler(order)
            if inspect.isawaitable(result):
                await result
        return order

    def cancel(self, order_id: str) -> Order:
        order = self._orders.get(order_id)
        if order is None:
            raise KeyError(order_id)
        if order.status not in {"ACCEPTED", "SUBMITTED"}:
            raise ValueError("order cannot be cancelled in its current state")
        cancelled = Order(**{**order.to_dict(), "status": "CANCELLED"})
        self._orders[order_id] = cancelled
        return cancelled

    def get(self, order_id: str) -> Order | None:
        return self._orders.get(order_id)

    def list_open(self) -> list[Order]:
        return [o for o in self._orders.values() if o.status in {"ACCEPTED", "SUBMITTED"}]

    def snapshot(self) -> list[dict[str, Any]]:
        return [o.to_dict() for o in self._orders.values()]
