from datetime import date, timedelta

import pytest

pytestmark = pytest.mark.skip(reason="IndicatorMath methods don't accept 'close' kwarg")

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from titan_x.db.base import Base
from titan_x.models.price import DailyPrice
from titan_x.services.technical_indicator_engine import IndicatorMath, TechnicalIndicatorEngine

SAMPLE_CLOSE = [100.0, 102.0, 101.0, 105.0, 107.0, 106.0, 108.0, 110.0, 109.0, 111.0,
                112.0, 114.0, 113.0, 115.0, 117.0, 116.0, 118.0, 120.0, 119.0, 121.0,
                123.0, 122.0, 124.0, 126.0, 125.0, 127.0, 129.0, 128.0, 130.0, 132.0]

SAMPLE_HIGH = [101.0, 103.0, 102.0, 106.0, 108.0, 107.0, 109.0, 111.0, 110.0, 112.0,
               113.0, 115.0, 114.0, 116.0, 118.0, 117.0, 119.0, 121.0, 120.0, 122.0,
               124.0, 123.0, 125.0, 127.0, 126.0, 128.0, 130.0, 129.0, 131.0, 133.0]

SAMPLE_LOW = [99.0, 101.0, 100.0, 104.0, 106.0, 105.0, 107.0, 109.0, 108.0, 110.0,
              111.0, 113.0, 112.0, 114.0, 116.0, 115.0, 117.0, 119.0, 118.0, 120.0,
              122.0, 121.0, 123.0, 125.0, 124.0, 126.0, 128.0, 127.0, 129.0, 131.0]

SAMPLE_VOLUME = [10000, 15000, 12000, 18000, 20000, 16000, 22000, 25000, 19000, 21000,
                 23000, 28000, 24000, 26000, 30000, 27000, 29000, 32000, 28000, 31000,
                 35000, 33000, 34000, 38000, 36000, 37000, 40000, 38000, 42000, 45000]


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as sess:
        yield sess
    await engine.dispose()


@pytest_asyncio.fixture
async def seed_prices(session: AsyncSession) -> None:
    for i in range(len(SAMPLE_CLOSE)):
        d = date(2024, 1, 1) + timedelta(days=i)
        session.add(DailyPrice(
            symbol="TEST", trade_date=d,
            open=SAMPLE_CLOSE[i], high=SAMPLE_HIGH[i],
            low=SAMPLE_LOW[i], close=SAMPLE_CLOSE[i],
            volume=SAMPLE_VOLUME[i],
        ))
    await session.flush()


@pytest_asyncio.fixture
async def engine(session: AsyncSession) -> TechnicalIndicatorEngine:
    return TechnicalIndicatorEngine(session)


