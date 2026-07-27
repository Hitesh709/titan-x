from datetime import date, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select, text as sqlite_raw_text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from titan_x.db.base import Base
from titan_x.models.company import Company
from titan_x.models.price import DailyPrice
from titan_x.models.watchlist import (
    WatchlistAiInsight,
    WatchlistItemTag,
)
from titan_x.services.watchlist_engine import WatchlistEngine


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as sess:
        await sess.execute(sqlite_raw_text("PRAGMA foreign_keys=ON"))
        yield sess
    await engine.dispose()


@pytest_asyncio.fixture
async def engine(session: AsyncSession) -> WatchlistEngine:
    return WatchlistEngine(session)


@pytest_asyncio.fixture
async def user_id(session: AsyncSession) -> int:
    from titan_x.models.user import User
    u = User(email="test@example.com", hashed_password="h", is_active=True)
    session.add(u)
    await session.flush()
    return u.id


@pytest_asyncio.fixture
async def wl_engine(engine: WatchlistEngine, user_id: int) -> tuple[WatchlistEngine, int]:
    return engine, user_id


class TestFolders:
    @pytest.mark.asyncio
    async def test_create_folder(self, wl_engine):
        engine, uid = wl_engine
        f = await engine.create_folder(uid, "My Folder", "desc", color="#ff0000")
        assert f["name"] == "My Folder"
        assert f["description"] == "desc"
        assert f["color"] == "#ff0000"
        assert f["user_id"] == uid
        assert f["id"] is not None

    @pytest.mark.asyncio
    async def test_list_folders(self, wl_engine):
        engine, uid = wl_engine
        await engine.create_folder(uid, "A")
        await engine.create_folder(uid, "B")
        folders = await engine.list_folders(uid)
        assert len(folders) == 2

    @pytest.mark.asyncio
    async def test_list_folders_other_user(self, wl_engine):
        engine, uid = wl_engine
        await engine.create_folder(uid, "A")
        folders = await engine.list_folders(999)
        assert len(folders) == 0

    @pytest.mark.asyncio
    async def test_get_folder(self, wl_engine):
        engine, uid = wl_engine
        f = await engine.create_folder(uid, "Test")
        got = await engine.get_folder(f["id"], uid)
        assert got is not None
        assert got["name"] == "Test"

    @pytest.mark.asyncio
    async def test_get_folder_wrong_user(self, wl_engine):
        engine, uid = wl_engine
        f = await engine.create_folder(uid, "Test")
        got = await engine.get_folder(f["id"], 999)
        assert got is None

    @pytest.mark.asyncio
    async def test_update_folder(self, wl_engine):
        engine, uid = wl_engine
        f = await engine.create_folder(uid, "Old")
        updated = await engine.update_folder(f["id"], uid, name="New", color="#00ff00")
        assert updated["name"] == "New"
        assert updated["color"] == "#00ff00"

    @pytest.mark.asyncio
    async def test_update_folder_wrong_user(self, wl_engine):
        engine, uid = wl_engine
        f = await engine.create_folder(uid, "Old")
        updated = await engine.update_folder(f["id"], 999, name="New")
        assert updated is None

    @pytest.mark.asyncio
    async def test_delete_folder(self, wl_engine):
        engine, uid = wl_engine
        f = await engine.create_folder(uid, "ToDelete")
        assert await engine.delete_folder(f["id"], uid) is True
        assert await engine.get_folder(f["id"], uid) is None

    @pytest.mark.asyncio
    async def test_delete_folder_wrong_user(self, wl_engine):
        engine, uid = wl_engine
        f = await engine.create_folder(uid, "ToDelete")
        assert await engine.delete_folder(f["id"], 999) is False


