from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import event as sa_event, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from titan_x.db.base import Base
from titan_x.models.company import Company
from titan_x.models.dynamic_ai_score import DynamicAIScore
from titan_x.models.news import NewsArticle
from titan_x.models.news_nlp import NewsNLPAnalysis
from titan_x.models.financial_analysis import QuarterlyResult
from titan_x.models.risk import RiskMetrics
from titan_x.models.chart_pattern import ChartPattern
from titan_x.models.user import User
from titan_x.models.watchlist import Watchlist, WatchlistItem, WatchlistMonitorEvent
from titan_x.services.watchlist_monitor_service import WatchlistMonitorService

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
        u = User(email="watcher@test.com", hashed_password="pw")
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
    wl = Watchlist(user_id=user.id, name="Test WL")
    session.add(wl)
    await session.flush()
    session.add(WatchlistItem(watchlist_id=wl.id, symbol="AAPL"))
    session.add(WatchlistItem(watchlist_id=wl.id, symbol="MSFT"))
    await session.commit()
    return session


@pytest.mark.asyncio
class TestAIChange:
    async def test_detects_signal_change(self, seeded_session, user):
        today = date.today()
        seeded_session.add(DynamicAIScore(symbol="AAPL", as_of_date=today, combined_score=0.8, combined_signal="buy", combined_confidence=0.9))
        seeded_session.add(DynamicAIScore(symbol="AAPL", as_of_date=today - timedelta(days=1), combined_score=0.4, combined_signal="neutral", combined_confidence=0.9))
        await seeded_session.commit()

        svc = WatchlistMonitorService(seeded_session)
        wl = (await seeded_session.execute(select(Watchlist).where(Watchlist.name == "Test WL"))).scalar_one()
        events = await svc.check_watchlist(wl.id, user.id)
        assert len(events) >= 1
        ai_events = [e for e in events if e.event_type == "ai_score_change"]
        assert len(ai_events) == 1
        assert "buy" in ai_events[0].current_value

    async def test_no_change_no_event(self, seeded_session, user):
        today = date.today()
        seeded_session.add(DynamicAIScore(symbol="AAPL", as_of_date=today, combined_score=0.8, combined_signal="buy", combined_confidence=0.9))
        seeded_session.add(DynamicAIScore(symbol="AAPL", as_of_date=today - timedelta(days=1), combined_score=0.7, combined_signal="buy", combined_confidence=0.9))
        await seeded_session.commit()

        svc = WatchlistMonitorService(seeded_session)
        wl = (await seeded_session.execute(select(Watchlist).where(Watchlist.name == "Test WL"))).scalar_one()
        events = await svc.check_watchlist(wl.id, user.id)
        ai_events = [e for e in events if e.event_type == "ai_score_change"]
        assert len(ai_events) == 0


@pytest.mark.asyncio
class TestNews:
    async def test_detects_positive_news(self, seeded_session, user):
        now = datetime.now(timezone.utc)
        article = NewsArticle(symbol="AAPL", title="Great earnings beat", source="test", source_id="src1", url="http://test.com/1", url_hash="h1", published_at=now)
        seeded_session.add(article)
        await seeded_session.flush()
        seeded_session.add(NewsNLPAnalysis(article_id=article.id, sentiment_label="positive", sentiment_confidence=0.9))
        await seeded_session.commit()

        svc = WatchlistMonitorService(seeded_session)
        wl = (await seeded_session.execute(select(Watchlist).where(Watchlist.name == "Test WL"))).scalar_one()
        events = await svc.check_watchlist(wl.id, user.id)
        news_events = [e for e in events if e.event_type == "news"]
        assert len(news_events) == 1
        assert news_events[0].severity == "info"

    async def test_detects_negative_news(self, seeded_session, user):
        now = datetime.now(timezone.utc)
        article = NewsArticle(symbol="MSFT", title="Regulatory concerns", source="test", source_id="src2", url="http://test.com/2", url_hash="h2", published_at=now)
        seeded_session.add(article)
        await seeded_session.flush()
        seeded_session.add(NewsNLPAnalysis(article_id=article.id, sentiment_label="negative", sentiment_confidence=0.85))
        await seeded_session.commit()

        svc = WatchlistMonitorService(seeded_session)
        wl = (await seeded_session.execute(select(Watchlist).where(Watchlist.name == "Test WL"))).scalar_one()
        events = await svc.check_watchlist(wl.id, user.id)
        news_events = [e for e in events if e.event_type == "news"]
        assert len(news_events) == 1
        assert news_events[0].severity == "warning"

    async def test_ignores_neutral_news(self, seeded_session, user):
        now = datetime.now(timezone.utc)
        article = NewsArticle(symbol="AAPL", title="Routine update", source="test", source_id="src3", url="http://test.com/3", url_hash="h3", published_at=now)
        seeded_session.add(article)
        await seeded_session.flush()
        seeded_session.add(NewsNLPAnalysis(article_id=article.id, sentiment_label="neutral", sentiment_confidence=0.9))
        await seeded_session.commit()

        svc = WatchlistMonitorService(seeded_session)
        wl = (await seeded_session.execute(select(Watchlist).where(Watchlist.name == "Test WL"))).scalar_one()
        events = await svc.check_watchlist(wl.id, user.id)
        news_events = [e for e in events if e.event_type == "news"]
        assert len(news_events) == 0


