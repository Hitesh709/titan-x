import math
from datetime import date, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from titan_x.db.base import Base
from titan_x.models.company import Company
from titan_x.models.price import DailyPrice
from titan_x.models.risk import RiskMetrics, PortfolioRisk
from titan_x.services.risk_engine import RiskEngine


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
async def risk_engine(session: AsyncSession) -> RiskEngine:
    return RiskEngine(session)


def _seed_prices(
    session: AsyncSession, symbol: str = "TEST",
    base_close: float = 100.0, trend: float = 0.05,
    volatility: float = 1.5, num_days: int = 500,
    base_date: date = date(2023, 1, 1),
) -> None:
    prices: list[DailyPrice] = []
    close = base_close
    for i in range(num_days):
        d = base_date + timedelta(days=i)
        noise = (i % 7 - 3) * volatility * 0.2
        cycle = math.sin(i * 0.1) * 5
        close = base_close + trend * i + cycle + noise
        gap = (i % 20 == 0) * 2.0
        open_p = close - gap
        prices.append(DailyPrice(
            symbol=symbol, trade_date=d,
            open=round(max(open_p, 1), 2),
            high=round(close + volatility, 2),
            low=round(close - volatility, 2),
            close=round(close, 2),
            volume=100000 + (i % 50) * 2000,
        ))
    for p in prices:
        session.add(p)


class TestMaxDrawdown:
    @pytest.mark.asyncio
    async def test_compute_max_drawdown(self, risk_engine: RiskEngine) -> None:
        prices = [{"close": 100.0}, {"close": 110.0}, {"close": 120.0},
                  {"close": 115.0}, {"close": 105.0}, {"close": 125.0}]
        result = risk_engine._compute_max_drawdown(prices, "1m")
        assert "max_drawdown_1m" in result
        assert result["max_drawdown_1m"] < 0

    @pytest.mark.asyncio
    async def test_no_drawdown(self, risk_engine: RiskEngine) -> None:
        prices = [{"close": 100.0}, {"close": 110.0}, {"close": 120.0}]
        result = risk_engine._compute_max_drawdown(prices, "1m")
        assert result["max_drawdown_1m"] == 0.0

    @pytest.mark.asyncio
    async def test_insufficient_data(self, risk_engine: RiskEngine) -> None:
        result = risk_engine._compute_max_drawdown([{"close": 100.0}], "1m")
        assert result["max_drawdown_1m"] is None


class TestVolatility:
    @pytest.mark.asyncio
    async def test_compute_volatility(self, risk_engine: RiskEngine) -> None:
        prices = [{"close": 100.0}, {"close": 102.0}, {"close": 98.0},
                  {"close": 101.0}, {"close": 99.0}, {"close": 103.0}]
        result = risk_engine._compute_volatility(prices, "20d")
        assert "volatility_20d" in result
        assert result["volatility_20d"] is not None
        assert result["volatility_20d"] > 0

    @pytest.mark.asyncio
    async def test_volatility_flat(self, risk_engine: RiskEngine) -> None:
        prices = [{"close": 100.0} for _ in range(10)]
        result = risk_engine._compute_volatility(prices, "20d")
        assert result["volatility_20d"] == 0.0


class TestLiquidity:
    @pytest.mark.asyncio
    async def test_compute_liquidity(self, risk_engine: RiskEngine) -> None:
        prices = [{"close": 100.0, "volume": 100000} for _ in range(20)]
        result = risk_engine._compute_liquidity(prices)
        assert result["avg_daily_volume_20d"] == 100000
        assert result["liquidity_score"] is not None

    @pytest.mark.asyncio
    async def test_liquidity_empty(self, risk_engine: RiskEngine) -> None:
        result = risk_engine._compute_liquidity([])
        assert result["avg_daily_volume_20d"] is None


class TestGapRisk:
    @pytest.mark.asyncio
    async def test_compute_gap_risk(self, risk_engine: RiskEngine) -> None:
        prices = []
        for i in range(30):
            prices.append({"open": 100.0 + (i % 3), "close": 100.0 + i})
        result = risk_engine._compute_gap_risk(prices)
        assert result["gap_frequency_20d"] is not None

    @pytest.mark.asyncio
    async def test_gap_risk_insufficient(self, risk_engine: RiskEngine) -> None:
        prices = [{"open": 100.0, "close": 101.0} for _ in range(3)]
        result = risk_engine._compute_gap_risk(prices)
        assert result["gap_frequency_20d"] is None


class TestEventRisk:
    @pytest.mark.asyncio
    async def test_compute_event_risk_low(self, risk_engine: RiskEngine) -> None:
        result = risk_engine._compute_event_risk(0)
        assert result["event_risk_score"] == 10

    @pytest.mark.asyncio
    async def test_compute_event_risk_high(self, risk_engine: RiskEngine) -> None:
        result = risk_engine._compute_event_risk(200)
        assert result["event_risk_score"] == 70


