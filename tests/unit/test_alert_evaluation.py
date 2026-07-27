from datetime import date, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from titan_x.core.config import Settings
from titan_x.db.base import Base
from titan_x.models.company import Company
from titan_x.models.price import DailyPrice
from titan_x.models.watchlist import (
    Notification,
    Watchlist,
    WatchlistAiInsight,
    WatchlistAlert,
    WatchlistItem,
)
from titan_x.services.alert_evaluation_service import AlertEvaluationService
from titan_x.services.notification_delivery_service import NotificationDeliveryService


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as sess:
        await sess.execute(select(1).where(True))
        yield sess
    await engine.dispose()


@pytest_asyncio.fixture
async def evaluator(session: AsyncSession) -> AlertEvaluationService:
    settings = Settings(
            database_url="sqlite+aiosqlite:///",
            redis_url="redis://localhost:6379/0",
                api_key="test-api-key-1234567890abcdef!!!!",
                jwt_secret_key="test-jwt-secret-1234567890abcdef!!!!",
            notification_log_only=True,
        )
    delivery = NotificationDeliveryService(settings)
    return AlertEvaluationService(session, delivery)


@pytest_asyncio.fixture
async def seeded(session: AsyncSession) -> dict:
    from titan_x.models.user import User
    u = User(email="alert@test.com", hashed_password="h", is_active=True)
    session.add(u)
    await session.flush()

    wl = Watchlist(user_id=u.id, name="Alert Test WL")
    session.add(wl)
    await session.flush()

    item = WatchlistItem(watchlist_id=wl.id, symbol="TEST", sort_order=0)
    session.add(item)

    company = Company(symbol="TEST", company_name="Test Corp", isin="US0000000001", sector="Technology", exchange="NYSE")
    session.add(company)

    today = date.today()
    for i in range(30):
        c = 100.0 + i * 0.5
        dp = DailyPrice(
            symbol="TEST", open=c, high=c + 1.0, low=c - 1.0, close=c,
            volume=1000000 + i * 5000,
            trade_date=today - timedelta(days=29 - i),
        )
        session.add(dp)
    await session.flush()

    return {"user": u, "watchlist": wl, "item": item, "symbol": "TEST"}


class TestCompare:
    @pytest.mark.asyncio
    async def test_compare_gt(self, evaluator):
        assert evaluator._compare(10.0, "gt", 5.0) is True
        assert evaluator._compare(3.0, "gt", 5.0) is False

    @pytest.mark.asyncio
    async def test_compare_gte(self, evaluator):
        assert evaluator._compare(5.0, "gte", 5.0) is True

    @pytest.mark.asyncio
    async def test_compare_lt(self, evaluator):
        assert evaluator._compare(3.0, "lt", 5.0) is True

    @pytest.mark.asyncio
    async def test_compare_eq(self, evaluator):
        assert evaluator._compare(5.0, "eq", 5.0) is True


class TestPriceAlerts:
    @pytest.mark.asyncio
    async def test_price_above_triggered(self, evaluator, session: AsyncSession, seeded: dict):
        item = seeded["item"]
        alert = WatchlistAlert(
            watchlist_item_id=item.id, alert_type="price.above",
            operator="gt", threshold_value=110.0, is_active=True,
        )
        session.add(alert)
        await session.flush()
        assert await evaluator._evaluate_alert(alert) is True

    @pytest.mark.asyncio
    async def test_price_above_not_triggered(self, evaluator, session: AsyncSession, seeded: dict):
        item = seeded["item"]
        alert = WatchlistAlert(
            watchlist_item_id=item.id, alert_type="price.above",
            operator="gt", threshold_value=200.0, is_active=True,
        )
        session.add(alert)
        await session.flush()
        assert await evaluator._evaluate_alert(alert) is False

    @pytest.mark.asyncio
    async def test_price_below_triggered(self, evaluator, session: AsyncSession, seeded: dict):
        item = seeded["item"]
        alert = WatchlistAlert(
            watchlist_item_id=item.id, alert_type="price.below",
            operator="lt", threshold_value=120.0, is_active=True,
        )
        session.add(alert)
        await session.flush()
        result = await evaluator._evaluate_alert(alert)
        assert result is True

    @pytest.mark.asyncio
    async def test_price_change_pct(self, evaluator, session: AsyncSession, seeded: dict):
        item = seeded["item"]
        alert = WatchlistAlert(
            watchlist_item_id=item.id, alert_type="price.change_pct",
            operator="gt", threshold_value=0.1, is_active=True,
        )
        session.add(alert)
        await session.flush()
        result = await evaluator._evaluate_alert(alert)
        assert result is True


class TestVolumeAlerts:
    @pytest.mark.asyncio
    async def test_volume_above_triggered(self, evaluator, session: AsyncSession, seeded: dict):
        item = seeded["item"]
        alert = WatchlistAlert(
            watchlist_item_id=item.id, alert_type="volume.above",
            operator="gt", threshold_value=500000, is_active=True,
        )
        session.add(alert)
        await session.flush()
        assert await evaluator._evaluate_alert(alert) is True

    @pytest.mark.asyncio
    async def test_volume_spike(self, evaluator, session: AsyncSession, seeded: dict):
        item = seeded["item"]
        dp = DailyPrice(
            symbol="TEST", open=200.0, high=200.0, low=200.0, close=200.0,
            volume=100_000_000,
            trade_date=date.today() + timedelta(days=1),
        )
        session.add(dp)
        await session.flush()
        alert = WatchlistAlert(
            watchlist_item_id=item.id, alert_type="volume.spike",
            operator="gt", threshold_value=2.0, is_active=True,
        )
        session.add(alert)
        await session.flush()
        assert await evaluator._evaluate_alert(alert) is True


