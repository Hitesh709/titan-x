from datetime import date, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import event as sa_event, select, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from titan_x.db.base import Base
from titan_x.models.price import DailyPrice
from titan_x.models.user import User
from titan_x.services.paper_analytics_service import PaperAnalyticsService
from titan_x.services.paper_trading_service import PaperTradingService

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


@pytest.mark.asyncio
class TestNoAccount:
    async def test_no_account_returns_empty(self, session, user):
        svc = PaperAnalyticsService(session)
        result = await svc.compute_analytics(user.id)
        assert result == {}


@pytest.mark.asyncio
class TestNoTrades:
    async def test_no_trades_returns_zeros(self, session, user):
        svc = PaperAnalyticsService(session)
        PaperTradingService(session)
        result = await svc.compute_analytics(user.id)
        assert result == {}


@pytest.mark.asyncio
class TestWinRateAndExpectancy:
    async def test_one_win(self, seeded_session, user):
        trading = PaperTradingService(seeded_session)
        await trading.create_account(user.id)
        await trading.place_order(user.id, "AAPL", "buy", "market", 10)
        await seeded_session.execute(
            update(DailyPrice).where(DailyPrice.symbol == "AAPL").values(close=210)
        )
        await seeded_session.commit()
        await trading.place_order(user.id, "AAPL", "sell", "market", 10)

        svc = PaperAnalyticsService(seeded_session)
        result = await svc.compute_analytics(user.id)
        assert result["win_rate"] == 1.0
        assert result["total_trades"] == 1
        assert result["winning_trades"] == 1
        assert result["losing_trades"] == 0
        assert result["expectancy"] > 0

    async def test_one_loss(self, seeded_session, user):
        trading = PaperTradingService(seeded_session)
        await trading.create_account(user.id)
        await trading.place_order(user.id, "AAPL", "buy", "market", 10)
        await seeded_session.execute(
            update(DailyPrice).where(DailyPrice.symbol == "AAPL").values(close=190)
        )
        await seeded_session.commit()
        await trading.place_order(user.id, "AAPL", "sell", "market", 10)

        svc = PaperAnalyticsService(seeded_session)
        result = await svc.compute_analytics(user.id)
        assert result["win_rate"] == 0.0
        assert result["total_trades"] == 1
        assert result["winning_trades"] == 0
        assert result["losing_trades"] == 1
        assert result["expectancy"] < 0

    async def test_mixed_outcomes(self, seeded_session, user):
        trading = PaperTradingService(seeded_session)
        await trading.create_account(user.id)
        await trading.place_order(user.id, "AAPL", "buy", "market", 10)
        await seeded_session.execute(
            update(DailyPrice).where(DailyPrice.symbol == "AAPL").values(close=210)
        )
        await seeded_session.commit()
        await trading.place_order(user.id, "AAPL", "sell", "market", 10)

        await trading.place_order(user.id, "MSFT", "buy", "market", 5)
        await seeded_session.execute(
            update(DailyPrice).where(DailyPrice.symbol == "MSFT").values(close=330)
        )
        await seeded_session.commit()
        await trading.place_order(user.id, "MSFT", "sell", "market", 5)

        svc = PaperAnalyticsService(seeded_session)
        result = await svc.compute_analytics(user.id)
        assert result["total_trades"] == 2
        assert result["winning_trades"] == 1
        assert result["losing_trades"] == 1
        assert result["win_rate"] == 0.5


