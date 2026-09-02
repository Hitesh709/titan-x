from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.models.paper_trading import PaperPosition, PaperTrade
from titan_x.services.paper_trading_service import PaperTradingService


class PersistentTradingPortfolioService:
    """Authoritative user portfolio view backed by the paper-trading ledger.

    The paper account/positions/trades are the single source of truth for the
    Trading screen and Auto Demo Bot. This service is intentionally a read
    facade so logout/login cannot create a second in-memory portfolio.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.paper = PaperTradingService(session)

    async def positions(self, user_id: int) -> list[dict[str, Any]]:
        account = await self.paper.get_account(user_id)
        if account is None:
            return []
        result = await self.session.execute(
            select(PaperPosition)
            .where(
                PaperPosition.account_id == account.id,
                PaperPosition.user_id == user_id,
                PaperPosition.quantity > 0,
            )
            .order_by(PaperPosition.symbol)
        )
        rows = result.scalars().all()
        return [self._position(row) for row in rows]

    async def orders(self, user_id: int, limit: int = 100) -> list[dict[str, Any]]:
        rows, _ = await self.paper.list_orders(user_id, skip=0, limit=limit)
        return [
            {
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
            for row in rows
        ]

    async def fills(self, user_id: int, limit: int = 100) -> list[dict[str, Any]]:
        rows, _ = await self.paper.get_trade_history(user_id, skip=0, limit=limit)
        return [
            {
                "id": row.id,
                "order_id": row.order_id,
                "symbol": row.symbol,
                "side": row.side,
                "quantity": row.quantity,
                "price": float(row.price),
                "commission": float(row.commission or Decimal("0")),
                "realized_pnl": float(row.realized_pnl) if row.realized_pnl is not None else None,
                "fill_time": row.trade_time.isoformat() if row.trade_time else None,
            }
            for row in rows
        ]

    async def snapshot(self, user_id: int) -> dict[str, Any]:
        positions = await self.positions(user_id)
        orders = await self.orders(user_id)
        fills = await self.fills(user_id)
        account = await self.paper.get_account_summary(user_id)
        summary = account or {
            "position_count": len(positions),
            "market_value": sum(item["market_value"] for item in positions),
            "realized_pnl": sum(item["realized_pnl"] for item in positions),
            "unrealized_pnl": sum(item["unrealized_pnl"] for item in positions),
        }
        return {
            "positions": positions,
            "orders": orders,
            "fills": fills,
            "summary": {
                "position_count": len(positions),
                "market_value": float(summary.get("portfolio_value", 0)),
                "realized_pnl": float(summary.get("total_realized_pnl", 0)),
                "unrealized_pnl": float(summary.get("total_unrealized_pnl", 0)),
                "total_pnl": float(summary.get("total_pnl", 0)),
            },
        }

    @staticmethod
    def _position(row: PaperPosition) -> dict[str, Any]:
        quantity = int(row.quantity or 0)
        average = float(row.average_price or 0)
        current = float(row.current_price or row.average_price or 0)
        market_value = current * quantity
        unrealized = float(row.current_price * row.quantity - row.cost_basis) if row.current_price else 0.0
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
