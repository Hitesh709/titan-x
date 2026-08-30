from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class RiskDecision:
    action: str
    reason: str
    stop_loss: float | None = None
    take_profit: float | None = None


class DemoRiskEngine:
    """Risk layer for Titan-X paper trading.

    It never creates a price. It only evaluates an existing position against
    a validated current market price supplied by the market-data layer.
    """

    def __init__(self, *, stop_loss_pct: float = 1.0, take_profit_pct: float = 1.5,
                 max_position_pct: float = 20.0) -> None:
        if stop_loss_pct <= 0 or take_profit_pct <= 0:
            raise ValueError("risk percentages must be positive")
        if not 0 < max_position_pct <= 100:
            raise ValueError("max_position_pct must be between 0 and 100")
        self.stop_loss_pct = float(stop_loss_pct)
        self.take_profit_pct = float(take_profit_pct)
        self.max_position_pct = float(max_position_pct)

    def exit_decision(self, average_price: float, current_price: float) -> RiskDecision:
        if average_price <= 0 or current_price <= 0:
            return RiskDecision("hold", "invalid risk price")
        stop = average_price * (1 - self.stop_loss_pct / 100)
        target = average_price * (1 + self.take_profit_pct / 100)
        if current_price <= stop:
            return RiskDecision("sell", "stop_loss_hit", stop, target)
        if current_price >= target:
            return RiskDecision("sell", "take_profit_hit", stop, target)
        return RiskDecision("hold", "protective levels not reached", stop, target)

    def position_allowed(self, trade_amount: Decimal, portfolio_value: Decimal) -> bool:
        if trade_amount <= 0 or portfolio_value <= 0:
            return False
        return trade_amount <= portfolio_value * Decimal(str(self.max_position_pct / 100))

    def metadata(self) -> dict[str, Any]:
        return {
            "stop_loss_pct": self.stop_loss_pct,
            "take_profit_pct": self.take_profit_pct,
            "max_position_pct": self.max_position_pct,
        }