@pytest.mark.asyncio
class TestProfitFactor:
    async def test_profit_factor(self, seeded_session, user):
        trading = PaperTradingService(seeded_session)
        await trading.create_account(user.id)
        await trading.place_order(user.id, "AAPL", "buy", "market", 10)
        await seeded_session.execute(
            update(DailyPrice).where(DailyPrice.symbol == "AAPL").values(close=220)
        )
        await seeded_session.commit()
        await trading.place_order(user.id, "AAPL", "sell", "market", 10)

        await trading.place_order(user.id, "MSFT", "buy", "market", 5)
        await seeded_session.execute(
            update(DailyPrice).where(DailyPrice.symbol == "MSFT").values(close=340)
        )
        await seeded_session.commit()
        await trading.place_order(user.id, "MSFT", "sell", "market", 5)

        svc = PaperAnalyticsService(seeded_session)
        result = await svc.compute_analytics(user.id)
        assert result["profit_factor"] > 0

    async def test_profit_factor_all_wins(self, seeded_session, user):
        trading = PaperTradingService(seeded_session)
        await trading.create_account(user.id)
        await trading.place_order(user.id, "AAPL", "buy", "market", 10)
        await seeded_session.execute(
            update(DailyPrice).where(DailyPrice.symbol == "AAPL").values(close=210)
        )
        await seeded_session.commit()
        await trading.place_order(user.id, "AAPL", "sell", "market", 10)

        svc = PaperAnalyticsService(seeded_session)
        result = await svc.compute_analytics(user.id)
        assert result["profit_factor"] == float("inf")

    async def test_profit_factor_all_losses(self, seeded_session, user):
        trading = PaperTradingService(seeded_session)
        await trading.create_account(user.id)
        await trading.place_order(user.id, "AAPL", "buy", "market", 10)
        await seeded_session.execute(
            update(DailyPrice).where(DailyPrice.symbol == "AAPL").values(close=190)
        )
        await seeded_session.commit()
        await trading.place_order(user.id, "AAPL", "sell", "market", 10)

        svc = PaperAnalyticsService(seeded_session)
        result = await svc.compute_analytics(user.id)
        assert result["profit_factor"] == 0.0


@pytest.mark.asyncio
class TestSharpeSortino:
    async def test_sharpe_and_sortino_with_two_trades(self, seeded_session, user):
        trading = PaperTradingService(seeded_session)
        await trading.create_account(user.id)
        await trading.place_order(user.id, "AAPL", "buy", "market", 10)
        await seeded_session.execute(
            update(DailyPrice).where(DailyPrice.symbol == "AAPL").values(close=210)
        )
        await seeded_session.commit()
        await trading.place_order(user.id, "AAPL", "sell", "market", 10)

        await trading.place_order(user.id, "MSFT", "buy", "market", 5)
        await seeded_session.execute(
            update(DailyPrice).where(DailyPrice.symbol == "MSFT").values(close=340)
        )
        await seeded_session.commit()
        await trading.place_order(user.id, "MSFT", "sell", "market", 5)

        svc = PaperAnalyticsService(seeded_session)
        result = await svc.compute_analytics(user.id)
        assert result["sharpe_ratio"] is not None
        assert result["sortino_ratio"] is not None

    async def test_sharpe_insufficient_trades(self, session, user):
        svc = PaperAnalyticsService(session)
        result = await svc.compute_analytics(user.id)
        assert result == {}

    async def test_sortino_no_downside(self, seeded_session, user):
        trading = PaperTradingService(seeded_session)
        await trading.create_account(user.id)
        await trading.place_order(user.id, "AAPL", "buy", "market", 10)
        await seeded_session.execute(
            update(DailyPrice).where(DailyPrice.symbol == "AAPL").values(close=210)
        )
        await seeded_session.commit()
        await trading.place_order(user.id, "AAPL", "sell", "market", 10)
        await trading.place_order(user.id, "MSFT", "buy", "market", 5)
        await seeded_session.execute(
            update(DailyPrice).where(DailyPrice.symbol == "MSFT").values(close=370)
        )
        await seeded_session.commit()
        await trading.place_order(user.id, "MSFT", "sell", "market", 5)

        svc = PaperAnalyticsService(seeded_session)
        result = await svc.compute_analytics(user.id)
        assert result["sortino_ratio"] == float("inf")


