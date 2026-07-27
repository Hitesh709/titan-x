from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from titan_x.db.base import Base
from titan_x.models.order import Order, OrderFill, Position
from titan_x.models.user import User
from titan_x.services.order_service import OrderService


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///")

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_fks(dbapi_con, _rec):
        cursor = dbapi_con.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as sess:
        yield sess
    await engine.dispose()


@pytest_asyncio.fixture
async def user(session: AsyncSession) -> User:
    u = User(email="test@test.com", hashed_password="hash")
    session.add(u)
    await session.flush()
    return u


@pytest_asyncio.fixture
def svc(session: AsyncSession) -> OrderService:
    return OrderService(session)


# ============================================================
# CREATE ORDER
# ============================================================

class TestCreateOrder:
    @pytest.mark.asyncio
    async def test_create_market_buy(self, svc: OrderService, user: User):
        o = await svc.create_order(user.id, "RELIANCE", "buy", "market", 100)
        assert o.symbol == "RELIANCE"
        assert o.side == "buy"
        assert o.order_type == "market"
        assert o.quantity == 100
        assert o.filled_quantity == 0
        assert o.status == "open"
        assert o.user_id == user.id

    @pytest.mark.asyncio
    async def test_create_limit_sell(self, svc: OrderService, user: User):
        o = await svc.create_order(user.id, "TCS", "sell", "limit", 50, price=Decimal("4000"))
        assert o.symbol == "TCS"
        assert o.side == "sell"
        assert o.order_type == "limit"
        assert o.price == Decimal("4000")
        assert o.status == "pending"

    @pytest.mark.asyncio
    async def test_create_stop_order(self, svc: OrderService, user: User):
        o = await svc.create_order(user.id, "INFY", "buy", "stop", 200, stop_price=Decimal("1500"))
        assert o.order_type == "stop"
        assert o.stop_price == Decimal("1500")
        assert o.status == "pending"

    @pytest.mark.asyncio
    async def test_invalid_side(self, svc: OrderService, user: User):
        with pytest.raises(ValueError, match="side must be"):
            await svc.create_order(user.id, "TEST", "invalid", "market", 10)

    @pytest.mark.asyncio
    async def test_invalid_order_type(self, svc: OrderService, user: User):
        with pytest.raises(ValueError, match="invalid order_type"):
            await svc.create_order(user.id, "TEST", "buy", "invalid", 10)

    @pytest.mark.asyncio
    async def test_zero_quantity(self, svc: OrderService, user: User):
        with pytest.raises(ValueError, match="quantity must be positive"):
            await svc.create_order(user.id, "TEST", "buy", "market", 0)

    @pytest.mark.asyncio
    async def test_uppercase_symbol(self, svc: OrderService, user: User):
        o = await svc.create_order(user.id, "abc", "buy", "market", 10)
        assert o.symbol == "ABC"


# ============================================================
# GET / LIST ORDERS
# ============================================================

