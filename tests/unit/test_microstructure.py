import json
from datetime import date, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from titan_x.db.base import Base
from titan_x.models.company import Company
from titan_x.models.microstructure import MarketMicrostructure
from titan_x.models.price import DailyPrice
from titan_x.services.microstructure_service import MicrostructureService


def _gen_prices(symbol: str, count: int, start_price: float = 100, base_vol: int = 100000) -> list[DailyPrice]:
    prices = []
    base_date = date(2024, 1, 1)
    price = start_price
    for i in range(count):
        d = base_date + timedelta(days=i)
        drift = 0.002
        noise = ((i % 7) - 3) * 0.3
        price = price * (1 + drift + noise * 0.01)
        vol = base_vol + (i % 10) * 5000
        prices.append(DailyPrice(
            symbol=symbol, trade_date=d,
            open=round(price * 0.99, 2), high=round(price * 1.025, 2),
            low=round(price * 0.975, 2), close=round(price, 2), volume=vol,
        ))
    return prices


def _gen_prices_high_volume(symbol: str, count: int, start_price: float = 100) -> list[DailyPrice]:
    prices = []
    base_date = date(2024, 1, 1)
    price = start_price
    for i in range(count):
        d = base_date + timedelta(days=i)
        price = price * (1 + 0.001)
        vol = 500000 + (i % 5) * 100000
        prices.append(DailyPrice(
            symbol=symbol, trade_date=d,
            open=round(price * 0.995, 2), high=round(price * 1.01, 2),
            low=round(price * 0.99, 2), close=round(price, 2), volume=vol,
        ))
    return prices


def _gen_prices_wide_spread(symbol: str, count: int, start_price: float = 100) -> list[DailyPrice]:
    prices = []
    base_date = date(2024, 1, 1)
    price = start_price
    for i in range(count):
        d = base_date + timedelta(days=i)
        price = price * (1 + 0.001)
        vol = 100000
        prices.append(DailyPrice(
            symbol=symbol, trade_date=d,
            open=round(price * 0.95, 2), high=round(price * 1.08, 2),
            low=round(price * 0.92, 2), close=round(price, 2), volume=vol,
        ))
    return prices


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///")

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_fks(dbapi_con, _rec):
        cursor = dbapi_con.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as sess:
        yield sess
    await engine.dispose()


@pytest_asyncio.fixture
def svc(session: AsyncSession) -> MicrostructureService:
    return MicrostructureService(session)


# ============================================================
# FULL ANALYSIS
# ============================================================

