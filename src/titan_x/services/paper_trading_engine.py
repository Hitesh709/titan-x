from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class Position:
    symbol: str
    quantity: float
    average_price: float


@dataclass(frozen=True)
class PaperTrade:
    symbol: str
    side: str
    quantity: float
    requested_price: float
    execution_price: float
    commission: float
    slippage: float
    realized_pnl: float


class PaperTradingEngine:
    """In-memory paper trading simulator; it never submits broker orders."""

    def __init__(self, initial_cash: float, commission_rate: float = 0.0, slippage_bps: float = 0.0):
        if initial_cash <= 0 or commission_rate < 0 or slippage_bps < 0:
            raise ValueError("invalid account parameters")
        self.initial_cash = float(initial_cash)
        self.cash = float(initial_cash)
        self.commission_rate = float(commission_rate)
        self.slippage_bps = float(slippage_bps)
        self.positions: dict[str, Position] = {}
        self.trades: list[PaperTrade] = []

    def execute(self, symbol: str, side: str, quantity: float, market_price: float) -> dict[str, Any]:
        side = side.upper()
        if side not in {"BUY", "SELL"}:
            raise ValueError("side must be BUY or SELL")
        if quantity <= 0 or market_price <= 0:
            raise ValueError("quantity and market_price must be positive")
        factor = 1 + self.slippage_bps / 10000 if side == "BUY" else 1 - self.slippage_bps / 10000
        execution_price = market_price * factor
        notional = quantity * execution_price
        commission = notional * self.commission_rate
        position = self.positions.get(symbol)
        realized = 0.0
        if side == "BUY":
            total_cost = notional + commission
            if total_cost > self.cash:
                raise ValueError("insufficient paper cash")
            self.cash -= total_cost
            if position:
                new_qty = position.quantity + quantity
                position.average_price = ((position.quantity * position.average_price) + notional) / new_qty
                position.quantity = new_qty
            else:
                self.positions[symbol] = Position(symbol, quantity, execution_price)
        else:
            if not position or position.quantity < quantity:
                raise ValueError("insufficient paper position")
            realized = (execution_price - position.average_price) * quantity - commission
            self.cash += notional - commission
            position.quantity -= quantity
            if position.quantity == 0:
                del self.positions[symbol]
        trade = PaperTrade(symbol, side, quantity, market_price, execution_price, commission, abs(execution_price - market_price) * quantity, realized)
        self.trades.append(trade)
        return asdict(trade)

    def equity(self, prices: dict[str, float]) -> float:
        value = self.cash
        for symbol, position in self.positions.items():
            price = prices.get(symbol)
            if price is None or price <= 0:
                raise ValueError(f"missing valid price for {symbol}")
            value += position.quantity * price
        return value

    def snapshot(self, prices: dict[str, float]) -> dict[str, Any]:
        equity = self.equity(prices)
        return {
            "cash": self.cash,
            "equity": equity,
            "unrealized_pnl": equity - self.initial_cash - sum(t.realized_pnl for t in self.trades),
            "positions": [asdict(p) for p in self.positions.values()],
            "trades": [asdict(t) for t in self.trades],
        }