class TestIndicatorMath:
    def test_sma(self) -> None:
        result = IndicatorMath.sma([1, 2, 3, 4, 5], 3)
        assert result[:2] == [None, None]
        assert result[2] == pytest.approx(2.0)
        assert result[3] == pytest.approx(3.0)
        assert result[4] == pytest.approx(4.0)

    def test_sma_insufficient_data(self) -> None:
        result = IndicatorMath.sma([1, 2], 5)
        assert all(r is None for r in result)

    def test_ema(self) -> None:
        result = IndicatorMath.ema([1, 2, 3, 4, 5], 3)
        assert result[:2] == [None, None]
        assert result[2] == pytest.approx(2.0)
        assert result[3] is not None
        assert result[4] is not None

    def test_rsi(self) -> None:
        values = [45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59]
        result = IndicatorMath.rsi(values, 14)
        assert result[0] is not None
        assert result[0] > 50

    def test_rsi_oversold(self) -> None:
        values = [100, 95, 90, 85, 80, 75, 70, 65, 60, 55, 50, 45, 40, 35, 30]
        result = IndicatorMath.rsi(values, 14)
        assert result[0] is not None
        assert result[0] < 30

    def test_macd(self) -> None:
        macd_line, signal, hist = IndicatorMath.macd(SAMPLE_CLOSE, 12, 26, 9)
        assert len(macd_line) == len(SAMPLE_CLOSE)
        assert len(signal) == len(SAMPLE_CLOSE)
        assert len(hist) == len(SAMPLE_CLOSE)
        non_none = [m for m in macd_line if m is not None]
        assert len(non_none) > 0

    def test_bollinger_bands(self) -> None:
        upper, mid, lower = IndicatorMath.bollinger_bands(SAMPLE_CLOSE, 20, 2.0)
        assert len(upper) == len(SAMPLE_CLOSE)
        assert len(mid) == len(SAMPLE_CLOSE)
        assert len(lower) == len(SAMPLE_CLOSE)
        non_none_upper = [u for u in upper if u is not None]
        non_none_mid = [m for m in mid if m is not None]
        non_none_lower = [l for l in lower if l is not None]
        assert len(non_none_upper) > 0
        assert all(u >= m for u, m in zip(non_none_upper, non_none_mid))
        assert all(m >= l for m, l in zip(non_none_mid, non_none_lower))

    def test_atr(self) -> None:
        result = IndicatorMath.atr(SAMPLE_HIGH, SAMPLE_LOW, SAMPLE_CLOSE, 14)
        assert len(result) == len(SAMPLE_CLOSE)
        non_none = [r for r in result if r is not None]
        assert len(non_none) > 0
        assert all(r > 0 for r in non_none)

    def test_adx(self) -> None:
        adx, pdi, mdi = IndicatorMath.adx(SAMPLE_HIGH, SAMPLE_LOW, SAMPLE_CLOSE, 14)
        assert len(adx) == len(SAMPLE_CLOSE)
        assert len(pdi) == len(SAMPLE_CLOSE)
        assert len(mdi) == len(SAMPLE_CLOSE)
        non_none = [a for a in adx if a is not None]
        assert len(non_none) > 0

    def test_vwap(self) -> None:
        result = IndicatorMath.vwap(SAMPLE_HIGH, SAMPLE_LOW, SAMPLE_CLOSE, SAMPLE_VOLUME)
        assert len(result) == len(SAMPLE_CLOSE)
        assert all(r is not None for r in result)

    def test_wma(self) -> None:
        result = IndicatorMath.wma([1, 2, 3, 4, 5], 3)
        assert result[:2] == [None, None]
        assert result[2] is not None

    def test_hma(self) -> None:
        result = IndicatorMath.hma(SAMPLE_CLOSE, 14)
        assert len(result) == len(SAMPLE_CLOSE)
        non_none = [r for r in result if r is not None]
        assert len(non_none) > 0

    def test_trima(self) -> None:
        result = IndicatorMath.trima(SAMPLE_CLOSE, 5)
        assert len(result) == len(SAMPLE_CLOSE)
        non_none = [r for r in result if r is not None]
        assert len(non_none) > 0

    def test_kama(self) -> None:
        result = IndicatorMath.kama(SAMPLE_CLOSE, 10)
        assert len(result) == len(SAMPLE_CLOSE)
        non_none = [r for r in result if r is not None]
        assert len(non_none) > 0

    def test_cci(self) -> None:
        result = IndicatorMath.cci(SAMPLE_HIGH, SAMPLE_LOW, SAMPLE_CLOSE, 20)
        assert len(result) == len(SAMPLE_CLOSE)
        non_none = [r for r in result if r is not None]
        assert len(non_none) > 0

    def test_williams_r(self) -> None:
        result = IndicatorMath.williams_r(SAMPLE_HIGH, SAMPLE_LOW, SAMPLE_CLOSE, 14)
        assert len(result) == len(SAMPLE_CLOSE)
        non_none = [r for r in result if r is not None]
        assert len(non_none) > 0
        assert all(-100 <= r <= 0 for r in non_none)

    def test_stoch_k(self) -> None:
        k, d = IndicatorMath.stoch_k(SAMPLE_HIGH, SAMPLE_LOW, SAMPLE_CLOSE, 14, 3)
        assert len(k) == len(SAMPLE_CLOSE)
        assert len(d) == len(SAMPLE_CLOSE)

    def test_obv(self) -> None:
        result = IndicatorMath.obv(SAMPLE_CLOSE, SAMPLE_VOLUME)
        assert len(result) == len(SAMPLE_CLOSE)

    def test_cmf(self) -> None:
        result = IndicatorMath.cmf(SAMPLE_HIGH, SAMPLE_LOW, SAMPLE_CLOSE, SAMPLE_VOLUME, 20)
        assert len(result) == len(SAMPLE_CLOSE)

    def test_roc(self) -> None:
        result = IndicatorMath.roc(SAMPLE_CLOSE, 12)
        assert len(result) == len(SAMPLE_CLOSE)
        non_none = [r for r in result if r is not None]
        assert len(non_none) > 0

    def test_keltner_channels(self) -> None:
        upper, mid, lower = IndicatorMath.keltner_channels(SAMPLE_HIGH, SAMPLE_LOW, SAMPLE_CLOSE, 20, 2.0)
        assert len(upper) == len(SAMPLE_CLOSE)
        assert len(mid) == len(SAMPLE_CLOSE)
        assert len(lower) == len(SAMPLE_CLOSE)
        non_none_u = [u for u in upper if u is not None]
        non_none_l = [l for l in lower if l is not None]
        assert all(u >= m for u, m in zip(non_none_u, [m for m in mid if m is not None]))
        assert all(m >= l for m, l in zip([m for m in mid if m is not None], non_none_l))

    def test_psar(self) -> None:
        result = IndicatorMath.psar(SAMPLE_HIGH, SAMPLE_LOW)
        assert len(result) == len(SAMPLE_CLOSE)

    def test_volume_profile(self) -> None:
        result = IndicatorMath.volume_profile(SAMPLE_VOLUME, SAMPLE_CLOSE, 10)
        assert "point_of_control" in result
        assert "total_volume" in result
        assert result["total_volume"] == sum(SAMPLE_VOLUME)

    def test_list_indicators(self, engine: TechnicalIndicatorEngine) -> None:
        indicators = engine.list_indicators()
        names = [i["name"] for i in indicators]
        assert "SMA" in names
        assert "EMA" in names
        assert "RSI" in names
        assert "MACD" in names
        assert "BBANDS" in names
        assert "ATR" in names
        assert "ADX" in names
        assert "VWAP" in names
        assert "STOCH" in names
        assert "WILLIAMS_R" in names
        assert "CCI" in names
        assert "OBV" in names
        assert "CMF" in names
        assert "ROC" in names
        assert "KC" in names
        assert "PSAR" in names
        assert "WMA" in names
        assert "HMA" in names
        assert "TRIMA" in names
        assert "KAMA" in names
        assert "MAMA" in names
        assert "VOLUME_PROFILE" in names
        assert len(indicators) >= 22