class TestGetListOrders:
    @pytest.mark.asyncio
    async def test_get_order_not_found(self, svc: OrderService):
        assert await svc.get_order(9999) is None

    @pytest.mark.asyncio
    async def test_get_order(self, svc: OrderService, user: User):
        o = await svc.create_order(user.id, "TEST", "buy", "market", 10)
        fetched = await svc.get_order(o.id)
        assert fetched is not None
        assert fetched.id == o.id
        assert fetched.symbol == "TEST"

    @pytest.mark.asyncio
    async def test_list_orders_empty(self, svc: OrderService, user: User):
        rows, total = await svc.list_orders(user_id=user.id)
        assert total == 0
        assert rows == []

    @pytest.mark.asyncio
    async def test_list_orders_by_user(self, svc: OrderService, user: User, session: AsyncSession):
        u2 = User(email="other@test.com", hashed_password="hash")
        session.add(u2)
        await session.flush()
        await svc.create_order(user.id, "TEST", "buy", "market", 10)
        await svc.create_order(u2.id, "OTHER", "sell", "limit", 5)
        rows, total = await svc.list_orders(user_id=user.id)
        assert total == 1

    @pytest.mark.asyncio
    async def test_list_orders_filter_status(self, svc: OrderService, user: User):
        await svc.create_order(user.id, "A", "buy", "market", 10)
        o2 = await svc.create_order(user.id, "B", "sell", "limit", 5)
        await svc.cancel_order(o2.id)
        rows, total = await svc.list_orders(user_id=user.id, status="cancelled")
        assert total == 1

    @pytest.mark.asyncio
    async def test_list_orders_filter_symbol(self, svc: OrderService, user: User):
        await svc.create_order(user.id, "ABC", "buy", "market", 10)
        await svc.create_order(user.id, "XYZ", "sell", "limit", 5)
        rows, total = await svc.list_orders(user_id=user.id, symbol="ABC")
        assert total == 1

    @pytest.mark.asyncio
    async def test_list_all_orders_offset_limit(self, svc: OrderService, user: User):
        for i in range(5):
            await svc.create_order(user.id, f"T{i}", "buy", "market", 10)
        rows, total = await svc.list_orders(limit=2, offset=0)
        assert len(rows) == 2
        assert total == 5


# ============================================================
# CANCEL ORDER
# ============================================================

class TestCancelOrder:
    @pytest.mark.asyncio
    async def test_cancel_not_found(self, svc: OrderService):
        assert await svc.cancel_order(9999) is None

    @pytest.mark.asyncio
    async def test_cancel_pending_order(self, svc: OrderService, user: User):
        o = await svc.create_order(user.id, "TEST", "buy", "limit", 10, price=Decimal("100"))
        cancelled = await svc.cancel_order(o.id)
        assert cancelled is not None
        assert cancelled.status == "cancelled"

    @pytest.mark.asyncio
    async def test_cancel_open_order(self, svc: OrderService, user: User):
        o = await svc.create_order(user.id, "TEST", "buy", "market", 10)
        cancelled = await svc.cancel_order(o.id)
        assert cancelled.status == "cancelled"

    @pytest.mark.asyncio
    async def test_cancel_filled_order_raises(self, svc: OrderService, user: User):
        o = await svc.create_order(user.id, "TEST", "buy", "market", 10)
        await svc.execute_order(o.id, fill_price=Decimal("100"))
        with pytest.raises(ValueError, match="Cannot cancel"):
            await svc.cancel_order(o.id)


# ============================================================
# EXECUTE ORDER
# ============================================================