class TestWatchlists:
    @pytest.mark.asyncio
    async def test_create_watchlist(self, wl_engine):
        engine, uid = wl_engine
        wl = await engine.create_watchlist(uid, "My Watchlist")
        assert wl["name"] == "My Watchlist"
        assert wl["user_id"] == uid
        assert wl["is_default"] is False

    @pytest.mark.asyncio
    async def test_create_default_watchlist(self, wl_engine):
        engine, uid = wl_engine
        wl = await engine.create_watchlist(uid, "Default", is_default=True)
        assert wl["is_default"] is True

    @pytest.mark.asyncio
    async def test_create_watchlist_in_folder(self, wl_engine):
        engine, uid = wl_engine
        f = await engine.create_folder(uid, "Folder")
        wl = await engine.create_watchlist(uid, "In Folder", folder_id=f["id"])
        assert wl["folder_id"] == f["id"]

    @pytest.mark.asyncio
    async def test_list_watchlists(self, wl_engine):
        engine, uid = wl_engine
        await engine.create_watchlist(uid, "A")
        await engine.create_watchlist(uid, "B")
        rows, total = await engine.list_watchlists(uid)
        assert total == 2

    @pytest.mark.asyncio
    async def test_list_watchlists_in_folder(self, wl_engine):
        engine, uid = wl_engine
        f = await engine.create_folder(uid, "Folder")
        await engine.create_watchlist(uid, "A", folder_id=f["id"])
        await engine.create_watchlist(uid, "B")
        rows, total = await engine.list_watchlists(uid, folder_id=f["id"])
        assert total == 1

    @pytest.mark.asyncio
    async def test_get_watchlist(self, wl_engine):
        engine, uid = wl_engine
        wl = await engine.create_watchlist(uid, "Test")
        got = await engine.get_watchlist(wl["id"], uid)
        assert got is not None
        assert got.name == "Test"

    @pytest.mark.asyncio
    async def test_get_watchlist_wrong_user(self, wl_engine):
        engine, uid = wl_engine
        wl = await engine.create_watchlist(uid, "Test")
        got = await engine.get_watchlist(wl["id"], 999)
        assert got is None

    @pytest.mark.asyncio
    async def test_update_watchlist(self, wl_engine):
        engine, uid = wl_engine
        wl = await engine.create_watchlist(uid, "Old")
        updated = await engine.update_watchlist(wl["id"], uid, name="New")
        assert updated["name"] == "New"

    @pytest.mark.asyncio
    async def test_update_watchlist_wrong_user(self, wl_engine):
        engine, uid = wl_engine
        wl = await engine.create_watchlist(uid, "Old")
        updated = await engine.update_watchlist(wl["id"], 999, name="New")
        assert updated is None

    @pytest.mark.asyncio
    async def test_delete_watchlist(self, wl_engine):
        engine, uid = wl_engine
        wl = await engine.create_watchlist(uid, "ToDelete")
        assert await engine.delete_watchlist(wl["id"], uid) is True
        assert await engine.get_watchlist(wl["id"], uid) is None

    @pytest.mark.asyncio
    async def test_delete_watchlist_wrong_user(self, wl_engine):
        engine, uid = wl_engine
        wl = await engine.create_watchlist(uid, "ToDelete")
        assert await engine.delete_watchlist(wl["id"], 999) is False