@pytest.mark.asyncio
class TestDrawdown:
    async def test_drawdown_with_losing_trade(self, seeded_session, user):
        trading = PaperTradingService(seeded_session)
        await trading.create_account(user.id, Decimal("10000.00"))
        await trading.place_order(user.id, "AAPL", "buy", "market", 10)
        await seeded_session.execute(
            update(DailyPrice).where(DailyPrice.symbol == "AAPL").values(close=150)
        )
        await seeded_session.commit()
        await trading.place_order(user.id, "AAPL", "sell", "market", 10)

        svc = PaperAnalyticsService(seeded_session)
        result = await svc.compute_analytics(user.id)
        assert result["max_drawdown"] > 0
        assert result["max_drawdown_amount"] > 0

    async def test_drawdown_no_losses(self, seeded_session, user):
        trading = PaperTradingService(seeded_session)
        await trading.create_account(user.id)
        await trading.place_order(user.id, "AAPL", "buy", "market", 10)
        await seeded_session.execute(
            update(DailyPrice).where(DailyPrice.symbol == "AAPL").values(close=210)
        )
        await seeded_session.commit()
        await trading.place_order(user.id, "AAPL", "sell", "market", 10)

        svc = PaperAnalyticsService(seeded_session)
        result = await svc.compute_analytics(user.id)
        assert result["max_drawdown"] == 0


@pytest.mark.asyncio
class TestCAGR:
    async def test_cagr_positive(self, seeded_session, user):
        trading = PaperTradingService(seeded_session)
        await trading.create_account(user.id)
        await trading.place_order(user.id, "AAPL", "buy", "market", 10)
        await seeded_session.execute(
            update(DailyPrice).where(DailyPrice.symbol == "AAPL").values(close=210)
        )
        await seeded_session.commit()
        await trading.place_order(user.id, "AAPL", "sell", "market", 10)

        svc = PaperAnalyticsService(seeded_session)
        result = await svc.compute_analytics(user.id)
        assert result["cagr"] is not None

    async def test_cagr_no_trades(self, session, user):
        PaperTradingService(session)
        svc = PaperAnalyticsService(session)
        result = await svc.compute_analytics(user.id)
        assert result == {}


@pytest.mark.asyncio
class TestCustomRiskFree:
    async def test_custom_risk_free_rate_affects_sharpe(self, seeded_session, user):
        trading = PaperTradingService(seeded_session)
        await trading.create_account(user.id)
        await trading.place_order(user.id, "AAPL", "buy", "market", 10)
        await seeded_session.execute(
            update(DailyPrice).where(DailyPrice.symbol == "AAPL").values(close=210)
        )
        await seeded_session.commit()
        await trading.place_order(user.id, "AAPL", "sell", "market", 10)
        await trading.place_order(user.id, "MSFT", "buy", "market", 5)
        await seeded_session.execute(
            update(DailyPrice).where(DailyPrice.symbol == "MSFT").values(close=340)
        )
        await seeded_session.commit()
        await trading.place_order(user.id, "MSFT", "sell", "market", 5)

        svc = PaperAnalyticsService(seeded_session)
        r1 = await svc.compute_analytics(user.id, risk_free_rate=0.0)
        r2 = await svc.compute_analytics(user.id, risk_free_rate=0.10)
        assert r1["sharpe_ratio"] != r2["sharpe_ratio"]


@pytest.mark.asyncio
class TestBrewEvenTrades:
    async def test_breakeven_trade_appears_in_count(self, seeded_session, user):
        trading = PaperTradingService(seeded_session)
        await trading.create_account(user.id)
        await trading.place_order(user.id, "AAPL", "buy", "market", 10)
        await seeded_session.execute(
            update(DailyPrice).where(DailyPrice.symbol == "AAPL").values(close=201)
        )
        await seeded_session.commit()
        await trading.place_order(user.id, "AAPL", "sell", "market", 10)

        svc = PaperAnalyticsService(seeded_session)
        result = await svc.compute_analytics(user.id)
        assert result["total_trades"] == 1
        assert result["breakeven_trades"] == 0
