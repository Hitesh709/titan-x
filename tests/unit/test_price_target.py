from datetime import date, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from titan_x.db.base import Base
from titan_x.models.chart_pattern import SupportResistance
from titan_x.models.price import DailyPrice
from titan_x.models.price_target import PriceTarget
from titan_x.services.price_target_service import PriceTargetService

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
    return PriceTargetService(session)


@pytest_asyncio.fixture
async def seed_prices(session):
    today = date.today()
    sym = "TEST"
    for i in range(100):
        dp = DailyPrice(
            symbol=sym,
            trade_date=today - timedelta(days=(99 - i)),
            open=100.0 + i * 0.5,
            high=101.0 + i * 0.5,
            low=99.0 + i * 0.5,
            close=100.0 + i * 0.5,
            volume=1_000_000,
        )
        session.add(dp)
    await session.flush()


@pytest_asyncio.fixture
async def seed_resistance(session):
    r1 = SupportResistance(
        symbol="TEST",
        level_type="resistance",
        price_level=155.0,
        strength_score=80.0,
        touch_count=6,
        first_detected=date.today() - timedelta(days=30),
        last_tested=date.today() - timedelta(days=1),
        is_active=True,
    )
    session.add(r1)
    r2 = SupportResistance(
        symbol="TEST",
        level_type="resistance",
        price_level=170.0,
        strength_score=55.0,
        touch_count=3,
        first_detected=date.today() - timedelta(days=20),
        last_tested=date.today() - timedelta(days=5),
        is_active=True,
    )
    session.add(r2)
    await session.flush()


class TestGenerate:
    async def test_generate_basic(self, service, seed_prices):
        result = await service.generate("TEST")
        assert result.symbol == "TEST"
        assert result.direction == "bullish"
        assert result.target_1_price is not None
        assert result.target_2_price is not None
        assert result.target_3_price is not None

    async def test_generate_with_entry_price(self, service, seed_prices):
        result = await service.generate("TEST", entry_price=150.0)
        assert result.entry_price == 150.0

    async def test_generate_bearish(self, service, seed_prices):
        result = await service.generate("TEST", direction="bearish")
        assert result.direction == "bearish"
        assert result.target_1_price is not None
        target_pct = result.target_1_pct
        assert target_pct is not None and target_pct > 0
        assert result.target_1_price < result.entry_price

    async def test_generate_no_data(self, service):
        result = await service.generate("NODATA")
        assert result.symbol == "NODATA"
        assert result.target_1_price is None

    async def test_generates_three_targets(self, service, seed_prices):
        result = await service.generate("TEST")
        assert result.target_1_price is not None
        assert result.target_2_price is not None
        assert result.target_3_price is not None
        assert result.target_1_price < result.target_2_price < result.target_3_price

    async def test_probabilities_decreasing(self, service, seed_prices):
        result = await service.generate("TEST")
        assert result.target_1_probability is not None
        assert result.target_2_probability is not None
        assert result.target_3_probability is not None
        assert result.target_1_probability > result.target_2_probability > result.target_3_probability

    async def test_pct_increasing(self, service, seed_prices):
        result = await service.generate("TEST")
        assert result.target_1_pct is not None
        assert result.target_2_pct is not None
        assert result.target_3_pct is not None
        assert result.target_1_pct < result.target_2_pct < result.target_3_pct

    async def test_expected_holding_days(self, service, seed_prices):
        result = await service.generate("TEST")
        assert result.expected_holding_days is not None
        assert 1 <= result.expected_holding_days <= 365

    async def test_generate_with_resistance(self, service, seed_prices, seed_resistance):
        result = await service.generate("TEST")
        assert result.nearest_resistance is not None
        assert result.resistance_strength is not None

    async def test_generate_atr_value(self, service, seed_prices):
        result = await service.generate("TEST")
        assert result.atr_value is not None

    async def test_pct_in_range(self, service, seed_prices):
        result = await service.generate("TEST")
        for pct in (result.target_1_pct, result.target_2_pct, result.target_3_pct):
            assert pct is not None
            assert 0.5 <= pct <= 50.0

    async def test_targets_within_reasonable_range(self, service, seed_prices):
        result = await service.generate("TEST")
        entry = result.entry_price
        assert result.target_3_price < entry * 2.0
        assert result.target_3_price > entry


class TestQuery:
    async def test_get_target(self, service, seed_prices):
        pt = await service.generate("TEST")
        found = await service.get_target(pt.id)
        assert found is not None
        assert found.id == pt.id

    async def test_get_target_not_found(self, service):
        found = await service.get_target(9999)
        assert found is None

    async def test_get_targets(self, service, seed_prices):
        await service.generate("TEST")
        await service.generate("TEST", entry_price=160.0)
        targets = await service.get_targets("TEST")
        assert len(targets) > 0


class TestEdgeCases:
    async def test_bearish_targets_descending(self, service, seed_prices):
        result = await service.generate("TEST", direction="bearish")
        assert result.target_1_price is not None
        assert result.target_2_price is not None
        assert result.target_3_price is not None
        assert result.target_1_price > result.target_2_price > result.target_3_price

    async def test_bearish_holding_days(self, service, seed_prices):
        result = await service.generate("TEST", direction="bearish")
        assert result.expected_holding_days is not None
        assert result.expected_holding_days >= 1
