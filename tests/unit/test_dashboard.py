from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import event as sa_event, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from titan_x.db.base import Base
from titan_x.models.dynamic_ai_score import DynamicAIScore
from titan_x.models.news import NewsArticle
from titan_x.models.news_nlp import NewsNLPAnalysis
from titan_x.models.paper_trading import PaperAccount, PaperPosition, SimulatedOrder
from titan_x.models.price import DailyPrice
from titan_x.models.user import User
from titan_x.models.watchlist import Watchlist, WatchlistItem, WatchlistMonitorEvent
from titan_x.services.dashboard_service import DashboardService
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
        u = User(email="dash@test.com", hashed_password="pw")
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
    for sym, close in [("AAPL", 200), ("MSFT", 350)]:
        session.add(DailyPrice(symbol=sym, trade_date=today, open=close, high=close, low=close, close=close, volume=1_000_000))
        session.add(DailyPrice(symbol=sym, trade_date=today - timedelta(days=1), open=close - 5, high=close, low=close - 5, close=close - 5, volume=1_000_000))
    wl = Watchlist(user_id=user.id, name="My Watchlist")
    session.add(wl)
    await session.flush()
    session.add(WatchlistItem(watchlist_id=wl.id, symbol="AAPL"))
    session.add(WatchlistItem(watchlist_id=wl.id, symbol="MSFT"))
    await session.commit()
    return session


@pytest.mark.asyncio
class TestPortfolio:
    async def test_no_account(self, session, user):
        svc = DashboardService(session)
        result = await svc._get_portfolio_summary(user.id)
        assert result["has_account"] is False

    async def test_with_account_no_positions(self, session, user):
        svc = PaperTradingService(session)
        await svc.create_account(user.id)
        dash = DashboardService(session)
        result = await dash._get_portfolio_summary(user.id)
        assert result["has_account"] is True
        assert result["cash_balance"] == 100000.0
        assert result["positions_count"] == 0

    async def test_with_positions(self, seeded_session, user):
        trading = PaperTradingService(seeded_session)
        await trading.create_account(user.id)
        await trading.place_order(user.id, "AAPL", "buy", "market", 10)
        dash = DashboardService(seeded_session)
        result = await dash._get_portfolio_summary(user.id)
        assert result["has_account"] is True
        assert result["positions_count"] >= 1
        pos = next(p for p in result["positions"] if p["symbol"] == "AAPL")
        assert pos["quantity"] == 10


@pytest.mark.asyncio
class TestWatchlists:
    async def test_no_watchlists(self, session, user):
        svc = DashboardService(session)
        result = await svc._get_watchlists(user.id)
        assert result == []

    async def test_with_watchlists(self, seeded_session, user):
        svc = DashboardService(seeded_session)
        result = await svc._get_watchlists(user.id)
        assert len(result) == 1
        assert result[0]["name"] == "My Watchlist"
        assert result[0]["item_count"] == 2
        assert "AAPL" in result[0]["symbols"]


@pytest.mark.asyncio
class TestAIPicks:
    async def test_no_scores(self, seeded_session, user):
        svc = DashboardService(seeded_session)
        result = await svc._get_ai_picks(user.id)
        assert result == []

    async def test_buy_signal(self, seeded_session, user):
        seeded_session.add(DynamicAIScore(
            symbol="AAPL", as_of_date=date.today(),
            combined_score=0.85, combined_signal="buy", combined_confidence=0.9,
        ))
        await seeded_session.commit()
        svc = DashboardService(seeded_session)
        result = await svc._get_ai_picks(user.id)
        assert len(result) == 1
        assert result[0]["symbol"] == "AAPL"
        assert result[0]["combined_signal"] == "buy"

    async def test_sell_signal_excluded(self, seeded_session, user):
        seeded_session.add(DynamicAIScore(
            symbol="AAPL", as_of_date=date.today(),
            combined_score=0.3, combined_signal="sell", combined_confidence=0.8,
        ))
        await seeded_session.commit()
        svc = DashboardService(seeded_session)
        result = await svc._get_ai_picks(user.id)
        assert result == []


