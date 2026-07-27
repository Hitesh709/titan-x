from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.db.repository import BaseRepository
from titan_x.models.order import Order, OrderFill, Position


class OrderService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.order_repo = BaseRepository(session, Order)
        self.fill_repo = BaseRepository(session, OrderFill)
        self.position_repo = BaseRepository(session, Position)

    async def create_order(
        self,
        user_id: int,
        symbol: str,
        side: str,
        order_type: str,
        quantity: int,
        price: Decimal | None = None,
        stop_price: Decimal | None = None,
        time_in_force: str = "day",
    ) -> Order:
        if side not in ("buy", "sell"):
            raise ValueError("side must be 'buy' or 'sell'")
        if order_type not in ("market", "limit", "stop", "stop_limit"):
            raise ValueError("invalid order_type")
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        if order_type == "market":
            status = "open"
        else:
            status = "pending"
        order = Order(
            user_id=user_id,
            symbol=symbol.upper(),
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            stop_price=stop_price,
            time_in_force=time_in_force,
            status=status,
        )
        self.session.add(order)
        await self.session.flush()
        await self.session.refresh(order)
        return order

    async def get_order(self, order_id: int) -> Order | None:
        return await self.order_repo.get(order_id)

    async def list_orders(
        self,
        user_id: int | None = None,
        status: str | None = None,
        symbol: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Order], int]:
        q = select(Order)
        if user_id is not None:
            q = q.where(Order.user_id == user_id)
        if status is not None:
            q = q.where(Order.status == status)
        if symbol is not None:
            q = q.where(Order.symbol == symbol.upper())
        q = q.order_by(Order.created_at.desc()).offset(offset).limit(limit)
        result = await self.session.execute(q)
        rows = list(result.scalars().unique().all())

        count_q = select(Order)
        if user_id is not None:
            count_q = count_q.where(Order.user_id == user_id)
        if status is not None:
            count_q = count_q.where(Order.status == status)
        if symbol is not None:
            count_q = count_q.where(Order.symbol == symbol.upper())
        count_result = await self.session.execute(count_q)
        total = len(list(count_result.scalars().all()))
        return rows, total

    async def cancel_order(self, order_id: int) -> Order | None:
        order = await self.order_repo.get(order_id)
        if order is None:
            return None
        if order.status in ("filled", "cancelled", "rejected"):
            raise ValueError(f"Cannot cancel order in '{order.status}' status")
        order.status = "cancelled"
        await self.session.flush()
        return order

    async def execute_order(
        self,
        order_id: int,
        fill_price: Decimal,
        fill_quantity: int | None = None,
        commission: Decimal | None = None,
    ) -> tuple[Order, OrderFill, Position | None]:
        order = await self.order_repo.get(order_id)
        if order is None:
            raise ValueError("Order not found")
        if order.status in ("filled", "cancelled", "rejected"):
            raise ValueError(f"Cannot execute order in '{order.status}' status")

        qty = fill_quantity if fill_quantity is not None else order.quantity
        if qty <= 0:
            raise ValueError("fill_quantity must be positive")

        remaining = order.quantity - order.filled_quantity
        if qty > remaining:
            raise ValueError(f"fill_quantity {qty} exceeds remaining {remaining}")

        comm = commission if commission is not None else Decimal("0")
        is_sell = order.side == "sell"

        fill = OrderFill(
            order_id=order.id,
            symbol=order.symbol,
            side=order.side,
            quantity=qty,
            price=fill_price,
            commission=comm,
        )

        order.filled_quantity += qty
        if order.filled_quantity >= order.quantity:
            order.status = "filled"
        else:
            order.status = "partial"

        pos = None
        result = await self.session.execute(
            select(Position).where(
                Position.user_id == order.user_id,
                Position.symbol == order.symbol,
            )
        )
        pos = result.scalar_one_or_none()

        if pos is None:
            pos = Position(
                user_id=order.user_id,
                symbol=order.symbol,
                quantity=0,
                average_price=Decimal("0"),
                cost_basis=Decimal("0"),
                realized_pnl=Decimal("0"),
                unrealized_pnl=Decimal("0"),
            )

        if is_sell:
            if pos.quantity < qty:
                raise ValueError(f"Insufficient position: have {pos.quantity}, need {qty}")
            avg_cost = pos.average_price
            trade_pnl = (fill_price - avg_cost) * qty - comm
            fill.realized_pnl = trade_pnl
            pos.quantity -= qty
            pos.realized_pnl += trade_pnl
            if pos.quantity == 0:
                pos.average_price = Decimal("0")
                pos.cost_basis = Decimal("0")
            else:
                pos.cost_basis = pos.average_price * pos.quantity
        else:
            total_cost = pos.cost_basis + fill_price * qty + comm
            total_qty = pos.quantity + qty
            pos.average_price = total_cost / total_qty if total_qty > 0 else Decimal("0")
            pos.quantity = total_qty
            pos.cost_basis = total_cost
            fill.realized_pnl = None

        pos.current_price = fill_price
        pos.unrealized_pnl = (pos.current_price - pos.average_price) * pos.quantity if pos.quantity > 0 else Decimal("0")

        if pos.id is None:
            self.session.add(pos)
        await self.session.flush()

        return order, fill, pos

    async def get_positions(self, user_id: int) -> list[Position]:
        result = await self.session.execute(
            select(Position).where(Position.user_id == user_id).order_by(Position.symbol)
        )
        return list(result.scalars().all())

    async def get_position(self, user_id: int, symbol: str) -> Position | None:
        result = await self.session.execute(
            select(Position).where(
                Position.user_id == user_id,
                Position.symbol == symbol.upper(),
            )
        )
        return result.scalar_one_or_none()

    async def get_order_book(self, user_id: int) -> list[Order]:
        result = await self.session.execute(
            select(Order).where(
                Order.user_id == user_id,
                Order.status.in_(("pending", "open", "partial")),
            ).order_by(Order.created_at.desc())
        )
        return list(result.scalars().all())