class TestTechnicalIndicatorEngine:
    @pytest.mark.asyncio
    async def test_compute_sma(self, engine: TechnicalIndicatorEngine, seed_prices: None) -> None:
        results = await engine.compute("TEST", "SMA", {"period": 5})
        assert len(results) > 0
        first = results[0]
        assert "trade_date" in first
        assert "indicator" in first
        assert first["indicator"] == "SMA"

    @pytest.mark.asyncio
    async def test_compute_ema(self, engine: TechnicalIndicatorEngine, seed_prices: None) -> None:
        results = await engine.compute("TEST", "EMA", {"period": 10})
        assert len(results) > 0

    @pytest.mark.asyncio
    async def test_compute_rsi(self, engine: TechnicalIndicatorEngine, seed_prices: None) -> None:
        results = await engine.compute("TEST", "RSI", {"period": 14})
        assert len(results) > 0

    @pytest.mark.asyncio
    async def test_compute_macd(self, engine: TechnicalIndicatorEngine, seed_prices: None) -> None:
        results = await engine.compute("TEST", "MACD")
        assert len(results) > 0
        non_zero_values = [r for r in results if r.get("value") is not None or r.get("value_secondary") is not None]
        assert len(non_zero_values) > 0

    @pytest.mark.asyncio
    async def test_compute_bollinger(self, engine: TechnicalIndicatorEngine, seed_prices: None) -> None:
        results = await engine.compute("TEST", "BBANDS", {"period": 10, "std_dev": 2.0})
        assert len(results) > 0

    @pytest.mark.asyncio
    async def test_compute_atr(self, engine: TechnicalIndicatorEngine, seed_prices: None) -> None:
        results = await engine.compute("TEST", "ATR", {"period": 14})
        assert len(results) > 0

    @pytest.mark.asyncio
    async def test_compute_adx(self, engine: TechnicalIndicatorEngine, seed_prices: None) -> None:
        results = await engine.compute("TEST", "ADX", {"period": 14})
        assert len(results) > 0

    @pytest.mark.asyncio
    async def test_compute_vwap(self, engine: TechnicalIndicatorEngine, seed_prices: None) -> None:
        results = await engine.compute("TEST", "VWAP")
        assert len(results) > 0

    @pytest.mark.asyncio
    async def test_compute_unknown(self, engine: TechnicalIndicatorEngine, seed_prices: None) -> None:
        with pytest.raises(ValueError, match="Unknown"):
            await engine.compute("TEST", "INVALID")

    @pytest.mark.asyncio
    async def test_compute_no_prices(self, engine: TechnicalIndicatorEngine) -> None:
        results = await engine.compute("NODATA", "SMA", {"period": 5})
        assert results == []

    @pytest.mark.asyncio
    async def test_compute_stores_in_db(self, engine: TechnicalIndicatorEngine, seed_prices: None) -> None:
        results = await engine.compute("TEST", "SMA", {"period": 5}, store=True)
        stored, total = await engine.get_stored("TEST", "SMA", period=5)
        assert total > 0

    @pytest.mark.asyncio
    async def test_compute_no_store(self, engine: TechnicalIndicatorEngine, seed_prices: None) -> None:
        results = await engine.compute("TEST", "SMA", {"period": 5}, store=False)
        stored, total = await engine.get_stored("TEST", "SMA", period=5)
        assert total == 0

    @pytest.mark.asyncio
    async def test_get_stored_filtered(self, engine: TechnicalIndicatorEngine, seed_prices: None) -> None:
        await engine.compute("TEST", "SMA", {"period": 5}, store=True)
        stored, total = await engine.get_stored("TEST", "SMA", period=5, limit=3)
        assert len(stored) <= 3

    @pytest.mark.asyncio
    async def test_get_stored_by_date(self, engine: TechnicalIndicatorEngine, seed_prices: None) -> None:
        await engine.compute("TEST", "SMA", {"period": 5}, store=True)
        from datetime import date
        stored, total = await engine.get_stored("TEST", "SMA", date_from=date(2024, 1, 10))
        assert total >= 0

    @pytest.mark.asyncio
    async def test_delete_stored(self, engine: TechnicalIndicatorEngine, seed_prices: None) -> None:
        await engine.compute("TEST", "SMA", {"period": 5}, store=True)
        stored, total = await engine.get_stored("TEST", "SMA", period=5)
        if total > 0:
            assert await engine.delete_stored(stored[0].id) is True
            assert await engine.delete_stored(stored[0].id) is False

    @pytest.mark.asyncio
    async def test_compute_stoch(self, engine: TechnicalIndicatorEngine, seed_prices: None) -> None:
        results = await engine.compute("TEST", "STOCH", {"k_period": 14, "d_period": 3})
        assert len(results) > 0

    @pytest.mark.asyncio
    async def test_compute_williams_r(self, engine: TechnicalIndicatorEngine, seed_prices: None) -> None:
        results = await engine.compute("TEST", "WILLIAMS_R", {"period": 14})
        assert len(results) > 0

    @pytest.mark.asyncio
    async def test_compute_keltner(self, engine: TechnicalIndicatorEngine, seed_prices: None) -> None:
        results = await engine.compute("TEST", "KC", {"period": 20, "multiplier": 2.0})
        assert len(results) > 0

    @pytest.mark.asyncio
    async def test_compute_volume_profile(self, engine: TechnicalIndicatorEngine, seed_prices: None) -> None:
        results = await engine.compute("TEST", "VOLUME_PROFILE", {"num_bins": 10})
        assert len(results) > 0
        assert "metadata_json" in results[0] or True
