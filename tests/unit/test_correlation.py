import json
from datetime import date, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from titan_x.db.base import Base
from titan_x.models.company import Company
from titan_x.models.correlation import CorrelationMatrix, CorrelationPair
from titan_x.models.price import DailyPrice
from titan_x.services.correlation_service import CorrelationService


def _gen_prices(symbol: str, count: int, start_price: float = 100, seed: int = 0) -> list[DailyPrice]:
    prices = []
    base_date = date(2023, 6, 1)
    price = start_price
    for i in range(count):
        d = base_date + timedelta(days=i)
        drift = 0.001
        noise = ((i + seed) % 7 - 3) * 0.3
        price = price * (1 + drift + noise * 0.01)
        prices.append(DailyPrice(
            symbol=symbol, trade_date=d,
            open=round(price * 0.99, 2), high=round(price * 1.02, 2),
            low=round(price * 0.98, 2), close=round(price, 2), volume=100000,
        ))
    return prices


def _gen_correlated_prices(symbol: str, base_prices: list[float], noise_scale: float = 0.1) -> list[DailyPrice]:
    prices = []
    base_date = date(2023, 6, 1)
    for i, bp in enumerate(base_prices):
        d = base_date + timedelta(days=i)
        noise = ((i % 5) - 2) * noise_scale
        price = bp * (1 + noise * 0.01)
        prices.append(DailyPrice(
            symbol=symbol, trade_date=d,
            open=round(price * 0.99, 2), high=round(price * 1.02, 2),
            low=round(price * 0.98, 2), close=round(price, 2), volume=100000,
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
def svc(session: AsyncSession) -> CorrelationService:
    return CorrelationService(session)


@pytest_asyncio.fixture
async def correlated_data(session: AsyncSession):
    """Create 300 days of highly correlated price series."""
    base_date = date(2023, 6, 1)
    base_price = 100
    base_series = []
    for i in range(300):
        d = base_date + timedelta(days=i)
        drift = 0.001
        noise = (i % 7 - 3) * 0.3
        base_price = base_price * (1 + drift + noise * 0.01)
        base_series.append(base_price)
        session.add(DailyPrice(
            symbol="BASE", trade_date=d,
            open=round(base_price * 0.99, 2), high=round(base_price * 1.02, 2),
            low=round(base_price * 0.98, 2), close=round(base_price, 2), volume=100000,
        ))

    # Highly correlated stock A (very little noise)
    for i, bp in enumerate(base_series):
        d = base_date + timedelta(days=i)
        noise = (i % 5 - 2) * 0.05
        price = bp * (1 + noise * 0.01)
        session.add(DailyPrice(
            symbol="CORR_A", trade_date=d,
            open=round(price * 0.99, 2), high=round(price * 1.02, 2),
            low=round(price * 0.98, 2), close=round(price, 2), volume=100000,
        ))

    # Weakly correlated stock B (lots of noise)
    for i, bp in enumerate(base_series):
        d = base_date + timedelta(days=i)
        noise = (i % 3 - 1) * 2.0
        price = bp * (1 + noise * 0.01)
        session.add(DailyPrice(
            symbol="CORR_B", trade_date=d,
            open=round(price * 0.99, 2), high=round(price * 1.02, 2),
            low=round(price * 0.98, 2), close=round(price, 2), volume=100000,
        ))

    await session.flush()


# ============================================================
# STOCK CORRELATION
# ============================================================

class TestStockCorrelation:
    @pytest.mark.asyncio
    async def test_high_correlation(self, svc: CorrelationService, correlated_data):
        result = await svc.stock_correlation("CORR_A", "BASE")
        assert result.correlation_type == "stock"
        assert result.samples >= 250
        assert result.correlation_value is not None
        assert result.correlation_value > 0.5

    @pytest.mark.asyncio
    async def test_lower_correlation(self, svc: CorrelationService, correlated_data):
        result = await svc.stock_correlation("CORR_B", "BASE")
        assert result.correlation_value is not None
        assert result.correlation_value < 0.9  # more noise = lower corr

    @pytest.mark.asyncio
    async def test_self_correlation(self, svc: CorrelationService, session: AsyncSession):
        for p in _gen_prices("SELF", 260):
            session.add(p)
        await session.flush()
        result = await svc.stock_correlation("SELF", "SELF")
        assert result.correlation_value == 1.0

    @pytest.mark.asyncio
    async def test_insufficient_data(self, svc: CorrelationService, session: AsyncSession):
        session.add(DailyPrice(symbol="A", trade_date=date(2024, 1, 1), open=100, high=101, low=99, close=100, volume=1000))
        session.add(DailyPrice(symbol="B", trade_date=date(2024, 1, 1), open=100, high=101, low=99, close=100, volume=1000))
        await session.flush()
        result = await svc.stock_correlation("A", "B", lookback_days=30)
        assert result.correlation_value is None

    @pytest.mark.asyncio
    async def test_inverse_correlation(self, svc: CorrelationService, session: AsyncSession):
        base_date = date(2023, 6, 1)
        price_a, price_b = 100, 100
        for i in range(260):
            d = base_date + timedelta(days=i)
            noise = (i % 7 - 3) * 0.3
            price_a = price_a * (1 + 0.001 + noise * 0.01)
            price_b = price_b * (1 + 0.001 - noise * 0.01)
            session.add(DailyPrice(symbol="POS", trade_date=d, open=price_a * 0.99, high=price_a * 1.02, low=price_a * 0.98, close=price_a, volume=100000))
            session.add(DailyPrice(symbol="NEG", trade_date=d, open=price_b * 0.99, high=price_b * 1.02, low=price_b * 0.98, close=price_b, volume=100000))
        await session.flush()
        result = await svc.stock_correlation("POS", "NEG", lookback_days=252)
        assert result.correlation_value is not None
        assert result.correlation_value < 0

    @pytest.mark.asyncio
    async def test_get_pair(self, svc: CorrelationService, correlated_data):
        await svc.stock_correlation("CORR_A", "BASE")
        fetched = await svc.get_pair("stock", "CORR_A", "BASE")
        assert fetched is not None
        assert fetched.correlation_value is not None


# ============================================================
# SECTOR CORRELATION
# ============================================================

class TestSectorCorrelation:
    @pytest.mark.asyncio
    async def test_sector_correlation(self, svc: CorrelationService, session: AsyncSession):
        session.add(Company(symbol="TECH1", company_name="T1", isin="IN001", sector="Technology", exchange="NSE"))
        session.add(Company(symbol="TECH2", company_name="T2", isin="IN002", sector="Technology", exchange="NSE"))
        session.add(Company(symbol="FIN1", company_name="F1", isin="IN003", sector="Finance", exchange="NSE"))
        session.add(Company(symbol="FIN2", company_name="F2", isin="IN004", sector="Finance", exchange="NSE"))
        for p in _gen_prices("TECH1", 260, start_price=100, seed=1):
            session.add(p)
        for p in _gen_prices("TECH2", 260, start_price=100, seed=2):
            session.add(p)
        for p in _gen_prices("FIN1", 260, start_price=100, seed=10):
            session.add(p)
        for p in _gen_prices("FIN2", 260, start_price=100, seed=11):
            session.add(p)
        await session.flush()
        result = await svc.sector_correlation("Technology", "Finance", lookback_days=252)
        assert result.correlation_type == "sector"
        assert result.samples is not None
        assert result.samples >= 200

    @pytest.mark.asyncio
    async def test_sector_correlation_same(self, svc: CorrelationService, session: AsyncSession):
        session.add(Company(symbol="S1", company_name="S1", isin="IN010", sector="SameSec", exchange="NSE"))
        session.add(Company(symbol="S2", company_name="S2", isin="IN011", sector="SameSec", exchange="NSE"))
        for p in _gen_prices("S1", 260, start_price=100, seed=1):
            session.add(p)
        for p in _gen_prices("S2", 260, start_price=100, seed=2):
            session.add(p)
        await session.flush()
        result = await svc.sector_correlation("SameSec", "SameSec", lookback_days=252)
        assert result.correlation_value is not None


# ============================================================
# INDEX CORRELATION
# ============================================================

class TestIndexCorrelation:
    @pytest.mark.asyncio
    async def test_index_correlation(self, svc: CorrelationService, correlated_data):
        result = await svc.index_correlation("CORR_A", "BASE")
        assert result.correlation_type == "stock"
        assert result.symbol_1 == "CORR_A"
        assert result.symbol_2 == "BASE"
        assert result.correlation_value is not None


# ============================================================
# PORTFOLIO CORRELATION
# ============================================================

class TestPortfolioCorrelation:
    @pytest.mark.asyncio
    async def test_portfolio_matrix(self, svc: CorrelationService, session: AsyncSession):
        for p in _gen_prices("A", 260, start_price=100, seed=1):
            session.add(p)
        for p in _gen_prices("B", 260, start_price=100, seed=2):
            session.add(p)
        for p in _gen_prices("C", 260, start_price=100, seed=3):
            session.add(p)
        await session.flush()
        result = await svc.portfolio_correlation(["A", "B", "C"], "test_portfolio")
        assert result.matrix_type == "portfolio"
        symbols = json.loads(result.symbols_json)
        assert symbols == ["A", "B", "C"]
        matrix = json.loads(result.matrix_json)
        assert len(matrix) == 3
        assert len(matrix[0]) == 3
        assert matrix[0][0] == 1.0
        assert matrix[1][1] == 1.0
        assert matrix[2][2] == 1.0

    @pytest.mark.asyncio
    async def test_portfolio_insufficient_data(self, svc: CorrelationService):
        result = await svc.portfolio_correlation(["X", "Y"], "empty")
        matrix = json.loads(result.matrix_json)
        assert matrix[0][0] == 1.0
        assert matrix[0][1] == 0.0

    @pytest.mark.asyncio
    async def test_get_matrix(self, svc: CorrelationService, session: AsyncSession):
        for p in _gen_prices("M1", 260, start_price=100, seed=1):
            session.add(p)
        for p in _gen_prices("M2", 260, start_price=100, seed=2):
            session.add(p)
        await session.flush()
        await svc.portfolio_correlation(["M1", "M2"], "get_test")
        fetched = await svc.get_matrix("portfolio", "get_test")
        assert fetched is not None
        assert json.loads(fetched.symbols_json) == ["M1", "M2"]


# ============================================================
# HEATMAP
# ============================================================

class TestHeatmap:
    @pytest.mark.asyncio
    async def test_heatmap(self, svc: CorrelationService, session: AsyncSession):
        for p in _gen_prices("H1", 260, start_price=100, seed=1):
            session.add(p)
        for p in _gen_prices("H2", 260, start_price=100, seed=2):
            session.add(p)
        for p in _gen_prices("H3", 260, start_price=100, seed=3):
            session.add(p)
        await session.flush()
        result = await svc.heatmap(["H1", "H2", "H3"])
        symbols = json.loads(result.symbols_json)
        matrix = json.loads(result.matrix_json)
        assert len(symbols) == 3
        assert len(matrix) == 3
        metadata = json.loads(result.metadata_json)
        assert "samples" in metadata
        assert "date_range" in metadata
        assert metadata["date_range"]["start"] is not None

    @pytest.mark.asyncio
    async def test_heatmap_metadata(self, svc: CorrelationService, session: AsyncSession):
        for p in _gen_prices("HM1", 260, start_price=100, seed=1):
            session.add(p)
        for p in _gen_prices("HM2", 260, start_price=100, seed=2):
            session.add(p)
        await session.flush()
        result = await svc.heatmap(["HM1", "HM2"])
        metadata = json.loads(result.metadata_json)
        assert metadata["samples"] >= 250


# ============================================================
# SECTOR HEATMAP
# ============================================================

class TestSectorHeatmap:
    @pytest.mark.asyncio
    async def test_sector_heatmap(self, svc: CorrelationService, session: AsyncSession):
        session.add(Company(symbol="SH1", company_name="SH1", isin="IN100", sector="Energy", exchange="NSE"))
        session.add(Company(symbol="SH2", company_name="SH2", isin="IN101", sector="Energy", exchange="NSE"))
        session.add(Company(symbol="SH3", company_name="SH3", isin="IN102", sector="Healthcare", exchange="NSE"))
        session.add(Company(symbol="SH4", company_name="SH4", isin="IN103", sector="Healthcare", exchange="NSE"))
        for p in _gen_prices("SH1", 260, start_price=100, seed=1):
            session.add(p)
        for p in _gen_prices("SH2", 260, start_price=100, seed=2):
            session.add(p)
        for p in _gen_prices("SH3", 260, start_price=100, seed=10):
            session.add(p)
        for p in _gen_prices("SH4", 260, start_price=100, seed=11):
            session.add(p)
        await session.flush()
        result = await svc.sector_heatmap(lookback_days=252)
        sectors = json.loads(result.symbols_json)
        matrix = json.loads(result.matrix_json)
        assert "Energy" in sectors
        assert "Healthcare" in sectors
        assert len(matrix) == len(sectors)
        for i, sec in enumerate(sectors):
            assert matrix[i][i] == 1.0

    @pytest.mark.asyncio
    async def test_sector_heatmap_single_sector(self, svc: CorrelationService, session: AsyncSession):
        session.add(Company(symbol="ONLY1", company_name="O1", isin="IN200", sector="OnlySec", exchange="NSE"))
        session.add(Company(symbol="ONLY2", company_name="O2", isin="IN201", sector="OnlySec", exchange="NSE"))
        for p in _gen_prices("ONLY1", 260, start_price=100, seed=1):
            session.add(p)
        for p in _gen_prices("ONLY2", 260, start_price=100, seed=2):
            session.add(p)
        await session.flush()
        with pytest.raises(ValueError, match="at least 2 sectors"):
            await svc.sector_heatmap()