@pytest.mark.asyncio
class TestTechnicalBreakout:
    async def test_detects_breakout(self, seeded_session, user):
        seeded_session.add(ChartPattern(
            symbol="AAPL", pattern_type="DOUBLE_BOTTOM", direction="bullish",
            start_date=date.today() - timedelta(days=5), end_date=date.today(),
            entry_price=200, target_price=220, stop_loss=190,
            confidence_score=0.75, is_active=True,
        ))
        await seeded_session.commit()

        svc = WatchlistMonitorService(seeded_session)
        wl = (await seeded_session.execute(select(Watchlist).where(Watchlist.name == "Test WL"))).scalar_one()
        events = await svc.check_watchlist(wl.id, user.id)
        breakout = [e for e in events if e.event_type == "technical_breakout"]
        assert len(breakout) == 1
        assert "DOUBLE_BOTTOM" in breakout[0].current_value

    async def test_low_confidence_no_event(self, seeded_session, user):
        seeded_session.add(ChartPattern(
            symbol="AAPL", pattern_type="HEAD_SHOULDERS", direction="bearish",
            start_date=date.today() - timedelta(days=3), end_date=date.today(),
            entry_price=200, target_price=180, stop_loss=210,
            confidence_score=0.4, is_active=True,
        ))
        await seeded_session.commit()

        svc = WatchlistMonitorService(seeded_session)
        wl = (await seeded_session.execute(select(Watchlist).where(Watchlist.name == "Test WL"))).scalar_one()
        events = await svc.check_watchlist(wl.id, user.id)
        breakout = [e for e in events if e.event_type == "technical_breakout"]
        assert len(breakout) == 0

    async def test_old_pattern_ignored(self, seeded_session, user):
        seeded_session.add(ChartPattern(
            symbol="AAPL", pattern_type="DOUBLE_TOP", direction="bearish",
            start_date=date.today() - timedelta(days=30), end_date=date.today() - timedelta(days=10),
            entry_price=200, target_price=180, stop_loss=210,
            confidence_score=0.8, is_active=True,
        ))
        await seeded_session.commit()

        svc = WatchlistMonitorService(seeded_session)
        wl = (await seeded_session.execute(select(Watchlist).where(Watchlist.name == "Test WL"))).scalar_one()
        events = await svc.check_watchlist(wl.id, user.id)
        breakout = [e for e in events if e.event_type == "technical_breakout"]
        assert len(breakout) == 0


@pytest.mark.asyncio
class TestEarnings:
    async def test_positive_eps_growth(self, seeded_session, user):
        seeded_session.add(QuarterlyResult(
            symbol="AAPL", fiscal_year=2026, quarter=2, revenue=100000,
            eps_basic=2.5, eps_diluted=2.4, eps_yoy_growth=35.0,
            filing_date=date.today() - timedelta(days=5),
            revenue_yoy_growth=15.0, gross_margin=0.4,
        ))
        await seeded_session.commit()

        svc = WatchlistMonitorService(seeded_session)
        wl = (await seeded_session.execute(select(Watchlist).where(Watchlist.name == "Test WL"))).scalar_one()
        events = await svc.check_watchlist(wl.id, user.id)
        earnings = [e for e in events if e.event_type == "earnings"]
        assert len(earnings) == 1
        assert earnings[0].severity == "info"

    async def test_negative_eps_growth(self, seeded_session, user):
        seeded_session.add(QuarterlyResult(
            symbol="MSFT", fiscal_year=2026, quarter=1, revenue=50000,
            eps_basic=1.0, eps_diluted=0.95, eps_yoy_growth=-25.0,
            filing_date=date.today() - timedelta(days=3),
            revenue_yoy_growth=-5.0, gross_margin=0.3,
        ))
        await seeded_session.commit()

        svc = WatchlistMonitorService(seeded_session)
        wl = (await seeded_session.execute(select(Watchlist).where(Watchlist.name == "Test WL"))).scalar_one()
        events = await svc.check_watchlist(wl.id, user.id)
        earnings = [e for e in events if e.event_type == "earnings"]
        assert len(earnings) == 1
        assert earnings[0].severity == "critical"

    async def test_small_eps_change_no_event(self, seeded_session, user):
        seeded_session.add(QuarterlyResult(
            symbol="AAPL", fiscal_year=2026, quarter=2, revenue=100000,
            eps_basic=2.5, eps_diluted=2.4, eps_yoy_growth=5.0,
            filing_date=date.today() - timedelta(days=5),
            revenue_yoy_growth=3.0, gross_margin=0.4,
        ))
        await seeded_session.commit()

        svc = WatchlistMonitorService(seeded_session)
        wl = (await seeded_session.execute(select(Watchlist).where(Watchlist.name == "Test WL"))).scalar_one()
        events = await svc.check_watchlist(wl.id, user.id)
        earnings = [e for e in events if e.event_type == "earnings"]
        assert len(earnings) == 0


