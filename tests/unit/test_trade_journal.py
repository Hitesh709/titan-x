from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from titan_x.db.base import Base
from titan_x.models.trade_journal import TradeJournal
from titan_x.models.user import User
from titan_x.services.trade_journal_service import TradeJournalService

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
async def session(engine):
    async with AsyncSession(engine, expire_on_commit=False) as s:
        yield s


@pytest_asyncio.fixture
async def service(session):
    return TradeJournalService(session)


@pytest_asyncio.fixture
async def user(session):
    u = User(
        email="trader@test.com",
        hashed_password="hash",
        is_superuser=False,
    )
    session.add(u)
    await session.flush()
    return u


@pytest.fixture
def now():
    return datetime(2025, 6, 15, 10, 30, 0)


class TestCreateEntry:
    async def test_create_basic(self, service, user, now):
        entry = await service.create_entry(
            user_id=user.id, symbol="AAPL", direction="long",
            entry_date=now, entry_price=150.0, quantity=100,
            reason="Bullish breakout on high volume",
            emotion_before="Confident",
            setup_type="Breakout",
            tags="earnings,tech",
        )
        assert entry.id is not None
        assert entry.symbol == "AAPL"
        assert entry.direction == "long"
        assert entry.entry_price == 150.0
        assert entry.quantity == 100
        assert entry.reason == "Bullish breakout on high volume"
        assert entry.emotion_before == "Confident"
        assert entry.setup_type == "Breakout"
        assert entry.tags == "earnings,tech"
        assert entry.is_closed is False

    async def test_create_short(self, service, user, now):
        entry = await service.create_entry(
            user_id=user.id, symbol="TSLA", direction="short",
            entry_date=now, entry_price=200.0, quantity=50,
        )
        assert entry.direction == "short"


class TestCloseEntry:
    async def test_close_long_profit(self, service, user, now):
        entry = await service.create_entry(
            user_id=user.id, symbol="AAPL", direction="long",
            entry_date=now - timedelta(days=5), entry_price=100.0, quantity=10,
        )
        closed = await service.close_entry(
            journal_id=entry.id,
            exit_date=now,
            exit_price=120.0,
            exit_reason="Target reached",
            exit_analysis="Hit first target, momentum fading",
            emotion_during="Patient",
            emotion_after="Satisfied",
            lessons_learned="Let winners run with trailing stop",
            rating=4,
        )
        assert closed is not None
        assert closed.is_closed is True
        assert closed.exit_price == 120.0
        assert closed.exit_reason == "Target reached"
        assert closed.emotion_during == "Patient"
        assert closed.pnl_amount == 200.0
        assert closed.pnl_pct == 20.0
        assert closed.rating == 4

    async def test_close_long_loss(self, service, user, now):
        entry = await service.create_entry(
            user_id=user.id, symbol="AAPL", direction="long",
            entry_date=now - timedelta(days=2), entry_price=100.0, quantity=10,
        )
        closed = await service.close_entry(
            journal_id=entry.id,
            exit_date=now,
            exit_price=90.0,
            exit_reason="Stop loss hit",
            mistake="Entered before confirmation",
        )
        assert closed is not None
        assert closed.pnl_amount == -100.0
        assert closed.pnl_pct == -10.0
        assert closed.mistake == "Entered before confirmation"

    async def test_close_short_profit(self, service, user, now):
        entry = await service.create_entry(
            user_id=user.id, symbol="TSLA", direction="short",
            entry_date=now - timedelta(days=3), entry_price=200.0, quantity=20,
        )
        closed = await service.close_entry(
            journal_id=entry.id,
            exit_date=now,
            exit_price=180.0,
            exit_reason="Trend reversal confirmed",
        )
        assert closed.pnl_amount == 400.0
        assert closed.pnl_pct == 10.0

    async def test_close_not_found(self, service, user, now):
        result = await service.close_entry(journal_id=9999, exit_date=now, exit_price=100.0)
        assert result is None


