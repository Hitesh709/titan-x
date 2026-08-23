from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.models.order import Order, OrderFill, Position


class PersistentTradingPortfolioService:
    """Authoritative DB-backed portfolio view for authenticated trading users."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def positions(self, user_id: int) -> list[dict[str, Any]]:
        result = await self.session.execute(
            select(Position)
            .where(Position.user_id == user_id, Position.quantity != 0)
            .order_by(Position.symbol)
        )
        rows = result.scalars().all()
        return [self._position(row) for row in rows]

    async def orders(self, user_id: int, limit: int = 100) -> list[dict[str, Any]]:
        result = await self.session.execute(
            select(Order)
            .where(Order.user_id == user_id)
            .order_by(Order.created_at.desc())
            .limit(limit)
        )
        return [self._order(row) for row in result.scalars().all()]

    async def fills(self, user_id: int, limit: int = 100) -> list[dict[str, Any]]:
        result = await self.session.execute(
            select(OrderFill, Order)
            .join(Order, Order.id == OrderFill.order_id)
            .where(Order.user_id == user_id)
            .order_by(OrderFill.fill_time.desc())
            .limit(limit)
        )
        return [self._fill(fill) for fill, _order in result.all()]

    async def snapshot(self, user_id: int) -> dict[str, Any]:
        positions = await self.positions(user_id)
        orders = await self.orders(user_id)
        fills = await self.fills(user_id)
        market_value = sum(item["market_value"] for item in positions)
        unrealized = sum(item["unrealized_pnl"] for item in positions)
        realized = sum(item["realized_pnl"] for item in positions)
        return {
            "positions": positions,
            "orders": orders,
            "fills": fills,
            "summary": {
                "position_count": len(positions),
                "market_value": market_value,
                "realized_pnl": realized,
                "unrealized_pnl": unrealized,
                "total_pnl": realized + unrealized,
            },
        }

    @staticmethod
    def _position(row: Position) -> dict[str, Any]:
        quantity = int(row.quantity or 0)
        average = float(row.average_price or 0)
        current = float(row.current_price or row.average_price or 0)
        market_value = current * quantity
        unrealized = float(row.unrealized_pnl or ((current - average) * quantity))
        return {
            "id": row.id,
            "symbol": row.symbol,
            "quantity": quantity,
            "average_price": average,
            "cost_basis": float(row.cost_basis or 0),
            "current_price": current,
            "market_value": market_value,
            "realized_pnl": float(row.realized_pnl or 0),
            "unrealized_pnl": unrealized,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    @staticmethod
    def _order(row: Order) -> dict[str, Any]:
        return {
            "id": row.id,
            "symbol": row.symbol,
            "side": row.side,
            "order_type": row.order_type,
            "quantity": row.quantity,
            "filled_quantity": row.filled_quantity,
            "price": float(row.price) if row.price is not None else None,
            "status": row.status,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    @staticmethod
    def _fill(row: OrderFill) -> dict[str, Any]:
        return {
            "id": row.id,
            "order_id": row.order_id,
            "symbol": row.symbol,
            "side": row.side,
            "quantity": row.quantity,
            "price": float(row.price),
            "commission": float(row.commission or Decimal("0")),
            "realized_pnl": float(row.realized_pnl) if row.realized_pnl is not None else None,
            "fill_time": row.fill_time.isoformat() if row.fill_time else None,
        }