class TestExecuteOrder:
    @pytest.mark.asyncio
    async def test_execute_not_found(self, svc: OrderService):
        with pytest.raises(ValueError, match="Order not found"):
            await svc.execute_order(9999, fill_price=Decimal("100"))

    @pytest.mark.asyncio
    async def test_execute_buy_full_fill(self, svc: OrderService, user: User):
        o = await svc.create_order(user.id, "RELIANCE", "buy", "market", 100)
        order, fill, pos = await svc.execute_order(o.id, fill_price=Decimal("2500"))
        assert order.status == "filled"
        assert order.filled_quantity == 100
        assert fill.quantity == 100
        assert fill.price == Decimal("2500")
        assert fill.side == "buy"
        assert fill.order_id == o.id
        assert pos is not None
        assert pos.quantity == 100
        assert pos.average_price == Decimal("2500")

    @pytest.mark.asyncio
    async def test_execute_buy_partial_fill(self, svc: OrderService, user: User):
        o = await svc.create_order(user.id, "TEST", "buy", "limit", 100, price=Decimal("500"))
        order, fill, pos = await svc.execute_order(o.id, fill_price=Decimal("500"), fill_quantity=40)
        assert order.status == "partial"
        assert order.filled_quantity == 40
        assert pos.quantity == 40

    @pytest.mark.asyncio
    async def test_execute_sell_full_fill(self, svc: OrderService, user: User):
        o1 = await svc.create_order(user.id, "TEST", "buy", "market", 50)
        await svc.execute_order(o1.id, fill_price=Decimal("100"))

        o2 = await svc.create_order(user.id, "TEST", "sell", "market", 50)
        order, fill, pos = await svc.execute_order(o2.id, fill_price=Decimal("110"))

        assert order.status == "filled"
        assert pos.quantity == 0
        assert pos.realized_pnl == (Decimal("110") - Decimal("100")) * 50
        assert fill.realized_pnl is not None

    @pytest.mark.asyncio
    async def test_execute_sell_partial(self, svc: OrderService, user: User):
        o1 = await svc.create_order(user.id, "TEST", "buy", "market", 50)
        await svc.execute_order(o1.id, fill_price=Decimal("100"))

        o2 = await svc.create_order(user.id, "TEST", "sell", "market", 30)
        order, fill, pos = await svc.execute_order(o2.id, fill_price=Decimal("120"))
        assert order.status == "filled"
        assert pos.quantity == 20
        assert pos.realized_pnl > 0

    @pytest.mark.asyncio
    async def test_execute_insufficient_position(self, svc: OrderService, user: User):
        o = await svc.create_order(user.id, "TEST", "sell", "market", 10)
        with pytest.raises(ValueError, match="Insufficient position"):
            await svc.execute_order(o.id, fill_price=Decimal("100"))

    @pytest.mark.asyncio
    async def test_execute_exceeds_remaining(self, svc: OrderService, user: User):
        o = await svc.create_order(user.id, "TEST", "buy", "limit", 50, price=Decimal("100"))
        with pytest.raises(ValueError, match="exceeds remaining"):
            await svc.execute_order(o.id, fill_price=Decimal("100"), fill_quantity=100)

    @pytest.mark.asyncio
    async def test_execute_filled_order_raises(self, svc: OrderService, user: User):
        o = await svc.create_order(user.id, "TEST", "buy", "market", 10)
        await svc.execute_order(o.id, fill_price=Decimal("100"))
        with pytest.raises(ValueError, match="Cannot execute"):
            await svc.execute_order(o.id, fill_price=Decimal("100"))

    @pytest.mark.asyncio
    async def test_execute_with_commission_buy(self, svc: OrderService, user: User):
        o = await svc.create_order(user.id, "TEST", "buy", "market", 100)
        order, fill, pos = await svc.execute_order(o.id, fill_price=Decimal("500"), commission=Decimal("25"))
        assert fill.commission == Decimal("25")
        expected_avg = (Decimal("500") * 100 + Decimal("25")) / 100
        assert pos.average_price == expected_avg

    @pytest.mark.asyncio
    async def test_execute_with_commission_sell(self, svc: OrderService, user: User):
        o1 = await svc.create_order(user.id, "TEST", "buy", "market", 100)
        await svc.execute_order(o1.id, fill_price=Decimal("100"))
        o2 = await svc.create_order(user.id, "TEST", "sell", "market", 100)
        order, fill, pos = await svc.execute_order(o2.id, fill_price=Decimal("110"), commission=Decimal("10"))
        expected_pnl = (Decimal("110") - Decimal("100")) * 100 - Decimal("10")
        assert pos.realized_pnl == expected_pnl

    @pytest.mark.asyncio
    async def test_multiple_buys_average_price(self, svc: OrderService, user: User):
        o1 = await svc.create_order(user.id, "TEST", "buy", "market", 10)
        await svc.execute_order(o1.id, fill_price=Decimal("100"))

        o2 = await svc.create_order(user.id, "TEST", "buy", "market", 10)
        order, fill, pos = await svc.execute_order(o2.id, fill_price=Decimal("200"))

        assert pos.quantity == 20
        assert pos.average_price == Decimal("150")
        assert pos.cost_basis == Decimal("3000")


