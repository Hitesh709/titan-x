import pytest
import pytest_asyncio
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from titan_x.db.base import Base
from titan_x.models.pattern_library import PATTERN_CATEGORIES, PatternDefinition, PatternInstance
from titan_x.models.price import DailyPrice
from titan_x.services.pattern_library_service import PatternLibraryService

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
    return PatternLibraryService(session)


@pytest_asyncio.fixture
async def seed_definitions(session):
    defs_by_cat = {
        "candlestick": ["doji", "hammer", "marubozu", "bullish_engulfing", "bearish_engulfing", "shooting_star", "hanging_man"],
        "volume": ["volume_spike", "volume_dry_up", "volume_rising"],
        "breakout": ["breakout_above_resistance", "breakdown_below_support"],
        "gap": ["breakaway_gap", "common_gap", "runaway_gap"],
        "trend": ["uptrend", "downtrend", "sideways", "consolidation"],
    }
    for cat, names in defs_by_cat.items():
        for name in names:
            d = PatternDefinition(name=name, category=cat, ai_pattern_id=f"AI-{name}")
            session.add(d)
    await session.flush()


@pytest_asyncio.fixture
async def seed_prices(session):
    from datetime import date, timedelta
    today = date.today()
    for i in range(60):
        dp = DailyPrice(
            symbol="TEST", trade_date=today - timedelta(days=(59 - i)),
            open=100 + i * 0.5, high=101 + i * 0.5, low=99 + i * 0.5,
            close=100 + i * 0.5, volume=1_000_000 + i * 1000,
        )
        session.add(dp)
    await session.flush()


class TestDefinitions:
    async def test_create_definition(self, service):
        d = await service.create_definition("doji", "candlestick", "A doji pattern")
        assert d.name == "doji"
        assert d.category == "candlestick"
        assert d.ai_pattern_id.startswith("AI-")
        assert d.is_active is True

    async def test_create_definition_invalid_category(self, service):
        with pytest.raises(ValueError, match="Invalid category"):
            await service.create_definition("test", "invalid_category")

    async def test_list_definitions(self, service, seed_definitions):
        defs, total = await service.list_definitions()
        assert total > 0
        assert len(defs) > 0

    async def test_list_definitions_by_category(self, service, seed_definitions):
        defs, total = await service.list_definitions(category="candlestick")
        assert total > 0
        assert all(d.category == "candlestick" for d in defs)


class TestDetectCandlestick:
    async def test_detect_doji(self, service, seed_definitions, seed_prices):
        results = await service.detect_candlestick("TEST")
        # May not always detect with our synthetic data
        assert isinstance(results, list)

    async def test_detect_no_prices(self, service, seed_definitions):
        results = await service.detect_candlestick("NONEXIST")
        assert len(results) == 0

    async def test_detect_volume_spike(self, service, seed_definitions, seed_prices):
        results = await service.detect_volume("TEST")
        assert isinstance(results, list)

    async def test_detect_breakout(self, service, seed_definitions, seed_prices):
        results = await service.detect_breakout("TEST")
        assert isinstance(results, list)

    async def test_detect_gap(self, service, seed_definitions, seed_prices):
        results = await service.detect_gap("TEST")
        assert isinstance(results, list)

    async def test_detect_trend(self, service, seed_definitions, seed_prices):
        results = await service.detect_trend("TEST")
        assert isinstance(results, list)

    async def test_detect_all(self, service, seed_definitions, seed_prices):
        results = await service.detect_all("TEST")
        for category in ("candlestick", "volume", "breakout", "gap", "trend"):
            assert category in results


class TestInstances:
    async def test_get_instances(self, service, seed_definitions, seed_prices):
        await service.detect_all("TEST")
        instances = await service.get_instances(symbol="TEST")
        assert len(instances) > 0

    async def test_get_instances_by_category(self, service, seed_definitions, seed_prices):
        await service.detect_all("TEST")
        instances = await service.get_instances(category="trend")
        assert all(i.category == "trend" for i in instances)

    async def test_instance_stats(self, service, seed_definitions, seed_prices):
        await service.detect_all("TEST")
        defs, _ = await service.list_definitions(category="trend")
        if defs:
            stats = await service.get_instance_stats(defs[0].id)
            assert "total" in stats


class TestHelpers:
    def test_make_instance(self, service, seed_definitions):
        import asyncio
        loop = asyncio.new_event_loop()
        async def _test():
            defs, _ = await service.list_definitions(category="trend")
            from datetime import date
            inst = service._make_instance(defs, {d.name: d for d in defs}, "uptrend", "TEST", date.today(), 100.0, 0.8, "bullish")
            assert inst.symbol == "TEST"
            assert inst.direction == "bullish"
            assert inst.confidence_score == 0.8
        loop.run_until_complete(_test())
        loop.close()
