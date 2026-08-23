from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Position:
    symbol: str
    quantity: int
    average_price: float
    last_price: float
    realized_pnl: float = 0.0

    @property
    def market_value(self) -> float:
        return self.quantity * self.last_price

    @property
    def unrealized_pnl(self) -> float:
        return (self.last_price - self.average_price) * self.quantity

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "market_value": self.market_value, "unrealized_pnl": self.unrealized_pnl}


class PositionExposureService:
    """Tracks positions and enforces portfolio exposure limits."""

    def __init__(self, *, max_gross_exposure: float = 1_000_000.0, max_symbol_exposure: float = 250_000.0):
        if max_gross_exposure <= 0 or max_symbol_exposure <= 0:
            raise ValueError("exposure limits must be positive")
        self.max_gross_exposure = float(max_gross_exposure)
        self.max_symbol_exposure = float(max_symbol_exposure)
        self._positions: dict[str, Position] = {}

    def apply_fill(self, *, symbol: str, quantity: int, price: float) -> Position:
        symbol = symbol.strip().upper()
        if not symbol or quantity == 0 or price <= 0:
            raise ValueError("symbol, non-zero quantity and positive price are required")
        old = self._positions.get(symbol)
        if old is None:
            new_qty, avg, realized = quantity, price, 0.0
        elif old.quantity == 0 or (old.quantity > 0 and quantity > 0) or (old.quantity < 0 and quantity < 0):
            new_qty = old.quantity + quantity
            avg = ((abs(old.quantity) * old.average_price) + (abs(quantity) * price)) / (abs(old.quantity) + abs(quantity))
            realized = old.realized_pnl
        else:
            closing = min(abs(old.quantity), abs(quantity))
            realized = old.realized_pnl + closing * (price - old.average_price) * (1 if old.quantity > 0 else -1)
            new_qty = old.quantity + quantity
            avg = price if new_qty != 0 else 0.0
        candidate = Position(symbol, new_qty, avg, price, realized)
        if abs(candidate.market_value) > self.max_symbol_exposure:
            raise ValueError("symbol exposure limit exceeded")
        gross = sum(abs(p.market_value) for s, p in self._positions.items() if s != symbol) + abs(candidate.market_value)
        if gross > self.max_gross_exposure:
            raise ValueError("gross exposure limit exceeded")
        self._positions[symbol] = candidate
        return candidate

    def mark_price(self, symbol: str, price: float) -> Position:
        symbol = symbol.strip().upper()
        position = self._positions.get(symbol)
        if position is None:
            raise KeyError(symbol)
        if price <= 0:
            raise ValueError("price must be positive")
        updated = Position(position.symbol, position.quantity, position.average_price, price, position.realized_pnl)
        self._positions[symbol] = updated
        return updated

    def get(self, symbol: str) -> Position | None:
        return self._positions.get(symbol.strip().upper())

    def gross_exposure(self) -> float:
        return sum(abs(p.market_value) for p in self._positions.values())

    def net_exposure(self) -> float:
        return sum(p.market_value for p in self._positions.values())

    def snapshot(self) -> dict[str, Any]:
        return {
            "gross_exposure": self.gross_exposure(),
            "net_exposure": self.net_exposure(),
            "positions": {s: p.to_dict() for s, p in self._positions.items()},
        }