class TestUpdateEntry:
    async def test_update_reason(self, service, user, now):
        entry = await service.create_entry(
            user_id=user.id, symbol="AAPL", direction="long",
            entry_date=now, entry_price=150.0, quantity=100,
        )
        updated = await service.update_entry(entry.id, reason="Updated thesis")
        assert updated is not None
        assert updated.reason == "Updated thesis"

    async def test_update_not_found(self, service):
        result = await service.update_entry(9999, reason="Nope")
        assert result is None


class TestGetEntries:
    async def test_get_entries(self, service, user, now):
        await service.create_entry(user.id, "AAPL", "long", now, 150.0, 100)
        await service.create_entry(user.id, "TSLA", "short", now, 200.0, 50)
        entries = await service.get_entries(user.id)
        assert len(entries) == 2

    async def test_get_entries_filter_symbol(self, service, user, now):
        await service.create_entry(user.id, "AAPL", "long", now, 150.0, 100)
        await service.create_entry(user.id, "TSLA", "short", now, 200.0, 50)
        entries = await service.get_entries(user.id, symbol="AAPL")
        assert len(entries) == 1
        assert entries[0].symbol == "AAPL"

    async def test_get_entries_filter_closed(self, service, user, now):
        e1 = await service.create_entry(user.id, "AAPL", "long", now, 150.0, 100)
        await service.create_entry(user.id, "TSLA", "short", now, 200.0, 50)
        await service.close_entry(e1.id, now, 160.0)
        entries = await service.get_entries(user.id, is_closed=True)
        assert len(entries) == 1

    async def test_get_entry_by_id(self, service, user, now):
        e = await service.create_entry(user.id, "AAPL", "long", now, 150.0, 100)
        found = await service.get_entry(e.id)
        assert found is not None
        assert found.id == e.id

    async def test_get_entry_not_found(self, service):
        assert await service.get_entry(9999) is None


class TestPerformance:
    async def test_performance_empty(self, service, user):
        perf = await service.get_performance(user.id)
        assert perf["total_trades"] == 0
        assert perf["win_rate"] == 0

    async def test_performance_mixed(self, service, user, now):
        for i in range(3):
            e = await service.create_entry(user.id, "AAPL", "long", now, 100.0, 10,
                                           setup_type="Breakout" if i == 0 else "Pullback")
            await service.close_entry(e.id, now + timedelta(days=1), 110.0,
                                       lessons_learned="Good setup" if i == 0 else None,
                                       mistake="None" if i == 0 else "FOMO")
        for i in range(2):
            e = await service.create_entry(user.id, "TSLA", "long", now, 100.0, 10)
            await service.close_entry(e.id, now + timedelta(days=1), 95.0,
                                       mistake="FOMO")

        perf = await service.get_performance(user.id)
        assert perf["total_trades"] == 5
        assert perf["wins"] == 3
        assert perf["losses"] == 2
        assert perf["win_rate"] == 60.0
        assert perf["total_pnl"] == 200.0
        assert perf["profit_factor"] > 0
        assert perf["best_setup"] is not None
        assert perf["most_common_mistake"] == "FOMO"

    async def test_performance_filter_symbol(self, service, user, now):
        e1 = await service.create_entry(user.id, "AAPL", "long", now, 100.0, 10)
        await service.close_entry(e1.id, now + timedelta(days=1), 110.0)
        e2 = await service.create_entry(user.id, "TSLA", "long", now, 100.0, 10)
        await service.close_entry(e2.id, now + timedelta(days=1), 90.0)

        perf = await service.get_performance(user.id, symbol="AAPL")
        assert perf["total_trades"] == 1
        assert perf["total_pnl"] == 100.0

    async def test_performance_filter_days(self, service, user, now):
        recent = datetime.now() - timedelta(hours=1)
        e = await service.create_entry(user.id, "AAPL", "long", recent, 100.0, 10)
        await service.close_entry(e.id, recent + timedelta(minutes=30), 110.0)

        perf = await service.get_performance(user.id, days=1)
        assert perf["total_trades"] >= 1
