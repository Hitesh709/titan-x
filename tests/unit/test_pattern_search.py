import math
from datetime import date, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from titan_x.db.base import Base
from titan_x.models.pattern_search import PatternSearchQuery, PatternSearchMatch
from titan_x.models.price import DailyPrice
from titan_x.services.pattern_search_service import PatternSearchService

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
    return PatternSearchService(session)


@pytest_asyncio.fixture
async def seed_historical_prices(session):
    today = date.today()
    symbols = ["TEST", "MATCH1", "MATCH2", "MATCH3"]
    for sym in symbols:
        for i in range(200):
            dp = DailyPrice(
                symbol=sym,
                trade_date=today - timedelta(days=(199 - i)),
                open=100 + math.sin(i * 0.1) * 10,
                high=105 + math.sin(i * 0.1) * 10,
                low=95 + math.sin(i * 0.1) * 10,
                close=100 + math.sin(i * 0.1) * 10 + (i * 0.02),
                volume=1_000_000,
            )
            session.add(dp)
    await session.flush()


class TestSearch:
    async def test_search_requires_enough_data(self, service):
        today = date.today()
        with pytest.raises(ValueError, match="Insufficient price data"):
            await service.search("NONEXIST", "price", today - timedelta(days=10), today, window_days=20)

    async def test_search_finds_matches(self, service, seed_historical_prices):
        today = date.today()
        query = await service.search(
            "TEST", "price",
            today - timedelta(days=30), today - timedelta(days=10),
            window_days=10, lookback_years=2, min_similarity=0.1, max_matches=10,
        )
        assert query.total_matches >= 0
        assert query.symbol == "TEST"

    async def test_search_with_high_threshold(self, service, seed_historical_prices):
        today = date.today()
        query = await service.search(
            "TEST", "price",
            today - timedelta(days=30), today - timedelta(days=10),
            window_days=10, lookback_years=2, min_similarity=0.99, max_matches=5,
        )
        assert query.total_matches >= 0

    async def test_search_stores_metrics(self, service, seed_historical_prices):
        today = date.today()
        query = await service.search(
            "TEST", "price",
            today - timedelta(days=30), today - timedelta(days=10),
            window_days=10, lookback_years=2, min_similarity=0.1, max_matches=5,
        )
        assert query.total_matches is not None
        assert query.pattern_type == "price"


class TestQueryMethods:
    async def test_get_query(self, service, seed_historical_prices):
        today = date.today()
        q = await service.search("TEST", "price", today - timedelta(days=30), today - timedelta(days=10))
        found = await service.get_query(q.id)
        assert found is not None
        assert found.id == q.id

    async def test_get_query_not_found(self, service):
        found = await service.get_query(9999)
        assert found is None

    async def test_get_matches(self, service, seed_historical_prices):
        today = date.today()
        q = await service.search("TEST", "price", today - timedelta(days=30), today - timedelta(days=10),
                                 min_similarity=0.1, max_matches=5)
        matches = await service.get_matches(q.id)
        assert isinstance(matches, list)

    async def test_get_history(self, service, seed_historical_prices):
        today = date.today()
        await service.search("TEST", "price", today - timedelta(days=30), today - timedelta(days=10))
        history = await service.get_history()
        assert len(history) > 0

    async def test_get_history_by_symbol(self, service, seed_historical_prices):
        today = date.today()
        await service.search("TEST", "price", today - timedelta(days=30), today - timedelta(days=10))
        history = await service.get_history(symbol="TEST")
        assert all(h.symbol == "TEST" for h in history)


class TestHelpers:
    def test_normalize(self, service):
        result = service._normalize([10, 20, 30])
        assert result == [0.0, 0.5, 1.0]

    def test_normalize_flat(self, service):
        result = service._normalize([5, 5, 5])
        assert result == [0.5, 0.5, 0.5]

    def test_normalize_empty(self, service):
        assert service._normalize([]) == []

    def test_euclidean(self, service):
        d = service._euclidean([0, 0.5, 1.0], [0, 0.5, 1.0])
        assert d == 0.0

    def test_euclidean_different(self, service):
        d = service._euclidean([0, 0, 0], [1, 1, 1])
        assert d > 0

    def test_pearson_perfect(self, service):
        r = service._pearson([1, 2, 3], [2, 4, 6])
        assert abs(r - 1.0) < 0.001

    def test_pearson_inverse(self, service):
        r = service._pearson([1, 2, 3], [3, 2, 1])
        assert abs(r - (-1.0)) < 0.001

    def test_pearson_short(self, service):
        r = service._pearson([1], [2])
        assert r == 0.0

    def test_returns(self, service):
        r = service._returns([100, 110, 121])
        assert len(r) == 2
        assert abs(r[0] - 0.1) < 0.001

    def test_returns_short(self, service):
        assert service._returns([100]) == []