class TestFullAnalysis:
    @pytest.mark.asyncio
    async def test_analyze_basic(self, svc: MicrostructureService, session: AsyncSession):
        for p in _gen_prices("YESBANK", 45, start_price=50):
            session.add(p)
        await session.flush()
        result = await svc.analyze("YESBANK", date(2024, 2, 15))
        assert result.symbol == "YESBANK"
        assert result.volume is not None
        assert result.avg_volume_5d is not None
        assert result.avg_volume_20d is not None
        assert result.volume_ratio is not None
        assert result.volume_trend in ("rising", "falling", "stable")
        assert result.liquidity_score is not None
        assert result.liquidity_rating in ("high", "moderate", "low")

    @pytest.mark.asyncio
    async def test_analyze_with_delivery(self, svc: MicrostructureService, session: AsyncSession):
        for p in _gen_prices("DELIV", 45, start_price=100):
            session.add(p)
        await session.flush()
        result = await svc.analyze("DELIV", date(2024, 2, 15), delivery_quantity=30000, total_traded_quantity=100000)
        assert result.delivery_percentage == 0.3
        assert result.delivery_score == 60.0
        assert result.delivery_trend in ("rising", "falling", "stable", None)

    @pytest.mark.asyncio
    async def test_analyze_with_delivery_trend(self, svc: MicrostructureService, session: AsyncSession):
        for p in _gen_prices("DTREND", 45, start_price=100):
            session.add(p)
        await session.flush()
        # Store prior analysis with low delivery
        prior = MarketMicrostructure(
            symbol="DTREND", as_of_date=date(2024, 2, 10),
            delivery_percentage=0.15, delivery_score=30.0, liquidity_score=50.0, liquidity_rating="moderate",
        )
        session.add(prior)
        await session.flush()
        result = await svc.analyze("DTREND", date(2024, 2, 15), delivery_quantity=50000, total_traded_quantity=100000)
        assert result.delivery_percentage == 0.5
        assert result.delivery_trend == "rising"

    @pytest.mark.asyncio
    async def test_spread_tight(self, svc: MicrostructureService, session: AsyncSession):
        prices = []
        base_date = date(2024, 1, 1)
        price = 100
        for i in range(45):
            d = base_date + timedelta(days=i)
            price = price * (1 + 0.001)
            prices.append(DailyPrice(
                symbol="TIGHT", trade_date=d,
                open=round(price * 0.998, 2), high=round(price * 1.003, 2),
                low=round(price * 0.997, 2), close=round(price, 2), volume=100000,
            ))
        for p in prices:
            session.add(p)
        await session.flush()
        result = await svc.analyze("TIGHT", date(2024, 2, 15))
        assert result.spread_regime == "tight"
        assert result.spread_score > 80

    @pytest.mark.asyncio
    async def test_spread_wide(self, svc: MicrostructureService, session: AsyncSession):
        for p in _gen_prices_wide_spread("WIDE", 45, start_price=100):
            session.add(p)
        await session.flush()
        result = await svc.analyze("WIDE", date(2024, 2, 15))
        assert result.spread_regime == "wide"

    @pytest.mark.asyncio
    async def test_high_liquidity_score(self, svc: MicrostructureService, session: AsyncSession):
        for p in _gen_prices_high_volume("HILIQ", 45, start_price=100):
            session.add(p)
        await session.flush()
        result = await svc.analyze("HILIQ", date(2024, 2, 15))
        assert result.liquidity_score > 50

    @pytest.mark.asyncio
    async def test_no_price_data(self, svc: MicrostructureService):
        result = await svc.analyze("UNKNOWN")
        assert result.liquidity_score == 0.0
        assert result.liquidity_rating == "low"

    @pytest.mark.asyncio
    async def test_amihud_illiquidity(self, svc: MicrostructureService, session: AsyncSession):
        for p in _gen_prices("AMIHUD", 45, start_price=100):
            session.add(p)
        await session.flush()
        result = await svc.analyze("AMIHUD", date(2024, 2, 15))
        assert result.amihud_illiquidity is not None
        assert result.amihud_illiquidity >= 0

    @pytest.mark.asyncio
    async def test_dollar_volume(self, svc: MicrostructureService, session: AsyncSession):
        for p in _gen_prices("DOLLAR", 45, start_price=100):
            session.add(p)
        await session.flush()
        result = await svc.analyze("DOLLAR", date(2024, 2, 15))
        assert result.dollar_volume is not None
        assert result.dollar_volume > 0
        assert result.avg_dollar_volume_20d is not None
        assert result.depth_score is not None

    @pytest.mark.asyncio
    async def test_turnover(self, svc: MicrostructureService, session: AsyncSession):
        for p in _gen_prices("TURN", 45, start_price=100):
            session.add(p)
        await session.flush()
        result = await svc.analyze("TURN", date(2024, 2, 15))
        assert result.turnover is not None
        assert result.turnover > 0
        assert result.avg_turnover_20d is not None
        assert result.turnover_ratio is not None

    @pytest.mark.asyncio
    async def test_free_float_turnover(self, svc: MicrostructureService, session: AsyncSession):
        session.add(Company(symbol="FFTURN", company_name="FF Test", isin="IN9999999991", sector="Finance", exchange="NSE", market_cap=10000000000))
        for p in _gen_prices("FFTURN", 45, start_price=100):
            session.add(p)
        await session.flush()
        result = await svc.analyze("FFTURN", date(2024, 2, 15))
        assert result.free_float_turnover is not None
        assert result.free_float_turnover > 0

    @pytest.mark.asyncio
    async def test_volume_percentile(self, svc: MicrostructureService, session: AsyncSession):
        for p in _gen_prices("VPCT", 45, start_price=100):
            session.add(p)
        await session.flush()
        result = await svc.analyze("VPCT", date(2024, 2, 15))
        assert 0 <= result.volume_percentile_20d <= 100

    @pytest.mark.asyncio
    async def test_details_json(self, svc: MicrostructureService, session: AsyncSession):
        for p in _gen_prices("DETAIL", 45, start_price=100):
            session.add(p)
        await session.flush()
        result = await svc.analyze("DETAIL", date(2024, 2, 15))
        data = json.loads(result.details_json)
        assert "close" in data
        assert "high" in data
        assert "low" in data
        assert "vol_component" in data

    @pytest.mark.asyncio
    async def test_get_analysis(self, svc: MicrostructureService, session: AsyncSession):
        for p in _gen_prices("GETAN", 45, start_price=100):
            session.add(p)
        await session.flush()
        await svc.analyze("GETAN", date(2024, 2, 14))
        r2 = await svc.analyze("GETAN", date(2024, 2, 15))
        fetched = await svc.get_analysis("GETAN")
        assert fetched.id == r2.id

    @pytest.mark.asyncio
    async def test_get_analysis_specific_date(self, svc: MicrostructureService, session: AsyncSession):
        for p in _gen_prices("SPEC", 45, start_price=100):
            session.add(p)
        await session.flush()
        r1 = await svc.analyze("SPEC", date(2024, 2, 14))
        await svc.analyze("SPEC", date(2024, 2, 15))
        fetched = await svc.get_analysis("SPEC", date(2024, 2, 14))
        assert fetched.id == r1.id

    @pytest.mark.asyncio
    async def test_get_analysis_not_found(self, svc: MicrostructureService):
        result = await svc.get_analysis("UNKNOWN")
        assert result is None

    @pytest.mark.asyncio
    async def test_list_analysis(self, svc: MicrostructureService, session: AsyncSession):
        for p in _gen_prices("LIST", 45, start_price=100):
            session.add(p)
        await session.flush()
        d = date(2024, 2, 1)
        for i in range(5):
            await svc.analyze("LIST", d + timedelta(days=i))
        results = await svc.list_analysis("LIST", limit=3)
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_rising_volume_trend(self, svc: MicrostructureService, session: AsyncSession):
        prices = []
        base_date = date(2024, 1, 1)
        price = 100
        for i in range(45):
            d = base_date + timedelta(days=i)
            price = price * (1 + 0.001)
            vol = 50000 + i * 5000
            prices.append(DailyPrice(
                symbol="RISEVOL", trade_date=d,
                open=round(price * 0.99, 2), high=round(price * 1.02, 2),
                low=round(price * 0.98, 2), close=round(price, 2), volume=vol,
            ))
        for p in prices:
            session.add(p)
        await session.flush()
        result = await svc.analyze("RISEVOL", date(2024, 2, 15))
        assert result.volume_trend == "rising"

    @pytest.mark.asyncio
    async def test_falling_volume_trend(self, svc: MicrostructureService, session: AsyncSession):
        prices = []
        base_date = date(2024, 1, 1)
        price = 100
        for i in range(45):
            d = base_date + timedelta(days=i)
            price = price * (1 + 0.001)
            vol = max(10000, 200000 - i * 5000)
            prices.append(DailyPrice(
                symbol="FALLVOL", trade_date=d,
                open=round(price * 0.99, 2), high=round(price * 1.02, 2),
                low=round(price * 0.98, 2), close=round(price, 2), volume=vol,
            ))
        for p in prices:
            session.add(p)
        await session.flush()
        result = await svc.analyze("FALLVOL", date(2024, 2, 15))
        assert result.volume_trend == "falling"

    @pytest.mark.asyncio
    async def test_low_liquidity_rating(self, svc: MicrostructureService, session: AsyncSession):
        prices = []
        base_date = date(2024, 1, 1)
        price = 10
        for i in range(45):
            d = base_date + timedelta(days=i)
            price = price * (1 + 0.0005)
            vol = 1000 + (i % 10) * 100
            prices.append(DailyPrice(
                symbol="LOWLIQ", trade_date=d,
                open=round(price * 0.99, 2), high=round(price * 1.03, 2),
                low=round(price * 0.97, 2), close=round(price, 2), volume=vol,
            ))
        for p in prices:
            session.add(p)
        await session.flush()
        result = await svc.analyze("LOWLIQ", date(2024, 2, 15))
        assert result.liquidity_rating == "low"