class TestNewsAlerts:
    @pytest.mark.asyncio
    async def test_news_mention(self, evaluator, session: AsyncSession, seeded: dict):
        from datetime import datetime, timezone
        from titan_x.models.news import NewsArticle
        article = NewsArticle(
            title="Test Article", source="test", source_id="src1", url="http://test.com",
            url_hash="abc123", summary="Testing", symbol="TEST",
            published_at=datetime.now(tz=timezone.utc),
        )
        session.add(article)
        await session.flush()
        item = seeded["item"]
        alert = WatchlistAlert(
            watchlist_item_id=item.id, alert_type="news.mention",
            operator="gte", threshold_value=1, is_active=True,
        )
        session.add(alert)
        await session.flush()
        assert await evaluator._evaluate_alert(alert) is True


class TestAiScoreAlerts:
    @pytest.mark.asyncio
    async def test_ai_score_above(self, evaluator, session: AsyncSession, seeded: dict):
        wl = seeded["watchlist"]
        insight = WatchlistAiInsight(
            watchlist_id=wl.id, insight_type="momentum_alert",
            content="Test", score=85.0, symbol="TEST",
        )
        session.add(insight)
        await session.flush()
        item = seeded["item"]
        alert = WatchlistAlert(
            watchlist_item_id=item.id, alert_type="ai_score.above",
            operator="gte", threshold_value=50.0, is_active=True,
        )
        session.add(alert)
        await session.flush()
        assert await evaluator._evaluate_alert(alert) is True

    @pytest.mark.asyncio
    async def test_ai_score_below(self, evaluator, session: AsyncSession, seeded: dict):
        wl = seeded["watchlist"]
        insight = WatchlistAiInsight(
            watchlist_id=wl.id, insight_type="momentum_alert",
            content="Test", score=20.0, symbol="TEST",
        )
        session.add(insight)
        await session.flush()
        item = seeded["item"]
        alert = WatchlistAlert(
            watchlist_item_id=item.id, alert_type="ai_score.below",
            operator="lte", threshold_value=30.0, is_active=True,
        )
        session.add(alert)
        await session.flush()
        assert await evaluator._evaluate_alert(alert) is True


class TestPortfolioAlerts:
    @pytest.mark.asyncio
    async def test_holding_count(self, evaluator, session: AsyncSession, seeded: dict):
        wl = seeded["watchlist"]
        item = seeded["item"]
        alert = WatchlistAlert(
            watchlist_item_id=item.id, alert_type="portfolio.holding_count",
            operator="gte", threshold_value=1, is_active=True,
        )
        session.add(alert)
        await session.flush()
        assert await evaluator._evaluate_alert(alert) is True

    @pytest.mark.asyncio
    async def test_holding_count_not_triggered(self, evaluator, session: AsyncSession, seeded: dict):
        wl = seeded["watchlist"]
        item = seeded["item"]
        alert = WatchlistAlert(
            watchlist_item_id=item.id, alert_type="portfolio.holding_count",
            operator="gte", threshold_value=100, is_active=True,
        )
        session.add(alert)
        await session.flush()
        assert await evaluator._evaluate_alert(alert) is False


class TestInactiveAlerts:
    @pytest.mark.asyncio
    async def test_inactive_alert_not_triggered(self, evaluator, session: AsyncSession, seeded: dict):
        item = seeded["item"]
        alert = WatchlistAlert(
            watchlist_item_id=item.id, alert_type="price.above",
            operator="gt", threshold_value=110.0, is_active=False,
        )
        session.add(alert)
        await session.flush()
        assert await evaluator.evaluate_watchlist_alerts(seeded["watchlist"].id) == []

    @pytest.mark.asyncio
    async def test_evaluate_all_active_only(self, evaluator, session: AsyncSession, seeded: dict):
        item = seeded["item"]
        a1 = WatchlistAlert(
            watchlist_item_id=item.id, alert_type="price.above",
            operator="gt", threshold_value=110.0, is_active=True,
        )
        a2 = WatchlistAlert(
            watchlist_item_id=item.id, alert_type="price.above",
            operator="gt", threshold_value=110.0, is_active=False,
        )
        session.add_all([a1, a2])
        await session.flush()
        count = await evaluator.evaluate_all_active_alerts()
        assert count == 1


class TestNotificationCreation:
    @pytest.mark.asyncio
    async def test_alert_creates_notification(self, evaluator, session: AsyncSession, seeded: dict):
        item = seeded["item"]
        alert = WatchlistAlert(
            watchlist_item_id=item.id, alert_type="price.above",
            operator="gt", threshold_value=110.0, is_active=True,
        )
        session.add(alert)
        await session.flush()
        await evaluator._evaluate_alert(alert)
        notifs = await session.execute(select(Notification))
        assert len(notifs.scalars().all()) >= 1

    @pytest.mark.asyncio
    async def test_alert_updates_last_triggered(self, evaluator, session: AsyncSession, seeded: dict):
        item = seeded["item"]
        alert = WatchlistAlert(
            watchlist_item_id=item.id, alert_type="price.above",
            operator="gt", threshold_value=110.0, is_active=True,
        )
        session.add(alert)
        await session.flush()
        assert alert.last_triggered_at is None
        await evaluator._evaluate_alert(alert)
        assert alert.last_triggered_at is not None