class TestCompositeScore:
    @pytest.mark.asyncio
    async def test_composite_score(self, risk_engine: RiskEngine) -> None:
        result = risk_engine._compute_composite_score(
            dd_1y=-10.0, vol_252d=25.0,
            liquidity_score=60.0, gap_freq=5.0, event_score=30.0,
        )
        assert 0 <= result["composite_risk_score"] <= 100
        assert result["risk_rating"] in ("very_low", "low", "medium", "high", "extreme")

    @pytest.mark.asyncio
    async def test_composite_high_risk(self, risk_engine: RiskEngine) -> None:
        result = risk_engine._compute_composite_score(
            dd_1y=-60.0, vol_252d=90.0,
            liquidity_score=10.0, gap_freq=30.0, event_score=70.0,
        )
        assert result["composite_risk_score"] >= 60
        assert result["risk_rating"] in ("high", "extreme")

    @pytest.mark.asyncio
    async def test_composite_low_risk(self, risk_engine: RiskEngine) -> None:
        result = risk_engine._compute_composite_score(
            dd_1y=-3.0, vol_252d=10.0,
            liquidity_score=95.0, gap_freq=1.0, event_score=10.0,
        )
        assert result["composite_risk_score"] <= 40


class TestComputeRiskMetrics:
    @pytest.mark.asyncio
    async def test_full_compute(
        self, risk_engine: RiskEngine, session: AsyncSession,
    ) -> None:
        session.add(Company(symbol="TEST", company_name="Test", isin="US1234567890", exchange="NYSE", status="active"))
        _seed_prices(session)
        await session.flush()

        result = await risk_engine.compute_risk_metrics("TEST", date(2024, 6, 1))
        assert "error" not in result
        assert result["symbol"] == "TEST"
        assert result.get("max_drawdown_1y") is not None
        assert result.get("volatility_252d") is not None
        assert result.get("liquidity_score") is not None
        assert result.get("gap_frequency_20d") is not None
        assert result.get("event_risk_score") is not None
        assert result.get("composite_risk_score") is not None
        assert result.get("risk_rating") is not None

    @pytest.mark.asyncio
    async def test_insufficient_data(
        self, risk_engine: RiskEngine, session: AsyncSession,
    ) -> None:
        _seed_prices(session, num_days=5)
        await session.flush()
        result = await risk_engine.compute_risk_metrics("TEST", date(2023, 1, 10))
        assert "error" in result


class TestStoreAndRetrieve:
    @pytest.mark.asyncio
    async def test_store_risk_metrics(
        self, risk_engine: RiskEngine, session: AsyncSession,
    ) -> None:
        session.add(Company(symbol="TEST", company_name="Test", isin="US1234567890", exchange="NYSE", status="active"))
        _seed_prices(session)
        await session.flush()

        result = await risk_engine.compute_and_store("TEST", date(2024, 6, 1))
        assert "id" in result

        retrieved = await risk_engine.get_risk_metrics("TEST", date(2024, 6, 1))
        assert retrieved is not None
        assert retrieved.symbol == "TEST"

    @pytest.mark.asyncio
    async def test_duplicate_store(
        self, risk_engine: RiskEngine, session: AsyncSession,
    ) -> None:
        session.add(Company(symbol="TEST", company_name="Test", isin="US1234567890", exchange="NYSE", status="active"))
        _seed_prices(session)
        await session.flush()

        await risk_engine.compute_and_store("TEST", date(2024, 6, 1))
        with pytest.raises(ValueError, match="already exist"):
            await risk_engine.compute_and_store("TEST", date(2024, 6, 1))

    @pytest.mark.asyncio
    async def test_historical_risk(
        self, risk_engine: RiskEngine, session: AsyncSession,
    ) -> None:
        session.add(Company(symbol="TEST", company_name="Test", isin="US1234567890", exchange="NYSE", status="active"))
        _seed_prices(session)
        await session.flush()

        await risk_engine.compute_and_store("TEST", date(2024, 6, 1))
        await risk_engine.compute_and_store("TEST", date(2024, 7, 1))

        rows, total = await risk_engine.get_historical_risk("TEST")
        assert total >= 2

    @pytest.mark.asyncio
    async def test_delete_risk(
        self, risk_engine: RiskEngine, session: AsyncSession,
    ) -> None:
        session.add(Company(symbol="TEST", company_name="Test", isin="US1234567890", exchange="NYSE", status="active"))
        _seed_prices(session)
        await session.flush()

        result = await risk_engine.compute_and_store("TEST", date(2024, 6, 1))
        assert await risk_engine.delete_risk_metrics(result["id"]) is True
        assert await risk_engine.delete_risk_metrics(result["id"]) is False