@pytest.mark.asyncio
class TestRiskEvents:
    async def test_high_risk_score(self, seeded_session, user):
        seeded_session.add(RiskMetrics(
            symbol="AAPL", as_of_date=date.today(),
            composite_risk_score=0.85, volatility_20d=0.06,
            event_risk_score=0.7, risk_rating="high",
        ))
        await seeded_session.commit()

        svc = WatchlistMonitorService(seeded_session)
        wl = (await seeded_session.execute(select(Watchlist).where(Watchlist.name == "Test WL"))).scalar_one()
        events = await svc.check_watchlist(wl.id, user.id)
        risk = [e for e in events if e.event_type == "risk_event"]
        assert len(risk) == 1
        assert risk[0].severity == "critical"

    async def test_low_risk_no_event(self, seeded_session, user):
        seeded_session.add(RiskMetrics(
            symbol="AAPL", as_of_date=date.today(),
            composite_risk_score=0.2, volatility_20d=0.02,
            event_risk_score=0.1, risk_rating="low",
        ))
        await seeded_session.commit()

        svc = WatchlistMonitorService(seeded_session)
        wl = (await seeded_session.execute(select(Watchlist).where(Watchlist.name == "Test WL"))).scalar_one()
        events = await svc.check_watchlist(wl.id, user.id)
        risk = [e for e in events if e.event_type == "risk_event"]
        assert len(risk) == 0


@pytest.mark.asyncio
class TestCheckAll:
    async def test_check_all_watchlists(self, session, user):
        wl1 = Watchlist(user_id=user.id, name="WL1")
        wl2 = Watchlist(user_id=user.id, name="WL2")
        session.add_all([wl1, wl2])
        await session.flush()
        session.add(WatchlistItem(watchlist_id=wl1.id, symbol="AAPL"))
        session.add(WatchlistItem(watchlist_id=wl2.id, symbol="MSFT"))
        await session.commit()

        svc = WatchlistMonitorService(session)
        events = await svc.check_all_watchlists(user.id)
        assert isinstance(events, list)

    async def test_check_watchlist_wrong_user(self, seeded_session, user):
        svc = WatchlistMonitorService(seeded_session)
        events = await svc.check_watchlist(9999, user.id)
        assert events == []

    async def test_check_watchlist_different_user(self, seeded_session, user):
        wl = (await seeded_session.execute(select(Watchlist).where(Watchlist.name == "Test WL"))).scalar_one()
        svc = WatchlistMonitorService(seeded_session)
        events = await svc.check_watchlist(wl.id, 9999)
        assert events == []


@pytest.mark.asyncio
class TestEventQuery:
    async def test_list_events(self, seeded_session, user):
        wl = (await seeded_session.execute(select(Watchlist).where(Watchlist.name == "Test WL"))).scalar_one()
        svc = WatchlistMonitorService(seeded_session)
        await svc._create_event(user.id, wl.id, "AAPL", "news", "info", "Test", "Test msg")
        rows, total = await svc.list_events(user.id)
        assert total == 1
        assert rows[0].title == "Test"

    async def test_list_events_filter_type(self, seeded_session, user):
        wl = (await seeded_session.execute(select(Watchlist).where(Watchlist.name == "Test WL"))).scalar_one()
        svc = WatchlistMonitorService(seeded_session)
        await svc._create_event(user.id, wl.id, "AAPL", "news", "info", "N", "M")
        await svc._create_event(user.id, wl.id, "AAPL", "earnings", "info", "E", "M")
        news_rows, news_total = await svc.list_events(user.id, event_type="news")
        assert news_total == 1
        ear_rows, ear_total = await svc.list_events(user.id, event_type="earnings")
        assert ear_total == 1

    async def test_mark_read(self, seeded_session, user):
        wl = (await seeded_session.execute(select(Watchlist).where(Watchlist.name == "Test WL"))).scalar_one()
        svc = WatchlistMonitorService(seeded_session)
        event = await svc._create_event(user.id, wl.id, "AAPL", "news", "info", "T", "M")
        ok = await svc.mark_read(event.id, user.id)
        assert ok
        assert event.is_read is True

    async def test_mark_read_wrong_user(self, seeded_session, user):
        wl = (await seeded_session.execute(select(Watchlist).where(Watchlist.name == "Test WL"))).scalar_one()
        svc = WatchlistMonitorService(seeded_session)
        event = await svc._create_event(user.id, wl.id, "AAPL", "news", "info", "T", "M")
        ok = await svc.mark_read(event.id, 9999)
        assert not ok

    async def test_get_stats(self, seeded_session, user):
        wl = (await seeded_session.execute(select(Watchlist).where(Watchlist.name == "Test WL"))).scalar_one()
        svc = WatchlistMonitorService(seeded_session)
        stats = await svc.get_event_stats(user.id)
        assert stats["total_events"] == 0
        assert stats["unread_events"] == 0
        await svc._create_event(user.id, wl.id, "AAPL", "news", "info", "T", "M")
        stats = await svc.get_event_stats(user.id)
        assert stats["total_events"] == 1
        assert stats["unread_events"] == 1
