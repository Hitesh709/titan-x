import json
from datetime import date, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from titan_x.db.base import Base
from titan_x.models.market_breadth import MarketBreadth
from titan_x.models.price import DailyPrice
from titan_x.models.regime import MarketRegime, RegimeSignal
from titan_x.services.regime_detection_service import RegimeDetectionService


def _gen_prices(symbol: str, count: int, start_price: float = 100, uptrend: bool = True) -> list[DailyPrice]:
    """Generate synthetic daily prices."""
    prices = []
    base_date = date(2024, 1, 1)
    price = start_price
    for i in range(count):
        d = base_date + timedelta(days=i)
        drift = 0.003 if uptrend else -0.003
        noise = ((i % 7) - 3) * 0.2
        price = price * (1 + drift + noise * 0.01)
        prices.append(DailyPrice(
            symbol=symbol,
            trade_date=d,
            open=round(price * 0.99, 2),
            high=round(price * 1.02, 2),
            low=round(price * 0.98, 2),
            close=round(price, 2),
            volume=100000 + i * 100,
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
def svc(session: AsyncSession) -> RegimeDetectionService:
    return RegimeDetectionService(session)


# ============================================================
# REGIME DETECTION
# ============================================================

class TestRegimeDetection:
    @pytest.mark.asyncio
    async def test_detect_regime_uptrend(self, svc: RegimeDetectionService, session: AsyncSession):
        for p in _gen_prices("NIFTY", 230, start_price=100, uptrend=True):
            session.add(p)
        await session.flush()
        regime = await svc.detect_regime("NIFTY", date(2024, 8, 20))
        assert regime.symbol == "NIFTY"
        assert regime.trend_regime == "bull"
        assert regime.trend_score > 60
        assert regime.confidence > 0.5

    @pytest.mark.asyncio
    async def test_detect_regime_downtrend(self, svc: RegimeDetectionService, session: AsyncSession):
        for p in _gen_prices("BEAR", 230, start_price=200, uptrend=False):
            session.add(p)
        await session.flush()
        regime = await svc.detect_regime("BEAR", date(2024, 8, 20))
        assert regime.trend_regime == "bear"
        assert regime.trend_score < 40

    @pytest.mark.asyncio
    async def test_detect_regime_sideways(self, svc: RegimeDetectionService, session: AsyncSession):
        prices = []
        base_date = date(2024, 1, 1)
        price = 100
        for i in range(230):
            noise = ((i % 5) - 2) * 0.5
            price = 100 + noise
            prices.append(DailyPrice(
                symbol="RANGE", trade_date=base_date + timedelta(days=i),
                open=price - 0.5, high=price + 1, low=price - 1, close=price, volume=100000,
            ))
        for p in prices:
            session.add(p)
        await session.flush()
        regime = await svc.detect_regime("RANGE", date(2024, 8, 20))
        assert regime.trend_regime == "sideways"

    @pytest.mark.asyncio
    async def test_detect_high_volatility(self, svc: RegimeDetectionService, session: AsyncSession):
        prices = []
        base_date = date(2024, 1, 1)
        price = 100
        # 210 stable days
        for i in range(210):
            price = price * (1 + 0.001)
            prices.append(DailyPrice(
                symbol="VOL", trade_date=base_date + timedelta(days=i),
                open=round(price * 0.998, 2), high=round(price * 1.002, 2),
                low=round(price * 0.998, 2), close=round(price, 2), volume=100000,
            ))
        # 20 highly volatile days
        for i in range(210, 230):
            big_move = ((i % 3) - 1) * 3.0
            price = price * (1 + big_move * 0.01)
            prices.append(DailyPrice(
                symbol="VOL", trade_date=base_date + timedelta(days=i),
                open=round(price * 0.97, 2), high=round(price * 1.04, 2),
                low=round(price * 0.96, 2), close=round(price, 2), volume=100000,
            ))
        for p in prices:
            session.add(p)
        await session.flush()
        regime = await svc.detect_regime("VOL", date(2024, 8, 20))
        assert regime.volatility_regime == "high_volatility"

    @pytest.mark.asyncio
    async def test_detect_low_volatility(self, svc: RegimeDetectionService, session: AsyncSession):
        prices = []
        base_date = date(2024, 1, 1)
        price = 100
        # 210 volatile days
        for i in range(210):
            big_move = ((i % 3) - 1) * 2.0
            price = price * (1 + big_move * 0.01)
            prices.append(DailyPrice(
                symbol="STABLE", trade_date=base_date + timedelta(days=i),
                open=round(price * 0.98, 2), high=round(price * 1.03, 2),
                low=round(price * 0.97, 2), close=round(price, 2), volume=100000,
            ))
        # 20 very stable days
        for i in range(210, 230):
            price = price * (1 + 0.0002)
            prices.append(DailyPrice(
                symbol="STABLE", trade_date=base_date + timedelta(days=i),
                open=round(price * 0.9995, 2), high=round(price * 1.0005, 2),
                low=round(price * 0.9995, 2), close=round(price, 2), volume=100000,
            ))
        for p in prices:
            session.add(p)
        await session.flush()
        regime = await svc.detect_regime("STABLE", date(2024, 8, 20))
        assert regime.volatility_regime == "low_volatility"

    @pytest.mark.asyncio
    async def test_sentiment_risk_on(self, svc: RegimeDetectionService, session: AsyncSession):
        for p in _gen_prices("RISKON", 230, start_price=100, uptrend=True):
            session.add(p)
        session.add(MarketBreadth(trade_date=date(2024, 8, 20),
            advancing=800, declining=200, unchanged=50, total_stocks=1050,
            advancing_volume=800000, declining_volume=200000, unchanged_volume=50000, total_volume=1050000,
            new_highs=100, new_lows=10,
            advance_decline_ratio=4.0, advance_decline_line=5000, volume_breadth_ratio=4.0,
            breadth_oscillator=0.6, index_strength_score=75.0))
        await session.flush()
        regime = await svc.detect_regime("RISKON", date(2024, 8, 20))
        assert regime.sentiment_regime == "risk_on"

    @pytest.mark.asyncio
    async def test_sentiment_risk_off(self, svc: RegimeDetectionService, session: AsyncSession):
        for p in _gen_prices("RISKOFF", 230, start_price=200, uptrend=False):
            session.add(p)
        session.add(MarketBreadth(trade_date=date(2024, 8, 20),
            advancing=200, declining=800, unchanged=50, total_stocks=1050,
            advancing_volume=200000, declining_volume=800000, unchanged_volume=50000, total_volume=1050000,
            new_highs=10, new_lows=100,
            advance_decline_ratio=0.25, advance_decline_line=-5000, volume_breadth_ratio=0.25,
            breadth_oscillator=-0.6, index_strength_score=25.0))
        await session.flush()
        regime = await svc.detect_regime("RISKOFF", date(2024, 8, 20))
        assert regime.sentiment_regime == "risk_off"

    @pytest.mark.asyncio
    async def test_insufficient_data(self, svc: RegimeDetectionService):
        regime = await svc.detect_regime("NEW")
        assert regime.trend_regime == "sideways"
        assert regime.confidence == 0.1

    @pytest.mark.asyncio
    async def test_get_regime_returns_latest(self, svc: RegimeDetectionService, session: AsyncSession):
        for p in _gen_prices("GETREG", 230, start_price=100, uptrend=True):
            session.add(p)
        await session.flush()
        r1 = await svc.detect_regime("GETREG", date(2024, 8, 19))
        r2 = await svc.detect_regime("GETREG", date(2024, 8, 20))
        fetched = await svc.get_regime("GETREG")
        assert fetched.id == r2.id

    @pytest.mark.asyncio
    async def test_get_regime_specific_date(self, svc: RegimeDetectionService, session: AsyncSession):
        for p in _gen_prices("SPECD", 230, start_price=100, uptrend=True):
            session.add(p)
        await session.flush()
        r1 = await svc.detect_regime("SPECD", date(2024, 8, 19))
        await svc.detect_regime("SPECD", date(2024, 8, 20))
        fetched = await svc.get_regime("SPECD", date(2024, 8, 19))
        assert fetched.id == r1.id

    @pytest.mark.asyncio
    async def test_get_regime_not_found(self, svc: RegimeDetectionService):
        result = await svc.get_regime("UNKNOWN")
        assert result is None

    @pytest.mark.asyncio
    async def test_list_regimes(self, svc: RegimeDetectionService, session: AsyncSession):
        for p in _gen_prices("LISTREG", 230, start_price=100, uptrend=True):
            session.add(p)
        await session.flush()
        d = date(2024, 8, 1)
        for i in range(5):
            await svc.detect_regime("LISTREG", d + timedelta(days=i))
        results = await svc.list_regimes("LISTREG", limit=3)
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_details_json(self, svc: RegimeDetectionService, session: AsyncSession):
        for p in _gen_prices("DETAIL", 230, start_price=100, uptrend=True):
            session.add(p)
        await session.flush()
        regime = await svc.detect_regime("DETAIL", date(2024, 8, 20))
        data = json.loads(regime.details_json)
        assert "price_count" in data
        assert "current_price" in data

    @pytest.mark.asyncio
    async def test_regime_persists_all_axes(self, svc: RegimeDetectionService, session: AsyncSession):
        for p in _gen_prices("AXES", 230, start_price=100, uptrend=True):
            session.add(p)
        await session.flush()
        regime = await svc.detect_regime("AXES", date(2024, 8, 20))
        assert regime.trend_regime is not None
        assert regime.volatility_regime is not None
        assert regime.sentiment_regime is not None


# ============================================================
# AI SIGNAL GENERATION
# ============================================================

class TestRegimeSignal:
    @pytest.mark.asyncio
    async def test_generate_signal_includes_detect(self, svc: RegimeDetectionService, session: AsyncSession):
        for p in _gen_prices("SIG", 230, start_price=100, uptrend=True):
            session.add(p)
        await session.flush()
        signal = await svc.generate_signal("SIG", date(2024, 8, 20))
        assert signal.symbol == "SIG"
        assert signal.signal in ("strong_buy", "buy", "hold", "sell", "strong_sell")
        assert signal.confidence > 0
        assert signal.regime_id is not None
        assert signal.expiry_date is not None

    @pytest.mark.asyncio
    async def test_generate_signal_uptrend(self, svc: RegimeDetectionService, session: AsyncSession):
        for p in _gen_prices("BULL", 230, start_price=100, uptrend=True):
            session.add(p)
        await session.flush()
        signal = await svc.generate_signal("BULL", date(2024, 8, 20))
        assert signal.signal in ("strong_buy", "buy")
        assert signal.confidence > 0.4

    @pytest.mark.asyncio
    async def test_generate_signal_downtrend(self, svc: RegimeDetectionService, session: AsyncSession):
        for p in _gen_prices("BEAR", 230, start_price=200, uptrend=False):
            session.add(p)
        await session.flush()
        signal = await svc.generate_signal("BEAR", date(2024, 8, 20))
        assert signal.signal in ("sell", "strong_sell")

    @pytest.mark.asyncio
    async def test_supporting_factors_json(self, svc: RegimeDetectionService, session: AsyncSession):
        for p in _gen_prices("FACTOR", 230, start_price=100, uptrend=True):
            session.add(p)
        await session.flush()
        signal = await svc.generate_signal("FACTOR", date(2024, 8, 20))
        factors = json.loads(signal.supporting_factors)
        assert isinstance(factors, list)
        assert len(factors) > 0

    @pytest.mark.asyncio
    async def test_regime_summary_format(self, svc: RegimeDetectionService, session: AsyncSession):
        for p in _gen_prices("SUMM", 230, start_price=100, uptrend=True):
            session.add(p)
        await session.flush()
        signal = await svc.generate_signal("SUMM", date(2024, 8, 20))
        parts = signal.regime_summary.split("/")
        assert len(parts) == 3

    @pytest.mark.asyncio
    async def test_get_signal_returns_latest(self, svc: RegimeDetectionService, session: AsyncSession):
        for p in _gen_prices("GETSIG", 230, start_price=100, uptrend=True):
            session.add(p)
        await session.flush()
        s1 = await svc.generate_signal("GETSIG", date(2024, 8, 19))
        s2 = await svc.generate_signal("GETSIG", date(2024, 8, 20))
        fetched = await svc.get_signal("GETSIG")
        assert fetched.id == s2.id

    @pytest.mark.asyncio
    async def test_get_signal_specific_date(self, svc: RegimeDetectionService, session: AsyncSession):
        for p in _gen_prices("SIGDT", 230, start_price=100, uptrend=True):
            session.add(p)
        await session.flush()
        s1 = await svc.generate_signal("SIGDT", date(2024, 8, 19))
        await svc.generate_signal("SIGDT", date(2024, 8, 20))
        fetched = await svc.get_signal("SIGDT", date(2024, 8, 19))
        assert fetched.id == s1.id

    @pytest.mark.asyncio
    async def test_get_signal_not_found(self, svc: RegimeDetectionService):
        result = await svc.get_signal("UNKNOWN")
        assert result is None

    @pytest.mark.asyncio
    async def test_list_signals(self, svc: RegimeDetectionService, session: AsyncSession):
        for p in _gen_prices("LISTSIG", 230, start_price=100, uptrend=True):
            session.add(p)
        await session.flush()
        d = date(2024, 8, 1)
        for i in range(5):
            await svc.generate_signal("LISTSIG", d + timedelta(days=i))
        results = await svc.list_signals("LISTSIG", limit=3)
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_signal_with_existing_regime(self, svc: RegimeDetectionService, session: AsyncSession):
        for p in _gen_prices("EXIST", 230, start_price=100, uptrend=True):
            session.add(p)
        await session.flush()
        regime = await svc.detect_regime("EXIST", date(2024, 8, 20))
        signal = await svc.generate_signal("EXIST", date(2024, 8, 20))
        assert signal.regime_id == regime.id

    @pytest.mark.asyncio
    async def test_expiry_date_set(self, svc: RegimeDetectionService, session: AsyncSession):
        for p in _gen_prices("EXP", 230, start_price=100, uptrend=True):
            session.add(p)
        await session.flush()
        signal = await svc.generate_signal("EXP", date(2024, 8, 20))
        assert signal.expiry_date == date(2024, 8, 25)

    @pytest.mark.asyncio
    async def test_insufficient_data_signal(self, svc: RegimeDetectionService):
        signal = await svc.generate_signal("NEWSYM")
        assert signal.signal in ("strong_buy", "buy", "hold", "sell", "strong_sell")
        assert signal.regime_id is not None

    @pytest.mark.asyncio
    async def test_breadth_enhances_confidence(self, svc: RegimeDetectionService, session: AsyncSession):
        for p in _gen_prices("BRDCONF", 230, start_price=100, uptrend=True):
            session.add(p)
        session.add(MarketBreadth(trade_date=date(2024, 8, 20),
            advancing=900, declining=100, unchanged=0, total_stocks=1000,
            advancing_volume=900000, declining_volume=100000, unchanged_volume=0, total_volume=1000000,
            new_highs=150, new_lows=5,
            advance_decline_ratio=9.0, advance_decline_line=8000, volume_breadth_ratio=9.0,
            breadth_oscillator=0.8, index_strength_score=90.0))
        await session.flush()
        regime = await svc.detect_regime("BRDCONF", date(2024, 8, 20))
        assert regime.sentiment_score > 60
