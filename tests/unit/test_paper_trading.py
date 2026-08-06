from datetime import date, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import event as sa_event, select, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from titan_x.db.base import Base
from titan_x.models.price import DailyPrice
from titan_x.models.user import User
from titan_x.services.paper_trading_service import PaperTradingError, PaperTradingService

ASYNC_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine(ASYNC_DB_URL, echo=False)

    @sa_event.listens_for(eng.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def user(engine):
    async with AsyncSession(engine, expire_on_commit=False) as s:
        u = User(email="trader@test.com", hashed_password="pw")
        s.add(u)
        await s.commit()
        yield u
        await s.close()


@pytest_asyncio.fixture
async def session(engine, user):
    async with AsyncSession(engine, expire_on_commit=False) as s:
        yield s


@pytest_asyncio.fixture
async def seeded_session(session, user):
    today = date.today()
    for sym, close in [("AAPL", 200), ("MSFT", 350), ("TSLA", 700)]:
        session.add(DailyPrice(symbol=sym, trade_date=today, open=close, high=close, low=close, close=close, volume=1_000_000))
        session.add(DailyPrice(symbol=sym, trade_date=today - timedelta(days=1), open=close - 5, high=close, low=close - 5, close=close - 5, volume=1_000_000))
    await session.commit()
    return session


# ── Account ──

@pytest.mark.asyncio
class TestAccount:
    async def test_create_account(self, session, user):
        svc = PaperTradingService(session)
        account = await svc.create_account(user.id)
        assert account.id is not None
        assert account.cash_balance == Decimal("100000.00")
        assert account.initial_capital == Decimal("100000.00")

    async def test_create_account_custom_capital(self, session, user):
        svc = PaperTradingService(session)
        account = await svc.create_account(user.id, Decimal("50000.00"))
        assert account.cash_balance == Decimal("50000.00")

    async def test_create_duplicate_account(self, session, user):
        svc = PaperTradingService(session)
        await svc.create_account(user.id)
        with pytest.raises(PaperTradingError, match="Account already exists"):
            await svc.create_account(user.id)

    async def test_get_account(self, session, user):
        svc = PaperTradingService(session)
        await svc.create_account(user.id)
        account = await svc.get_account(user.id)
        assert account is not None
        assert account.cash_balance == Decimal("100000.00")

    async def test_get_account_nonexistent(self, session, user):
        svc = PaperTradingService(session)
        account = await svc.get_account(user.id)
        assert account is None

    async def test_account_summary(self, session, user):
        svc = PaperTradingService(session)
        await svc.create_account(user.id)
        summary = await svc.get_account_summary(user.id)
        assert summary is not None
        assert summary["cash_balance"] == 100000.0
        assert summary["total_pnl"] == 0
        assert summary["positions_count"] == 0


# ── Market Orders ──

@pytest.mark.asyncio
class TestMarketOrders:
    async def test_buy_market_fills_immediately(self, seeded_session, user):
        svc = PaperTradingService(seeded_session)
        await svc.create_account(user.id)
        order = await svc.place_order(user.id, "AAPL", "buy", "market", 10)
        assert order.status == "filled"
        assert order.filled_quantity == 10
        account = await svc.get_account(user.id)
        expected = Decimal("100000.00") - (Decimal("200") * 10 + Decimal("200") * 10 * Decimal("0.001"))
        assert account.cash_balance == expected

    async def test_sell_market_without_position(self, seeded_session, user):
        svc = PaperTradingService(seeded_session)
        await svc.create_account(user.id)
        order = await svc.place_order(user.id, "AAPL", "sell", "market", 10)
        assert order.status == "rejected"
        assert order.rejection_reason == "Insufficient shares"

    async def test_buy_then_sell(self, seeded_session, user):
        svc = PaperTradingService(seeded_session)
        await svc.create_account(user.id)
        await svc.place_order(user.id, "AAPL", "buy", "market", 10)
        order = await svc.place_order(user.id, "AAPL", "sell", "market", 5)
        assert order.status == "filled"
        account = await svc.get_account(user.id)
        assert account.cash_balance > Decimal("0")

    async def test_insufficient_cash(self, seeded_session, user):
        svc = PaperTradingService(seeded_session)
        await svc.create_account(user.id, Decimal("100.00"))
        order = await svc.place_order(user.id, "AAPL", "buy", "market", 10)
        assert order.status == "rejected"
        assert order.rejection_reason == "Insufficient cash"


# ── Limit & Stop Orders ──

@pytest.mark.asyncio
class TestLimitStopOrders:
    async def test_limit_buy_above_price_opens(self, seeded_session, user):
        svc = PaperTradingService(seeded_session)
        await svc.create_account(user.id)
        order = await svc.place_order(user.id, "AAPL", "buy", "limit", 10, price=Decimal("150"))
        assert order.status == "open"

    async def test_limit_buy_at_price_fills(self, seeded_session, user):
        svc = PaperTradingService(seeded_session)
        await svc.create_account(user.id)
        order = await svc.place_order(user.id, "AAPL", "buy", "limit", 10, price=Decimal("250"))
        assert order.status == "filled"

    async def test_limit_sell_above_market_stays_open(self, seeded_session, user):
        svc = PaperTradingService(seeded_session)
        await svc.create_account(user.id)
        await svc.place_order(user.id, "AAPL", "buy", "market", 10)
        order = await svc.place_order(user.id, "AAPL", "sell", "limit", 5, price=Decimal("210"))
        assert order.status == "open"

    async def test_limit_sell_below_market_fills(self, seeded_session, user):
        svc = PaperTradingService(seeded_session)
        await svc.create_account(user.id)
        await svc.place_order(user.id, "AAPL", "buy", "market", 10)
        order = await svc.place_order(user.id, "AAPL", "sell", "limit", 5, price=Decimal("190"))
        assert order.status == "filled"

    async def test_stop_buy_above_price_opens(self, seeded_session, user):
        svc = PaperTradingService(seeded_session)
        await svc.create_account(user.id)
        order = await svc.place_order(user.id, "AAPL", "buy", "stop", 10, stop_price=Decimal("250"))
        assert order.status == "open"

    async def test_stop_buy_below_price_fills(self, seeded_session, user):
        svc = PaperTradingService(seeded_session)
        await svc.create_account(user.id)
        order = await svc.place_order(user.id, "AAPL", "buy", "stop", 10, stop_price=Decimal("150"))
        assert order.status == "filled"

    async def test_stop_sell_above_price_fills(self, seeded_session, user):
        svc = PaperTradingService(seeded_session)
        await svc.create_account(user.id)
        await svc.place_order(user.id, "AAPL", "buy", "market", 10)
        order = await svc.place_order(user.id, "AAPL", "sell", "stop", 5, stop_price=Decimal("210"))
        assert order.status == "filled"

    async def test_stop_sell_below_price_opens(self, seeded_session, user):
        svc = PaperTradingService(seeded_session)
        await svc.create_account(user.id)
        await svc.place_order(user.id, "AAPL", "buy", "market", 10)
        order = await svc.place_order(user.id, "AAPL", "sell", "stop", 5, stop_price=Decimal("150"))
        assert order.status == "open"


# ── Cancel Orders ──

@pytest.mark.asyncio
class TestCancel:
    async def test_cancel_open_order(self, seeded_session, user):
        svc = PaperTradingService(seeded_session)
        await svc.create_account(user.id)
        order = await svc.place_order(user.id, "AAPL", "buy", "limit", 10, price=Decimal("50"))
        assert order.status == "open"
        ok = await svc.cancel_order(order.id, user.id)
        assert ok
        cancelled = await svc.get_order(order.id, user.id)
        assert cancelled.status == "cancelled"

    async def test_cancel_filled_order_fails(self, seeded_session, user):
        svc = PaperTradingService(seeded_session)
        await svc.create_account(user.id)
        order = await svc.place_order(user.id, "AAPL", "buy", "market", 10)
        assert order.status == "filled"
        ok = await svc.cancel_order(order.id, user.id)
        assert not ok

    async def test_cancel_wrong_user(self, seeded_session, user):
        svc = PaperTradingService(seeded_session)
        await svc.create_account(user.id)
        order = await svc.place_order(user.id, "AAPL", "buy", "limit", 10, price=Decimal("50"))
        ok = await svc.cancel_order(order.id, 9999)
        assert not ok

    async def test_cancel_not_found(self, seeded_session, user):
        svc = PaperTradingService(seeded_session)
        ok = await svc.cancel_order(9999, user.id)
        assert not ok


# ── List Orders ──

@pytest.mark.asyncio
class TestListOrders:
    async def test_list_orders(self, seeded_session, user):
        svc = PaperTradingService(seeded_session)
        await svc.create_account(user.id)
        await svc.place_order(user.id, "AAPL", "buy", "market", 10)
        await svc.place_order(user.id, "MSFT", "buy", "limit", 5, price=Decimal("300"))
        rows, total = await svc.list_orders(user.id)
        assert total == 2

    async def test_list_orders_filter_status(self, seeded_session, user):
        svc = PaperTradingService(seeded_session)
        await svc.create_account(user.id)
        await svc.place_order(user.id, "AAPL", "buy", "market", 10)
        await svc.place_order(user.id, "MSFT", "buy", "limit", 5, price=Decimal("300"))
        rows, total = await svc.list_orders(user.id, status="filled")
        assert total == 1
        rows, total = await svc.list_orders(user.id, status="open")
        assert total == 1


# ── Process Open Orders ──

@pytest.mark.asyncio
class TestProcessOpen:
    async def test_process_open_orders(self, seeded_session, user):
        svc = PaperTradingService(seeded_session)
        await svc.create_account(user.id)
        await svc.place_order(user.id, "AAPL", "buy", "limit", 10, price=Decimal("50"))
        filled = await svc.process_open_orders("AAPL")
        assert filled == 0
        await svc.place_order(user.id, "MSFT", "buy", "limit", 5, price=Decimal("300"))
        filled = await svc.process_open_orders("MSFT")
        assert filled == 0
        await seeded_session.execute(
            update(DailyPrice).where(DailyPrice.symbol == "MSFT").values(close=250)
        )
        await seeded_session.commit()
        filled = await svc.process_open_orders("MSFT")
        assert filled == 1


# ── Portfolio ──

@pytest.mark.asyncio
class TestPortfolio:
    async def test_portfolio_after_buy(self, seeded_session, user):
        svc = PaperTradingService(seeded_session)
        await svc.create_account(user.id)
        await svc.place_order(user.id, "AAPL", "buy", "market", 10)
        portfolio = await svc.get_portfolio(user.id)
        assert len(portfolio) == 1
        assert portfolio[0]["symbol"] == "AAPL"
        assert portfolio[0]["quantity"] == 10
        assert portfolio[0]["average_price"] == 200.0

    async def test_portfolio_empty(self, session, user):
        svc = PaperTradingService(session)
        await svc.create_account(user.id)
        portfolio = await svc.get_portfolio(user.id)
        assert portfolio == []

    async def test_refresh_prices(self, seeded_session, user):
        svc = PaperTradingService(seeded_session)
        await svc.create_account(user.id)
        await svc.place_order(user.id, "AAPL", "buy", "market", 10)
        updated = await svc.refresh_prices(user.id)
        assert updated >= 1


# ── PnL ──

@pytest.mark.asyncio
class TestPnL:
    async def test_pnl_initial(self, session, user):
        svc = PaperTradingService(session)
        await svc.create_account(user.id)
        pnl = await svc.get_pnl_summary(user.id)
        assert pnl["total_pnl"] == 0

    async def test_pnl_after_buy(self, seeded_session, user):
        svc = PaperTradingService(seeded_session)
        await svc.create_account(user.id)
        await svc.place_order(user.id, "AAPL", "buy", "market", 10)
        pnl = await svc.get_pnl_summary(user.id)
        assert pnl["total_realized_pnl"] == 0
        assert pnl["total_unrealized_pnl"] == 0

    async def test_pnl_after_buy_and_sell(self, seeded_session, user):
        svc = PaperTradingService(seeded_session)
        await svc.create_account(user.id)
        await svc.place_order(user.id, "AAPL", "buy", "market", 10)
        await seeded_session.execute(
            update(DailyPrice).where(DailyPrice.symbol == "AAPL").values(close=210)
        )
        await seeded_session.commit()
        await svc.place_order(user.id, "AAPL", "sell", "market", 5)
        pnl = await svc.get_pnl_summary(user.id)
        assert pnl["total_realized_pnl"] != 0


# ── Reports ──

@pytest.mark.asyncio
class TestReports:
    async def test_trade_history(self, seeded_session, user):
        svc = PaperTradingService(seeded_session)
        await svc.create_account(user.id)
        await svc.place_order(user.id, "AAPL", "buy", "market", 10)
        rows, total = await svc.get_trade_history(user.id)
        assert total == 1
        assert rows[0].symbol == "AAPL"
        assert rows[0].side == "buy"

    async def test_performance_report(self, seeded_session, user):
        svc = PaperTradingService(seeded_session)
        await svc.create_account(user.id)
        await svc.place_order(user.id, "AAPL", "buy", "market", 10)
        report = await svc.get_performance_report(user.id)
        assert report["account"] is not None
        assert report["total_trades"] == 1
        assert report["filled_orders"] == 1

    async def test_performance_report_no_account(self, session, user):
        svc = PaperTradingService(session)
        report = await svc.get_performance_report(user.id)
        assert report == {}


# ── Validation ──

@pytest.mark.asyncio
class TestValidation:
    async def test_place_order_no_account(self, session, user):
        svc = PaperTradingService(session)
        with pytest.raises(PaperTradingError, match="No paper account"):
            await svc.place_order(user.id, "AAPL", "buy", "market", 10)

    async def test_invalid_side(self, session, user):
        svc = PaperTradingService(session)
        await svc.create_account(user.id)
        with pytest.raises(PaperTradingError, match="Side must be"):
            await svc.place_order(user.id, "AAPL", "invalid", "market", 10)

    async def test_invalid_order_type(self, session, user):
        svc = PaperTradingService(session)
        await svc.create_account(user.id)
        with pytest.raises(PaperTradingError, match="Invalid order type"):
            await svc.place_order(user.id, "AAPL", "buy", "invalid", 10)

    async def test_zero_quantity(self, session, user):
        svc = PaperTradingService(session)
        await svc.create_account(user.id)
        with pytest.raises(PaperTradingError, match="Quantity must be positive"):
            await svc.place_order(user.id, "AAPL", "buy", "market", 0)


# ── Simulated Orders ──

@pytest.mark.asyncio
class TestSimulatedOrders:
    async def test_buy_creates_open_simulated_order(self, seeded_session, user):
        svc = PaperTradingService(seeded_session)
        await svc.create_account(user.id)
        await svc.place_order(user.id, "AAPL", "buy", "market", 10)
        rows, total = await svc.list_simulated_orders(user.id)
        assert total == 1
        sim = rows[0]
        assert sim.symbol == "AAPL"
        assert sim.status == "open"
        assert sim.direction == "long"
        assert sim.entry_price == Decimal("200")
        assert sim.quantity == 10
        assert sim.outcome is None

    async def test_buy_sell_marks_as_closed_with_outcome(self, seeded_session, user):
        svc = PaperTradingService(seeded_session)
        await svc.create_account(user.id)
        await svc.place_order(user.id, "AAPL", "buy", "market", 10)
        await seeded_session.execute(
            update(DailyPrice).where(DailyPrice.symbol == "AAPL").values(close=210)
        )
        await seeded_session.commit()
        await svc.place_order(user.id, "AAPL", "sell", "market", 10)
        rows, total = await svc.list_simulated_orders(user.id)
        assert total == 1
        sim = rows[0]
        assert sim.status == "closed"
        assert sim.outcome == "win"
        assert sim.exit_price == Decimal("210")
        assert sim.gross_pnl == Decimal("100")
        assert sim.net_pnl is not None

    async def test_sell_without_buy_does_not_create_simulated(self, seeded_session, user):
        svc = PaperTradingService(seeded_session)
        await svc.create_account(user.id)
        await svc.place_order(user.id, "AAPL", "sell", "market", 10)
        rows, total = await svc.list_simulated_orders(user.id)
        assert total == 0

    async def test_partial_sell_leaves_sim_open(self, seeded_session, user):
        svc = PaperTradingService(seeded_session)
        await svc.create_account(user.id)
        await svc.place_order(user.id, "AAPL", "buy", "market", 10)
        await svc.place_order(user.id, "AAPL", "sell", "market", 3)
        rows, total = await svc.list_simulated_orders(user.id)
        assert total == 1
        sim = rows[0]
        assert sim.status == "open"
        assert sim.quantity == 7
        assert sim.exit_price == Decimal("200")
        assert sim.gross_pnl == Decimal("0")

    async def test_sell_loss_outcome(self, seeded_session, user):
        svc = PaperTradingService(seeded_session)
        await svc.create_account(user.id)
        await svc.place_order(user.id, "AAPL", "buy", "market", 10)
        await seeded_session.execute(
            update(DailyPrice).where(DailyPrice.symbol == "AAPL").values(close=190)
        )
        await seeded_session.commit()
        await svc.place_order(user.id, "AAPL", "sell", "market", 10)
        rows, total = await svc.list_simulated_orders(user.id)
        assert total == 1
        sim = rows[0]
        assert sim.status == "closed"
        assert sim.outcome == "loss"

    async def test_sell_same_price_is_loss_due_to_fees(self, seeded_session, user):
        svc = PaperTradingService(seeded_session)
        await svc.create_account(user.id)
        await svc.place_order(user.id, "AAPL", "buy", "market", 10)
        await svc.place_order(user.id, "AAPL", "sell", "market", 10)
        rows, total = await svc.list_simulated_orders(user.id)
        assert total == 1
        sim = rows[0]
        assert sim.status == "closed"
        assert sim.outcome == "loss"

    async def test_list_filter_by_status(self, seeded_session, user):
        svc = PaperTradingService(seeded_session)
        await svc.create_account(user.id)
        await svc.place_order(user.id, "AAPL", "buy", "market", 10)
        open_rows, open_total = await svc.list_simulated_orders(user.id, status="open")
        assert open_total == 1
        closed_rows, closed_total = await svc.list_simulated_orders(user.id, status="closed")
        assert closed_total == 0

    async def test_list_filter_by_outcome(self, seeded_session, user):
        svc = PaperTradingService(seeded_session)
        await svc.create_account(user.id)
        await svc.place_order(user.id, "AAPL", "buy", "market", 10)
        await svc.place_order(user.id, "AAPL", "sell", "market", 10)
        loss_rows, loss_total = await svc.list_simulated_orders(user.id, outcome="loss")
        assert loss_total == 1

    async def test_get_simulated_order(self, seeded_session, user):
        svc = PaperTradingService(seeded_session)
        await svc.create_account(user.id)
        await svc.place_order(user.id, "AAPL", "buy", "market", 10)
        rows, _ = await svc.list_simulated_orders(user.id)
        sim_id = rows[0].id
        sim = await svc.get_simulated_order(sim_id, user.id)
        assert sim is not None
        assert sim.id == sim_id

    async def test_get_simulated_order_wrong_user(self, seeded_session, user):
        svc = PaperTradingService(seeded_session)
        await svc.create_account(user.id)
        await svc.place_order(user.id, "AAPL", "buy", "market", 10)
        rows, _ = await svc.list_simulated_orders(user.id)
        sim_id = rows[0].id
        sim = await svc.get_simulated_order(sim_id, 9999)
        assert sim is None

    async def test_get_simulated_order_not_found(self, seeded_session, user):
        svc = PaperTradingService(seeded_session)
        sim = await svc.get_simulated_order(9999, user.id)
        assert sim is None

    async def test_slippage_on_limit_order(self, seeded_session, user):
        svc = PaperTradingService(seeded_session)
        await svc.create_account(user.id)
        order = await svc.place_order(user.id, "AAPL", "buy", "limit", 10, price=Decimal("250"))
        assert order.slippage is not None
        assert order.slippage == Decimal("-50")  # 200 - 250

    async def test_slippage_on_stop_order(self, seeded_session, user):
        svc = PaperTradingService(seeded_session)
        await svc.create_account(user.id)
        order = await svc.place_order(user.id, "AAPL", "buy", "stop", 10, stop_price=Decimal("150"))
        assert order.slippage is not None
        assert order.slippage == Decimal("50")  # 200 - 150

    async def test_slippage_on_market_order(self, seeded_session, user):
        svc = PaperTradingService(seeded_session)
        await svc.create_account(user.id)
        order = await svc.place_order(user.id, "AAPL", "buy", "market", 10)
        assert order.slippage is None


# ── Live Quote Fallback (no stored price) ──

class FakeProvider:
    def __init__(self, quote: dict):
        self._quote = quote
        self.closed = False

    async def get_quote(self, symbol: str) -> dict:
        return {**self._quote, "symbol": symbol}

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
class TestLiveQuoteFallback:
    async def test_market_order_fills_with_genuine_live_quote(
        self, session, user, monkeypatch,
    ):
        svc = PaperTradingService(session)
        await svc.create_account(user.id)
        provider = FakeProvider({"last_price": 1500.0, "source": "yahoo"})
        monkeypatch.setattr(
            "titan_x.services.paper_trading_service.get_market_data_provider",
            lambda name: provider,
        )
        order = await svc.place_order(user.id, "RELIANCE", "buy", "market", 10)
        assert order.status == "filled"
        assert order.filled_quantity == 10
        assert provider.closed
        portfolio = await svc.get_portfolio(user.id)
        assert any(p["symbol"] == "RELIANCE" and p["quantity"] == 10 and p["average_price"] == 1500.0 for p in portfolio)

    async def test_market_order_rejects_fabricated_fallback_quote(
        self, session, user, monkeypatch,
    ):
        svc = PaperTradingService(session)
        await svc.create_account(user.id)
        provider = FakeProvider({"last_price": 150.0, "source": "yahoo-fallback"})
        monkeypatch.setattr(
            "titan_x.services.paper_trading_service.get_market_data_provider",
            lambda name: provider,
        )
        order = await svc.place_order(user.id, "RELIANCE", "buy", "market", 10)
        assert order.status != "filled"
        assert order.filled_quantity == 0
        assert provider.closed
