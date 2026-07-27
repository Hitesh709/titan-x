from datetime import date, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from titan_x.db.base import Base
from titan_x.models.adaptive_stop_loss import AdaptiveStopLoss
from titan_x.models.chart_pattern import SupportResistance
from titan_x.models.microstructure import MarketMicrostructure
from titan_x.models.price import DailyPrice
from titan_x.models.regime import MarketRegime
from titan_x.services.adaptive_stop_loss_service import AdaptiveStopLossService

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
    return AdaptiveStopLossService(session)


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
async def seed_support(session):
    sr = SupportResistance(
        symbol="TEST",
        level_type="support",
        price_level=130.0,
        strength_score=75.0,
        touch_count=5,
        first_detected=date.today() - timedelta(days=30),
        last_tested=date.today() - timedelta(days=2),
        is_active=True,
    )
    session.add(sr)
    sr2 = SupportResistance(
        symbol="TEST",
        level_type="support",
        price_level=120.0,
        strength_score=60.0,
        touch_count=3,
        first_detected=date.today() - timedelta(days=20),
        last_tested=date.today() - timedelta(days=5),
        is_active=True,
    )
    session.add(sr2)
    await session.flush()


@pytest_asyncio.fixture
async def seed_regime(session):
    regime = MarketRegime(
        symbol="TEST",
        as_of_date=date.today(),
        trend_regime="bull",
        volatility_regime="normal_volatility",
        trend_score=70.0,
        volatility_score=50.0,
        confidence=0.8,
    )
    session.add(regime)
    await session.flush()


@pytest_asyncio.fixture
async def seed_liquidity(session):
    liq = MarketMicrostructure(
        symbol="TEST",
        as_of_date=date.today(),
        volume=1_500_000,
        avg_volume_5d=1_200_000,
        avg_volume_20d=1_000_000,
        volume_ratio=1.5,
        liquidity_score=75.0,
        liquidity_rating="high",
        avg_spread_pct=0.5,
    )
    session.add(liq)
    await session.flush()


class TestCompute:
    async def test_compute_basic(self, service, seed_prices):
        result = await service.compute("TEST")
        assert result.symbol == "TEST"
        assert result.composite_stop_price is not None
        assert result.composite_stop_pct is not None
        assert result.atr_value is not None
        assert result.sl_price_atr is not None

    async def test_compute_with_entry_price(self, service, seed_prices):
        result = await service.compute("TEST", entry_price=150.0)
        assert result.entry_price == 150.0
        assert result.composite_stop_price is not None

    async def test_compute_custom_multipliers(self, service, seed_prices):
        result = await service.compute("TEST", atr_multiplier=3.0, vol_multiplier=2.0)
        assert result.atr_multiplier == 3.0
        assert result.vol_multiplier == 2.0

    async def test_compute_no_data(self, service):
        result = await service.compute("NODATA")
        assert result.symbol == "NODATA"
        assert result.composite_stop_price is None

    async def test_compute_with_support(self, service, seed_prices, seed_support):
        result = await service.compute("TEST")
        assert result.nearest_support is not None
        assert result.sl_price_support is not None

    async def test_compute_with_regime(self, service, seed_prices, seed_regime):
        result = await service.compute("TEST")
        assert result.trend_regime == "bull"
        assert result.volatility_regime == "normal_volatility"
        assert result.regime_adjustment is not None

    async def test_compute_with_liquidity(self, service, seed_prices, seed_liquidity):
        result = await service.compute("TEST")
        assert result.liquidity_score is not None
        assert result.liquidity_rating == "high"
        assert result.liq_adjustment is not None

    async def test_compute_all_factors(
        self, service, seed_prices, seed_support, seed_regime, seed_liquidity,
    ):
        result = await service.compute("TEST")
        assert result.composite_stop_price is not None
        assert result.composite_stop_pct is not None
        assert result.sl_price_atr is not None
        assert result.sl_price_support is not None
        assert result.regime_adjustment is not None
        assert result.liq_adjustment is not None
        assert result.method == "composite"

    async def test_compute_stop_pct_in_range(self, service, seed_prices):
        result = await service.compute("TEST")
        assert 0.5 <= result.composite_stop_pct <= 15.0

    async def test_compute_trailing_default(self, service, seed_prices):
        result = await service.compute("TEST")
        assert result.is_trailing is True
        assert result.trailing_activation_pct == 5.0

    async def test_compute_trailing_disabled(self, service, seed_prices):
        result = await service.compute("TEST", trailing_activation_pct=None)
        assert result.is_trailing is False


class TestQuery:
    async def test_get_level(self, service, seed_prices):
        sl = await service.compute("TEST")
        found = await service.get_level(sl.id)
        assert found is not None
        assert found.id == sl.id

    async def test_get_level_not_found(self, service):
        found = await service.get_level(9999)
        assert found is None

    async def test_get_levels(self, service, seed_prices):
        await service.compute("TEST")
        await service.compute("TEST", atr_multiplier=3.0)
        levels = await service.get_levels("TEST")
        assert len(levels) > 0

    async def test_get_active(self, service, seed_prices):
        sl = await service.compute("TEST")
        active = await service.get_active("TEST")
        assert active is not None
        assert active.id == sl.id

    async def test_deactivate(self, service, seed_prices):
        sl = await service.compute("TEST")
        deactivated = await service.deactivate(sl.id)
        assert deactivated is not None
        assert deactivated.is_active is False

    async def test_deactivate_not_found(self, service):
        result = await service.deactivate(9999)
        assert result is None
