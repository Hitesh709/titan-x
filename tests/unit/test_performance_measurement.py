from datetime import date, datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from titan_x.db.base import Base
from titan_x.models.performance_snapshot import PerformanceSnapshot
from titan_x.models.trade_journal import TradeJournal
from titan_x.models.user import User
from titan_x.services.performance_measurement_service import PerformanceMeasurementService

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
    return PerformanceMeasurementService(session)


@pytest_asyncio.fixture
async def seed_user(session):
    u = User(email="test@test.com", hashed_password="x")
    session.add(u)
    await session.flush()
    return u


def _make_trade(session, user_id, symbol, direction, entry_dt, exit_dt,
                entry_price, exit_price, quantity, pnl_amount, pnl_pct,
                setup_type=None, mistake=None, emotion_before=None):
    t = TradeJournal(
        user_id=user_id, symbol=symbol, direction=direction,
        entry_date=entry_dt, exit_date=exit_dt,
        entry_price=entry_price, exit_price=exit_price,
        quantity=quantity, pnl_amount=pnl_amount, pnl_pct=pnl_pct,
        is_closed=True, setup_type=setup_type, mistake=mistake,
        emotion_before=emotion_before,
    )
    session.add(t)
    return t


class TestTakeSnapshot:
    async def test_no_trades(self, service, seed_user):
        snap = await service.take_snapshot(user_id=seed_user.id)
        assert snap.total_trades == 0
        assert snap.win_rate == 0.0
        assert snap.max_drawdown_pct is None

    async def test_single_winning_trade(self, service, seed_user, session):
        now = datetime.now(timezone.utc)
        _make_trade(session, seed_user.id, "AAPL", "long",
                    now - timedelta(days=3), now,
                    100.0, 110.0, 10, 100.0, 10.0)
        await session.flush()
        snap = await service.take_snapshot(user_id=seed_user.id)
        assert snap.total_trades == 1
        assert snap.winning_trades == 1
        assert snap.win_rate == 100.0
        assert snap.total_pnl == 100.0

    async def test_single_losing_trade(self, service, seed_user, session):
        now = datetime.now(timezone.utc)
        _make_trade(session, seed_user.id, "AAPL", "long",
                    now - timedelta(days=2), now,
                    100.0, 90.0, 10, -100.0, -10.0)
        await session.flush()
        snap = await service.take_snapshot(user_id=seed_user.id)
        assert snap.total_trades == 1
        assert snap.losing_trades == 1
        assert snap.win_rate == 0.0
        assert snap.total_pnl == -100.0

    async def test_mixed_trades(self, service, seed_user, session):
        now = datetime.now(timezone.utc)
        _make_trade(session, seed_user.id, "AAPL", "long",
                    now - timedelta(days=10), now - timedelta(days=8),
                    100.0, 110.0, 10, 100.0, 10.0)
        _make_trade(session, seed_user.id, "GOOG", "long",
                    now - timedelta(days=7), now - timedelta(days=5),
                    200.0, 180.0, 5, -100.0, -10.0)
        _make_trade(session, seed_user.id, "MSFT", "short",
                    now - timedelta(days=4), now - timedelta(days=2),
                    300.0, 280.0, 3, 60.0, 6.67)
        await session.flush()
        snap = await service.take_snapshot(user_id=seed_user.id)
        assert snap.total_trades == 3
        assert snap.winning_trades == 2
        assert snap.win_rate == pytest.approx(66.67, rel=0.1)
        assert snap.total_pnl == pytest.approx(60.0, rel=0.1)
        assert snap.avg_return == pytest.approx(20.0, rel=0.1)

    async def test_sharpe_non_empty(self, service, seed_user, session):
        now = datetime.now(timezone.utc)
        for i in range(5):
            _make_trade(session, seed_user.id, "AAPL", "long",
                        now - timedelta(days=10 - i), now - timedelta(days=9 - i),
                        100.0, 105.0, 10, 50.0, 5.0)
        await session.flush()
        snap = await service.take_snapshot(user_id=seed_user.id)
        assert snap.total_trades == 5
        assert snap.win_rate == 100.0

    async def test_symbol_filtered(self, service, seed_user, session):
        now = datetime.now(timezone.utc)
        _make_trade(session, seed_user.id, "AAPL", "long",
                    now - timedelta(days=3), now, 100.0, 110.0, 10, 100.0, 10.0)
        _make_trade(session, seed_user.id, "IBM", "long",
                    now - timedelta(days=2), now, 50.0, 45.0, 20, -100.0, -10.0)
        await session.flush()
        snap = await service.take_snapshot(user_id=seed_user.id, symbol="AAPL")
        assert snap.total_trades == 1
        assert snap.symbol == "AAPL"
        assert snap.total_pnl == 100.0

    async def test_accuracy_equals_win_rate(self, service, seed_user, session):
        now = datetime.now(timezone.utc)
        _make_trade(session, seed_user.id, "AAPL", "long",
                    now - timedelta(days=3), now, 100.0, 110.0, 10, 100.0, 10.0)
        await session.flush()
        snap = await service.take_snapshot(user_id=seed_user.id)
        assert snap.accuracy == snap.win_rate

    async def test_drawdown_mixed_trades(self, service, seed_user, session):
        now = datetime.now(timezone.utc)
        _make_trade(session, seed_user.id, "AAPL", "long",
                    now - timedelta(days=10), now - timedelta(days=9),
                    100.0, 110.0, 10, 100.0, 10.0)
        _make_trade(session, seed_user.id, "AAPL", "long",
                    now - timedelta(days=8), now - timedelta(days=7),
                    110.0, 90.0, 10, -200.0, -18.18)
        _make_trade(session, seed_user.id, "AAPL", "long",
                    now - timedelta(days=6), now - timedelta(days=5),
                    90.0, 100.0, 10, 100.0, 11.11)
        await session.flush()
        snap = await service.take_snapshot(user_id=seed_user.id, initial_capital=1000.0)
        assert snap.total_trades == 3
        assert snap.max_drawdown is not None
        assert snap.max_drawdown_pct is not None

    async def test_short_trades_pnl(self, service, seed_user, session):
        now = datetime.now(timezone.utc)
        _make_trade(session, seed_user.id, "TSLA", "short",
                    now - timedelta(days=3), now,
                    200.0, 180.0, 5, 100.0, 10.0)
        await session.flush()
        snap = await service.take_snapshot(user_id=seed_user.id)
        assert snap.total_pnl == 100.0
        assert snap.winning_trades == 1