class TestPortfolioRisk:
    @pytest.mark.asyncio
    async def test_portfolio_risk_compute(
        self, risk_engine: RiskEngine, session: AsyncSession,
    ) -> None:
        session.add(Company(symbol="AAPL", company_name="Apple", isin="US0378331005", exchange="NASDAQ", status="active"))
        session.add(Company(symbol="MSFT", company_name="Microsoft", isin="US5949181045", exchange="NASDAQ", status="active"))
        _seed_prices(session, symbol="AAPL", base_close=150.0, trend=0.1, volatility=1.0)
        _seed_prices(session, symbol="MSFT", base_close=300.0, trend=0.08, volatility=1.2)
        await session.flush()

        holdings = {
            "AAPL": {"weight": 0.6},
            "MSFT": {"weight": 0.4},
        }
        result = await risk_engine.compute_portfolio_risk("port1", holdings, date(2024, 6, 1), store=False)
        assert "error" not in result
        assert result["num_positions"] == 2
        assert result.get("portfolio_volatility") is not None
        assert result.get("portfolio_var_95") is not None
        assert result.get("diversification_ratio") is not None
        assert result.get("concentration_risk") is not None
        assert result.get("risk_rating") is not None
        assert "holdings" in result
        assert len(result["holdings"]) == 2

    @pytest.mark.asyncio
    async def test_portfolio_risk_store(
        self, risk_engine: RiskEngine, session: AsyncSession,
    ) -> None:
        session.add(Company(symbol="AAPL", company_name="Apple", isin="US0378331005", exchange="NASDAQ", status="active"))
        session.add(Company(symbol="MSFT", company_name="Microsoft", isin="US5949181045", exchange="NASDAQ", status="active"))
        _seed_prices(session, symbol="AAPL", base_close=150.0, trend=0.1, volatility=1.0)
        _seed_prices(session, symbol="MSFT", base_close=300.0, trend=0.08, volatility=1.2)
        await session.flush()

        holdings = {"AAPL": {"weight": 0.6}, "MSFT": {"weight": 0.4}}
        result = await risk_engine.compute_portfolio_risk("port1", holdings, date(2024, 6, 1), store=True)
        assert result.get("id") is not None

        pr = await risk_engine.get_portfolio_risk("port1", date(2024, 6, 1))
        assert pr is not None
        assert pr.portfolio_id == "port1"

    @pytest.mark.asyncio
    async def test_portfolio_history(
        self, risk_engine: RiskEngine, session: AsyncSession,
    ) -> None:
        session.add(Company(symbol="AAPL", company_name="Apple", isin="US0378331005", exchange="NASDAQ", status="active"))
        _seed_prices(session, symbol="AAPL")
        await session.flush()

        holdings = {"AAPL": {"weight": 1.0}}
        await risk_engine.compute_portfolio_risk("port1", holdings, date(2024, 6, 1), store=True)
        await risk_engine.compute_portfolio_risk("port1", holdings, date(2024, 7, 1), store=True)

        rows, total = await risk_engine.get_portfolio_history("port1")
        assert total >= 2

    @pytest.mark.asyncio
    async def test_empty_holdings(self, risk_engine: RiskEngine) -> None:
        result = await risk_engine.compute_portfolio_risk("port1", {})
        assert "error" in result

    @pytest.mark.asyncio
    async def test_delete_portfolio_risk(
        self, risk_engine: RiskEngine, session: AsyncSession,
    ) -> None:
        session.add(Company(symbol="AAPL", company_name="Apple", isin="US0378331005", exchange="NASDAQ", status="active"))
        _seed_prices(session, symbol="AAPL")
        await session.flush()

        holdings = {"AAPL": {"weight": 1.0}}
        result = await risk_engine.compute_portfolio_risk("port1", holdings, date(2024, 6, 1), store=True)
        assert await risk_engine.delete_portfolio_risk(result["id"]) is True
        assert await risk_engine.delete_portfolio_risk(result["id"]) is False


class TestVaR:
    @pytest.mark.asyncio
    async def test_var_always_positive(self, risk_engine: RiskEngine) -> None:
        var95 = risk_engine._compute_var(0.0, 0.02, 0.95, 1_000_000)
        assert var95 >= 0

    @pytest.mark.asyncio
    async def test_var_99_greater_than_95(self, risk_engine: RiskEngine) -> None:
        var95 = risk_engine._compute_var(0.0, 0.02, 0.95, 1_000_000)
        var99 = risk_engine._compute_var(0.0, 0.02, 0.99, 1_000_000)
        assert var99 > var95

    @pytest.mark.asyncio
    async def test_expected_shortfall(self, risk_engine: RiskEngine) -> None:
        es = risk_engine._compute_expected_shortfall(0.02, 0.95, 1_000_000)
        assert es > 0

    @pytest.mark.asyncio
    async def test_correlation_matrix(self, risk_engine: RiskEngine) -> None:
        returns = {
            "A": [0.01, 0.02, 0.03, 0.04, 0.05],
            "B": [0.02, 0.04, 0.06, 0.08, 0.10],
        }
        matrix = risk_engine._compute_correlation_matrix(returns, ["A", "B"])
        assert abs(matrix[0][1] - 1.0) < 0.01

    @pytest.mark.asyncio
    async def test_average_correlation(self, risk_engine: RiskEngine) -> None:
        matrix = [[1.0, 0.5, 0.3], [0.5, 1.0, 0.7], [0.3, 0.7, 1.0]]
        avg = risk_engine._average_correlation(matrix)
        assert abs(avg - 0.5) < 0.01