@pytest.mark.asyncio
class TestNews:
    async def test_no_news(self, seeded_session, user):
        svc = DashboardService(seeded_session)
        result = await svc._get_recent_news(user.id)
        assert result == []

    async def test_recent_news(self, seeded_session, user):
        now = datetime.now(timezone.utc)
        article = NewsArticle(symbol="AAPL", title="Great earnings", source="test", source_id="s1", url="http://test.com/a", url_hash="ha", published_at=now - timedelta(hours=12))
        seeded_session.add(article)
        await seeded_session.flush()
        seeded_session.add(NewsNLPAnalysis(article_id=article.id, sentiment_label="positive", sentiment_confidence=0.9))
        await seeded_session.commit()
        svc = DashboardService(seeded_session)
        result = await svc._get_recent_news(user.id)
        assert len(result) == 1
        assert result[0]["symbol"] == "AAPL"
        assert result[0]["sentiment"] == "positive"


@pytest.mark.asyncio
class TestPerformance:
    async def test_no_data(self, session, user):
        svc = DashboardService(session)
        result = await svc._get_performance(user.id)
        assert result["has_data"] is False

    async def test_with_trades(self, seeded_session, user):
        trading = PaperTradingService(seeded_session)
        await trading.create_account(user.id)
        await trading.place_order(user.id, "AAPL", "buy", "market", 10)
        from sqlalchemy import update
        await seeded_session.execute(update(DailyPrice).where(DailyPrice.symbol == "AAPL").values(close=210))
        await seeded_session.commit()
        await trading.place_order(user.id, "AAPL", "sell", "market", 10)
        svc = DashboardService(seeded_session)
        result = await svc._get_performance(user.id)
        assert result["has_data"] is True
        assert result["total_trades"] >= 1
        assert result["winning_trades"] >= 1


@pytest.mark.asyncio
class TestAlerts:
    async def test_no_alerts(self, seeded_session, user):
        svc = DashboardService(seeded_session)
        result = await svc._get_recent_alerts(user.id)
        assert result == []

    async def test_with_alerts(self, seeded_session, user):
        wl = (await seeded_session.execute(select(Watchlist).where(Watchlist.name == "My Watchlist"))).scalar_one()
        event = WatchlistMonitorEvent(
            user_id=user.id, watchlist_id=wl.id, symbol="AAPL",
            event_type="news", severity="warning", title="Test Alert", message="Test message",
        )
        seeded_session.add(event)
        await seeded_session.commit()
        svc = DashboardService(seeded_session)
        result = await svc._get_recent_alerts(user.id)
        assert len(result) == 1
        assert result[0]["title"] == "Test Alert"
        assert result[0]["is_read"] is False


@pytest.mark.asyncio
class TestFullDashboard:
    async def test_empty_dashboard(self, session, user):
        svc = DashboardService(session)
        result = await svc.get_dashboard(user.id)
        assert result["portfolio"]["has_account"] is False
        assert result["watchlists"] == []
        assert result["ai_picks"] == []
        assert result["news"] == []
        assert result["performance"]["has_data"] is False
        assert result["alerts"] == []

    async def test_populated_dashboard(self, seeded_session, user):
        trading = PaperTradingService(seeded_session)
        await trading.create_account(user.id)
        seeded_session.add(DynamicAIScore(
            symbol="AAPL", as_of_date=date.today(),
            combined_score=0.8, combined_signal="buy", combined_confidence=0.9,
        ))
        now = datetime.now(timezone.utc)
        article = NewsArticle(symbol="AAPL", title="Positive news", source="test", source_id="s1", url="http://test.com/a", url_hash="ha", published_at=now - timedelta(hours=6))
        seeded_session.add(article)
        await seeded_session.flush()
        seeded_session.add(NewsNLPAnalysis(article_id=article.id, sentiment_label="positive", sentiment_confidence=0.9))
        wl = (await seeded_session.execute(select(Watchlist).where(Watchlist.name == "My Watchlist"))).scalar_one()
        seeded_session.add(WatchlistMonitorEvent(
            user_id=user.id, watchlist_id=wl.id, symbol="AAPL",
            event_type="news", severity="info", title="News Alert", message="Test",
        ))
        await seeded_session.commit()
        svc = DashboardService(seeded_session)
        result = await svc.get_dashboard(user.id)
        assert result["portfolio"]["has_account"] is True
        assert len(result["watchlists"]) == 1
        assert len(result["ai_picks"]) == 1
        assert len(result["news"]) == 1
        assert len(result["alerts"]) == 1