class TestItems:
    @pytest.mark.asyncio
    async def test_add_item(self, wl_engine):
        engine, uid = wl_engine
        wl = await engine.create_watchlist(uid, "Test")
        item = await engine.add_item(wl["id"], uid, "AAPL", "my notes")
        assert item is not None
        assert item["symbol"] == "AAPL"
        assert item["notes"] == "my notes"
        assert item["watchlist_id"] == wl["id"]

    @pytest.mark.asyncio
    async def test_add_item_duplicate(self, wl_engine):
        engine, uid = wl_engine
        wl = await engine.create_watchlist(uid, "Test")
        await engine.add_item(wl["id"], uid, "AAPL")
        with pytest.raises(ValueError, match="already in watchlist"):
            await engine.add_item(wl["id"], uid, "AAPL")

    @pytest.mark.asyncio
    async def test_add_item_wrong_user(self, wl_engine):
        engine, uid = wl_engine
        wl = await engine.create_watchlist(uid, "Test")
        item = await engine.add_item(wl["id"], 999, "AAPL")
        assert item is None

    @pytest.mark.asyncio
    async def test_list_items(self, wl_engine):
        engine, uid = wl_engine
        wl = await engine.create_watchlist(uid, "Test")
        await engine.add_item(wl["id"], uid, "AAPL")
        await engine.add_item(wl["id"], uid, "GOOG")
        items = await engine.list_items(wl["id"], uid)
        assert items is not None
        assert len(items) == 2

    @pytest.mark.asyncio
    async def test_list_items_wrong_user(self, wl_engine):
        engine, uid = wl_engine
        wl = await engine.create_watchlist(uid, "Test")
        items = await engine.list_items(wl["id"], 999)
        assert items is None

    @pytest.mark.asyncio
    async def test_update_item(self, wl_engine):
        engine, uid = wl_engine
        wl = await engine.create_watchlist(uid, "Test")
        item = await engine.add_item(wl["id"], uid, "AAPL")
        updated = await engine.update_item(item["id"], wl["id"], uid, notes="updated notes")
        assert updated["notes"] == "updated notes"

    @pytest.mark.asyncio
    async def test_remove_item(self, wl_engine):
        engine, uid = wl_engine
        wl = await engine.create_watchlist(uid, "Test")
        item = await engine.add_item(wl["id"], uid, "AAPL")
        assert await engine.remove_item(item["id"], wl["id"], uid) is True
        items = await engine.list_items(wl["id"], uid)
        assert len(items) == 0

    @pytest.mark.asyncio
    async def test_reorder_items(self, wl_engine):
        engine, uid = wl_engine
        wl = await engine.create_watchlist(uid, "Test")
        i1 = await engine.add_item(wl["id"], uid, "AAPL")
        i2 = await engine.add_item(wl["id"], uid, "GOOG")
        assert await engine.reorder_items(wl["id"], uid, [i2["id"], i1["id"]]) is True


class TestTags:
    @pytest.mark.asyncio
    async def test_create_tag(self, wl_engine):
        engine, uid = wl_engine
        tag = await engine.create_tag(uid, "Tech", "#1e90ff")
        assert tag["name"] == "Tech"
        assert tag["color"] == "#1e90ff"

    @pytest.mark.asyncio
    async def test_list_tags(self, wl_engine):
        engine, uid = wl_engine
        await engine.create_tag(uid, "A")
        await engine.create_tag(uid, "B")
        tags = await engine.list_tags(uid)
        assert len(tags) == 2

    @pytest.mark.asyncio
    async def test_delete_tag(self, wl_engine):
        engine, uid = wl_engine
        tag = await engine.create_tag(uid, "ToDelete")
        assert await engine.delete_tag(tag["id"], uid) is True

    @pytest.mark.asyncio
    async def test_tag_item(self, wl_engine):
        engine, uid = wl_engine
        wl = await engine.create_watchlist(uid, "Test")
        item = await engine.add_item(wl["id"], uid, "AAPL")
        tag = await engine.create_tag(uid, "Tech")
        assert await engine.tag_item(item["id"], tag["id"], wl["id"], uid) is True

    @pytest.mark.asyncio
    async def test_untag_item(self, wl_engine):
        engine, uid = wl_engine
        wl = await engine.create_watchlist(uid, "Test")
        item = await engine.add_item(wl["id"], uid, "AAPL")
        tag = await engine.create_tag(uid, "Tech")
        await engine.tag_item(item["id"], tag["id"], wl["id"], uid)
        assert await engine.untag_item(item["id"], tag["id"], wl["id"], uid) is True