# ============================================================
# POSITIONS
# ============================================================

class TestPositions:
    @pytest.mark.asyncio
    async def test_get_positions_empty(self, svc: OrderService, user: User):
        pos_list = await svc.get_positions(user.id)
        assert pos_list == []

    @pytest.mark.asyncio
    async def test_get_position_not_found(self, svc: OrderService, user: User):
        assert await svc.get_position(user.id, "NONEXISTENT") is None

    @pytest.mark.asyncio
    async def test_get_positions_after_buy(self, svc: OrderService, user: User):
        o = await svc.create_order(user.id, "TEST", "buy", "market", 50)
        await svc.execute_order(o.id, fill_price=Decimal("500"))
        pos_list = await svc.get_positions(user.id)
        assert len(pos_list) == 1
        assert pos_list[0].symbol == "TEST"
        assert pos_list[0].quantity == 50

    @pytest.mark.asyncio
    async def test_get_position_by_symbol(self, svc: OrderService, user: User):
        o1 = await svc.create_order(user.id, "A", "buy", "market", 10)
        await svc.execute_order(o1.id, fill_price=Decimal("100"))
        o2 = await svc.create_order(user.id, "B", "buy", "market", 20)
        await svc.execute_order(o2.id, fill_price=Decimal("200"))

        pos = await svc.get_position(user.id, "A")
        assert pos is not None
        assert pos.quantity == 10
        assert pos.symbol == "A"

        pos = await svc.get_position(user.id, "b")
        assert pos is not None
        assert pos.quantity == 20

    @pytest.mark.asyncio
    async def test_unrealized_pnl(self, svc: OrderService, user: User):
        o = await svc.create_order(user.id, "TEST", "buy", "market", 10)
        await svc.execute_order(o.id, fill_price=Decimal("100"))
        pos = await svc.get_position(user.id, "TEST")
        assert pos is not None
        assert pos.unrealized_pnl == Decimal("0")

        o2 = await svc.create_order(user.id, "TEST", "buy", "market", 10)
        await svc.execute_order(o2.id, fill_price=Decimal("150"))
        pos = await svc.get_position(user.id, "TEST")
        assert pos.current_price == Decimal("150")
        expected_unrealized = (Decimal("150") - pos.average_price) * pos.quantity
        assert pos.unrealized_pnl == expected_unrealized


# ============================================================
# ORDER BOOK
# ============================================================

class TestOrderBook:
    @pytest.mark.asyncio
    async def test_order_book_empty(self, svc: OrderService, user: User):
        book = await svc.get_order_book(user.id)
        assert book == []

    @pytest.mark.asyncio
    async def test_order_book_shows_open_only(self, svc: OrderService, user: User):
        await svc.create_order(user.id, "T1", "buy", "market", 10)
        o2 = await svc.create_order(user.id, "T2", "sell", "limit", 5, price=Decimal("100"))
        o3 = await svc.create_order(user.id, "T3", "buy", "market", 20)
        await svc.execute_order(o3.id, fill_price=Decimal("50"))
        await svc.cancel_order(o2.id)

        book = await svc.get_order_book(user.id)
        symbols = {o.symbol for o in book}
        assert "T1" in symbols
        assert "T2" not in symbols
        assert "T3" not in symbols

    @pytest.mark.asyncio
    async def test_order_book_multi_user(self, svc: OrderService, user: User, session: AsyncSession):
        u2 = User(email="u2@test.com", hashed_password="hash")
        session.add(u2)
        await session.flush()
        await svc.create_order(user.id, "U1TEST", "buy", "market", 10)
        await svc.create_order(u2.id, "U2TEST", "buy", "market", 20)

        book_u1 = await svc.get_order_book(user.id)
        assert all(o.user_id == user.id for o in book_u1)
        assert len(book_u1) == 1