class TestQuery:
    async def test_get_snapshot(self, service, seed_user, session):
        now = datetime.now(timezone.utc)
        _make_trade(session, seed_user.id, "AAPL", "long",
                    now - timedelta(days=1), now, 100.0, 110.0, 10, 100.0, 10.0)
        await session.flush()
        snap = await service.take_snapshot(user_id=seed_user.id)
        found = await service.get_snapshot(snap.id)
        assert found is not None
        assert found.id == snap.id

    async def test_get_snapshot_not_found(self, service):
        found = await service.get_snapshot(9999)
        assert found is None

    async def test_get_snapshots(self, service, seed_user, session):
        now = datetime.now(timezone.utc)
        _make_trade(session, seed_user.id, "AAPL", "long",
                    now - timedelta(days=1), now, 100.0, 110.0, 10, 100.0, 10.0)
        await session.flush()
        await service.take_snapshot(user_id=seed_user.id)
        await service.take_snapshot(user_id=seed_user.id, period_label="daily")
        snapshots = await service.get_snapshots(user_id=seed_user.id)
        assert len(snapshots) >= 2

    async def test_get_latest(self, service, seed_user, session):
        now = datetime.now(timezone.utc)
        _make_trade(session, seed_user.id, "AAPL", "long",
                    now - timedelta(days=1), now, 100.0, 110.0, 10, 100.0, 10.0)
        await session.flush()
        s1 = await service.take_snapshot(user_id=seed_user.id, period_label="daily")
        s2 = await service.take_snapshot(user_id=seed_user.id, period_label="weekly")
        latest = await service.get_latest(user_id=seed_user.id)
        assert latest is not None
        assert latest.id == s2.id or latest.id == s1.id

    async def test_get_latest_with_period(self, service, seed_user, session):
        now = datetime.now(timezone.utc)
        _make_trade(session, seed_user.id, "AAPL", "long",
                    now - timedelta(days=1), now, 100.0, 110.0, 10, 100.0, 10.0)
        await session.flush()
        await service.take_snapshot(user_id=seed_user.id, period_label="daily")
        latest = await service.get_latest(user_id=seed_user.id, period_label="daily")
        assert latest is not None
        assert latest.period_label == "daily"

    async def test_get_latest_no_snapshots(self, service, seed_user):
        latest = await service.get_latest(user_id=seed_user.id)
        assert latest is None

    async def test_get_trend(self, service, seed_user, session):
        now = datetime.now(timezone.utc)
        _make_trade(session, seed_user.id, "AAPL", "long",
                    now - timedelta(days=1), now, 100.0, 110.0, 10, 100.0, 10.0)
        await session.flush()
        await service.take_snapshot(user_id=seed_user.id, period_label="daily")
        await service.take_snapshot(user_id=seed_user.id, period_label="daily",
                                    snapshot_date=date.today())
        trend = await service.get_trend(user_id=seed_user.id)
        assert len(trend) >= 2
        assert all("win_rate" in t for t in trend)

    async def test_get_trend_empty(self, service, seed_user):
        trend = await service.get_trend(user_id=seed_user.id)
        assert trend == []
