from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True, slots=True)
class PortfolioSnapshot:
    timestamp: str
    equity: float
    cash: float
    gross_exposure: float
    net_exposure: float
    realized_pnl: float
    unrealized_pnl: float
    total_pnl: float
    return_pct: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class LivePnlMonitorService:
    """Calculates a real-time portfolio snapshot from marked positions."""

    def __init__(self, *, starting_equity: float, cash: float | None = None) -> None:
        if starting_equity <= 0:
            raise ValueError("starting_equity must be positive")
        self.starting_equity = float(starting_equity)
        self.cash = float(starting_equity if cash is None else cash)
        self._snapshot: PortfolioSnapshot | None = None

    def update(self, *, positions: dict[str, dict[str, Any]], realized_pnl: float = 0.0) -> PortfolioSnapshot:
        gross = 0.0
        net = 0.0
        unrealized = 0.0
        for raw in positions.values():
            quantity = int(raw.get("quantity", 0))
            last_price = float(raw.get("last_price", raw.get("price", 0)))
            if quantity and last_price <= 0:
                raise ValueError("position price must be positive")
            market_value = quantity * last_price
            gross += abs(market_value)
            net += market_value
            if "unrealized_pnl" in raw:
                unrealized += float(raw["unrealized_pnl"])
            else:
                avg = float(raw.get("average_price", last_price))
                unrealized += (last_price - avg) * quantity

        total_pnl = float(realized_pnl) + unrealized
        equity = self.starting_equity + total_pnl
        return_pct = (total_pnl / self.starting_equity) * 100
        self._snapshot = PortfolioSnapshot(
            timestamp=datetime.now(timezone.utc).isoformat(),
            equity=equity,
            cash=self.cash,
            gross_exposure=gross,
            net_exposure=net,
            realized_pnl=float(realized_pnl),
            unrealized_pnl=unrealized,
            total_pnl=total_pnl,
            return_pct=return_pct,
        )
        return self._snapshot

    def latest(self) -> PortfolioSnapshot | None:
        return self._snapshot