class TestAlerts:
    @pytest.mark.asyncio
    async def test_create_alert(self, wl_engine):
        engine, uid = wl_engine
        wl = await engine.create_watchlist(uid, "Test")
        item = await engine.add_item(wl["id"], uid, "AAPL")
        alert = await engine.create_alert(
            item["id"], wl["id"], uid, "price_above", "gt", 200.0,
        )
        assert alert is not None
        assert alert["alert_type"] == "price_above"
        assert alert["operator"] == "gt"
        assert alert["threshold_value"] == 200.0

    @pytest.mark.asyncio
    async def test_create_alert_wrong_user(self, wl_engine):
        engine, uid = wl_engine
        wl = await engine.create_watchlist(uid, "Test")
        item = await engine.add_item(wl["id"], uid, "AAPL")
        alert = await engine.create_alert(item["id"], wl["id"], 999, "price_above", "gt", 200.0)
        assert alert is None

    @pytest.mark.asyncio
    async def test_list_alerts(self, wl_engine):
        engine, uid = wl_engine
        wl = await engine.create_watchlist(uid, "Test")
        item = await engine.add_item(wl["id"], uid, "AAPL")
        await engine.create_alert(item["id"], wl["id"], uid, "price_above", "gt", 200.0)
        alerts = await engine.list_alerts(wl["id"], uid)
        assert alerts is not None
        assert len(alerts) == 1

    @pytest.mark.asyncio
    async def test_update_alert(self, wl_engine):
        engine, uid = wl_engine
        wl = await engine.create_watchlist(uid, "Test")
        item = await engine.add_item(wl["id"], uid, "AAPL")
        alert = await engine.create_alert(item["id"], wl["id"], uid, "price_above", "gt", 200.0)
        updated = await engine.update_alert(alert["id"], wl["id"], uid, threshold_value=250.0)
        assert updated["threshold_value"] == 250.0

    @pytest.mark.asyncio
    async def test_delete_alert(self, wl_engine):
        engine, uid = wl_engine
        wl = await engine.create_watchlist(uid, "Test")
        item = await engine.add_item(wl["id"], uid, "AAPL")
        alert = await engine.create_alert(item["id"], wl["id"], uid, "price_above", "gt", 200.0)
        assert await engine.delete_alert(alert["id"], wl["id"], uid) is True


class TestNotifications:
    @pytest.mark.asyncio
    async def test_create_notification(self, wl_engine):
        engine, uid = wl_engine
        n = await engine.create_notification(uid, "Test Alert", "Message body", "alert")
        assert n["title"] == "Test Alert"
        assert n["message"] == "Message body"
        assert n["is_read"] is False

    @pytest.mark.asyncio
    async def test_list_notifications(self, wl_engine):
        engine, uid = wl_engine
        await engine.create_notification(uid, "A", "Msg A")
        await engine.create_notification(uid, "B", "Msg B")
        rows, total = await engine.list_notifications(uid)
        assert total == 2

    @pytest.mark.asyncio
    async def test_mark_read(self, wl_engine):
        engine, uid = wl_engine
        n = await engine.create_notification(uid, "Test", "Body")
        assert await engine.mark_notification_read(n["id"], uid) is True
        rows, _ = await engine.list_notifications(uid, is_read=True)
        assert len(rows) == 1

    @pytest.mark.asyncio
    async def test_mark_all_read(self, wl_engine):
        engine, uid = wl_engine
        await engine.create_notification(uid, "A", "Body")
        await engine.create_notification(uid, "B", "Body")
        count = await engine.mark_all_notifications_read(uid)
        rows, _ = await engine.list_notifications(uid, is_read=True)
        assert len(rows) == 2

    @pytest.mark.asyncio
    async def test_delete_notification(self, wl_engine):
        engine, uid = wl_engine
        n = await engine.create_notification(uid, "Test", "Body")
        assert await engine.delete_notification(n["id"], uid) is True
        rows, total = await engine.list_notifications(uid)
        assert total == 0


