from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True, slots=True)
class RiskDecision:
    approved: bool
    reason: str
    symbol: str
    action: str
    quantity: int
    projected_exposure: float
    timestamp: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RealtimeRiskControlService:
    """Synchronous pre-trade risk gate for live execution decisions."""

    def __init__(
        self,
        *,
        max_order_value: float = 100_000.0,
        max_gross_exposure: float = 1_000_000.0,
        max_daily_loss: float = 50_000.0,
        max_position_quantity: int = 100_000,
    ) -> None:
        if min(max_order_value, max_gross_exposure, max_daily_loss) <= 0 or max_position_quantity <= 0:
            raise ValueError("risk limits must be positive")
        self.max_order_value = float(max_order_value)
        self.max_gross_exposure = float(max_gross_exposure)
        self.max_daily_loss = float(max_daily_loss)
        self.max_position_quantity = int(max_position_quantity)
        self.daily_realized_pnl = 0.0
        self._kill_switch = False

    def record_realized_pnl(self, pnl: float) -> None:
        self.daily_realized_pnl += float(pnl)

    def set_kill_switch(self, enabled: bool) -> None:
        self._kill_switch = bool(enabled)

    def approve(self, *, symbol: str, action: str, quantity: int, price: float, current_gross_exposure: float) -> RiskDecision:
        symbol = symbol.strip().upper()
        action = action.strip().upper()
        timestamp = datetime.now(timezone.utc).isoformat()
        value = abs(int(quantity) * float(price))
        projected = abs(float(current_gross_exposure)) + value

        reason = "approved"
        approved = True
        if self._kill_switch:
            approved, reason = False, "risk kill switch is enabled"
        elif action not in {"BUY", "SELL"}:
            approved, reason = False, "unsupported action"
        elif not symbol or quantity <= 0 or price <= 0:
            approved, reason = False, "invalid order parameters"
        elif quantity > self.max_position_quantity:
            approved, reason = False, "position quantity limit exceeded"
        elif value > self.max_order_value:
            approved, reason = False, "order value limit exceeded"
        elif projected > self.max_gross_exposure:
            approved, reason = False, "gross exposure limit exceeded"
        elif self.daily_realized_pnl <= -self.max_daily_loss:
            approved, reason = False, "daily loss limit reached"

        return RiskDecision(approved, reason, symbol, action, int(quantity), projected, timestamp)