class TestAiInsights:
    @pytest.mark.asyncio
    async def test_run_ai_analysis_no_data(self, wl_engine):
        engine, uid = wl_engine
        wl = await engine.create_watchlist(uid, "Test")
        insights = await engine.run_ai_analysis(wl["id"], uid)
        assert insights == []

    @pytest.mark.asyncio
    async def test_run_ai_analysis_with_prices(self, wl_engine, session: AsyncSession):
        engine, uid = wl_engine
        wl = await engine.create_watchlist(uid, "Test")
        await engine.add_item(wl["id"], uid, "AAPL")
        company = Company(symbol="AAPL", company_name="Apple Inc.", isin="US0378331005", sector="Technology", exchange="NASDAQ")
        session.add(company)
        today = date.today()
        for i in range(30):
            c = 150.0 + i * 0.5
            dp = DailyPrice(
                symbol="AAPL", open=c, high=c + 1.0, low=c - 1.0, close=c,
                volume=1000000 + i * 100,
                trade_date=today - timedelta(days=29 - i),
            )
            session.add(dp)
        await session.flush()
        insights = await engine.run_ai_analysis(wl["id"], uid)
        assert isinstance(insights, list)

    @pytest.mark.asyncio
    async def test_get_insights(self, wl_engine, session: AsyncSession):
        engine, uid = wl_engine
        wl = await engine.create_watchlist(uid, "Test")
        insight = WatchlistAiInsight(
            watchlist_id=wl["id"], insight_type="momentum_alert",
            content="Test insight", score=75.0,
        )
        session.add(insight)
        await session.flush()
        insights = await engine.get_insights(wl["id"], uid)
        assert insights is not None
        assert len(insights) == 1
        assert insights[0]["insight_type"] == "momentum_alert"

    @pytest.mark.asyncio
    async def test_delete_insight(self, wl_engine, session: AsyncSession):
        engine, uid = wl_engine
        wl = await engine.create_watchlist(uid, "Test")
        insight = WatchlistAiInsight(
            watchlist_id=wl["id"], insight_type="test",
            content="Test", score=50.0,
        )
        session.add(insight)
        await session.flush()
        assert await engine.delete_insight(insight.id, wl["id"], uid) is True


class TestCascadeAndOwnership:
    @pytest.mark.asyncio
    async def test_cascade_delete_folder(self, wl_engine):
        engine, uid = wl_engine
        f = await engine.create_folder(uid, "Folder")
        wl = await engine.create_watchlist(uid, "Test", folder_id=f["id"])
        await engine.delete_folder(f["id"], uid)
        got = await engine.get_watchlist(wl["id"], uid)
        assert got is not None
        assert got.folder_id is None

    @pytest.mark.asyncio
    async def test_cascade_delete_watchlist(self, wl_engine):
        engine, uid = wl_engine
        wl = await engine.create_watchlist(uid, "Test")
        await engine.add_item(wl["id"], uid, "AAPL")
        await engine.delete_watchlist(wl["id"], uid)
        items = await engine.list_items(wl["id"], uid)
        assert items is None

    @pytest.mark.asyncio
    async def test_ownership_isolation(self, wl_engine):
        engine, uid = wl_engine
        f = await engine.create_folder(uid, "Mine")
        wl = await engine.create_watchlist(uid, "Mine", folder_id=f["id"])
        other_uid = uid + 1
        assert await engine.get_folder(f["id"], other_uid) is None
        assert await engine.get_watchlist(wl["id"], other_uid) is None

    @pytest.mark.asyncio
    async def test_watchlist_with_items_cascade_tags(self, wl_engine, session: AsyncSession):
        engine, uid = wl_engine
        wl = await engine.create_watchlist(uid, "Test")
        item = await engine.add_item(wl["id"], uid, "AAPL")
        tag = await engine.create_tag(uid, "Tech")
        await engine.tag_item(item["id"], tag["id"], wl["id"], uid)
        assocs = await session.execute(select(WatchlistItemTag))
        assert len(assocs.scalars().all()) == 1
        await engine.delete_watchlist(wl["id"], uid)
        assocs = await session.execute(select(WatchlistItemTag))
        assert len(assocs.scalars().all()) == 0
