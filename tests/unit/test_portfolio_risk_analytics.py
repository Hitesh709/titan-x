from datetime import date, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from titan_x.db.base import Base
from titan_x.models.company import Company
from titan_x.models.price import DailyPrice
from titan_x.services.portfolio_engine import PortfolioEngine


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
async def pe(session: AsyncSession) -> PortfolioEngine:
    return PortfolioEngine(session)


@pytest_asyncio.fixture
async def portfolio(pe: PortfolioEngine) -> dict:
    return await pe.create_portfolio("Risk Test Portfolio")


def _add_price(session: AsyncSession, symbol: str, trade_date: date, close: float) -> None:
    session.add(DailyPrice(symbol=symbol, trade_date=trade_date, open=close, high=close, low=close, close=close, volume=1000000))


def _seed_prices(session: AsyncSession) -> None:
    base = date.today() - timedelta(days=400)
    for i in range(400):
        d = base + timedelta(days=i)
        _add_price(session, "SPY", d, 100 + i * 0.2 + (i % 10))
        _add_price(session, "AAPL", d, 150 + i * 0.15 + (i % 8))
        _add_price(session, "GOOG", d, 200 + i * 0.1 + (i % 6))
        _add_price(session, "MSFT", d, 250 + i * 0.12 + (i % 7))
    session.add(Company(symbol="AAPL", company_name="Apple", isin="US0378331005", exchange="NASDAQ", sector="Tech", status="active"))
    session.add(Company(symbol="GOOG", company_name="Google", isin="US02079K3059", exchange="NASDAQ", sector="Tech", status="active"))
    session.add(Company(symbol="MSFT", company_name="Microsoft", isin="US5949181045", exchange="NASDAQ", sector="Tech", status="active"))


class TestPortfolioBeta:
    @pytest.mark.asyncio
    async def test_beta_empty_portfolio(self, pe: PortfolioEngine, portfolio: dict) -> None:
        result = await pe.get_portfolio_beta(portfolio["id"])
        assert result["beta"] is None

    @pytest.mark.asyncio
    async def test_beta_no_benchmark_data(self, pe: PortfolioEngine, portfolio: dict, session: AsyncSession) -> None:
        session.add(Company(symbol="AAPL", company_name="Apple", isin="US0378331005", exchange="NASDAQ", sector="Tech", status="active"))
        await session.flush()
        await pe.record_transaction(portfolio["id"], "AAPL", "buy", 100, 150.0, date(2024, 1, 1))
        result = await pe.get_portfolio_beta(portfolio["id"])
        assert result["beta"] is None

    @pytest.mark.asyncio
    async def test_beta_with_data(self, pe: PortfolioEngine, portfolio: dict, session: AsyncSession) -> None:
        _seed_prices(session)
        await session.flush()
        await pe.record_transaction(portfolio["id"], "AAPL", "buy", 100, 150.0, date(2024, 1, 1))
        result = await pe.get_portfolio_beta(portfolio["id"])
        assert result["portfolio_beta"] is not None
        assert len(result["individual_betas"]) == 1
        assert result["individual_betas"][0]["symbol"] == "AAPL"


class TestCorrelationMatrix:
    @pytest.mark.asyncio
    async def test_single_holding(self, pe: PortfolioEngine, portfolio: dict, session: AsyncSession) -> None:
        await pe.record_transaction(portfolio["id"], "AAPL", "buy", 100, 150.0, date(2024, 1, 1))
        result = await pe.get_correlation_matrix(portfolio["id"])
        assert "message" in result

    @pytest.mark.asyncio
    async def test_two_holdings(self, pe: PortfolioEngine, portfolio: dict, session: AsyncSession) -> None:
        _seed_prices(session)
        await session.flush()
        await pe.record_transaction(portfolio["id"], "AAPL", "buy", 100, 150.0, date(2024, 1, 1))
        await pe.record_transaction(portfolio["id"], "GOOG", "buy", 100, 200.0, date(2024, 6, 1))
        result = await pe.get_correlation_matrix(portfolio["id"])
        assert len(result["symbols"]) == 2
        assert result["average_correlation"] is not None

    @pytest.mark.asyncio
    async def test_diagonal_is_one(self, pe: PortfolioEngine, portfolio: dict, session: AsyncSession) -> None:
        _seed_prices(session)
        await session.flush()
        await pe.record_transaction(portfolio["id"], "AAPL", "buy", 100, 150.0, date(2024, 1, 1))
        await pe.record_transaction(portfolio["id"], "GOOG", "buy", 100, 200.0, date(2024, 6, 1))
        result = await pe.get_correlation_matrix(portfolio["id"])
        assert result["matrix"][0][0] == 1.0
        assert result["matrix"][1][1] == 1.0


class TestDiversification:
    @pytest.mark.asyncio
    async def test_empty_portfolio(self, pe: PortfolioEngine, portfolio: dict) -> None:
        result = await pe.get_diversification_metrics(portfolio["id"])
        assert result["holding_count"] == 0

    @pytest.mark.asyncio
    async def test_single_holding(self, pe: PortfolioEngine, portfolio: dict, session: AsyncSession) -> None:
        _seed_prices(session)
        await session.flush()
        await pe.record_transaction(portfolio["id"], "AAPL", "buy", 100, 150.0, date(2024, 1, 1))
        result = await pe.get_diversification_metrics(portfolio["id"])
        assert result["holding_count"] == 1
        assert result["hhi"] == 1.0
        assert result["effective_n"] == 1.0

    @pytest.mark.asyncio
    async def test_equal_weight_improves_diversification(self, pe: PortfolioEngine, portfolio: dict, session: AsyncSession) -> None:
        _seed_prices(session)
        await session.flush()
        await pe.record_transaction(portfolio["id"], "AAPL", "buy", 100, 100.0, date(2024, 1, 1))
        await pe.record_transaction(portfolio["id"], "GOOG", "buy", 100, 100.0, date(2024, 6, 1))
        result = await pe.get_diversification_metrics(portfolio["id"])
        assert result["holding_count"] == 2
        assert result["hhi"] < 1.0
        assert result["effective_n"] > 1.0


class TestConcentrationRisk:
    @pytest.mark.asyncio
    async def test_empty_portfolio(self, pe: PortfolioEngine, portfolio: dict) -> None:
        result = await pe.get_concentration_risk(portfolio["id"])
        assert result["concentration_score"] == 0

    @pytest.mark.asyncio
    async def test_single_holding_max_concentration(self, pe: PortfolioEngine, portfolio: dict, session: AsyncSession) -> None:
        _seed_prices(session)
        await session.flush()
        await pe.record_transaction(portfolio["id"], "AAPL", "buy", 100, 150.0, date(2024, 1, 1))
        result = await pe.get_concentration_risk(portfolio["id"])
        assert result["concentration_score"] > 0
        assert result["top_1_pct"] == 100.0

    @pytest.mark.asyncio
    async def test_top_3_concentration(self, pe: PortfolioEngine, portfolio: dict, session: AsyncSession) -> None:
        _seed_prices(session)
        await session.flush()
        await pe.record_transaction(portfolio["id"], "AAPL", "buy", 100, 100.0, date(2024, 1, 1))
        await pe.record_transaction(portfolio["id"], "GOOG", "buy", 100, 100.0, date(2024, 6, 1))
        await pe.record_transaction(portfolio["id"], "MSFT", "buy", 100, 100.0, date(2024, 6, 1))
        result = await pe.get_concentration_risk(portfolio["id"])
        assert result["top_3_pct"] == 100.0
        assert result["holdings_above_5pct"] == 3


class TestSectorExposure:
    @pytest.mark.asyncio
    async def test_empty_portfolio(self, pe: PortfolioEngine, portfolio: dict) -> None:
        result = await pe.get_sector_exposure(portfolio["id"])
        assert result["sector_count"] == 0

    @pytest.mark.asyncio
    async def test_single_sector(self, pe: PortfolioEngine, portfolio: dict, session: AsyncSession) -> None:
        _seed_prices(session)
        await session.flush()
        await pe.record_transaction(portfolio["id"], "AAPL", "buy", 100, 150.0, date(2024, 1, 1))
        await pe.record_transaction(portfolio["id"], "GOOG", "buy", 100, 200.0, date(2024, 6, 1))
        result = await pe.get_sector_exposure(portfolio["id"])
        assert result["sector_count"] == 1
        assert result["sectors"][0]["sector"] == "Tech"

    @pytest.mark.asyncio
    async def test_multi_sector(self, pe: PortfolioEngine, portfolio: dict, session: AsyncSession) -> None:
        _seed_prices(session)
        session.add(Company(symbol="XOM", company_name="Exxon", isin="US30231G1022", exchange="NYSE", sector="Energy", status="active"))
        await session.flush()
        await pe.record_transaction(portfolio["id"], "AAPL", "buy", 100, 100.0, date(2024, 1, 1))
        await pe.record_transaction(portfolio["id"], "XOM", "buy", 100, 100.0, date(2024, 6, 1))
        result = await pe.get_sector_exposure(portfolio["id"])
        assert result["sector_count"] == 2


class TestExpectedDrawdown:
    @pytest.mark.asyncio
    async def test_empty_portfolio(self, pe: PortfolioEngine, portfolio: dict) -> None:
        result = await pe.get_expected_drawdown(portfolio["id"])
        assert result["expected_drawdown_pct"] == 0

    @pytest.mark.asyncio
    async def test_with_data(self, pe: PortfolioEngine, portfolio: dict, session: AsyncSession) -> None:
        _seed_prices(session)
        await session.flush()
        await pe.record_transaction(portfolio["id"], "AAPL", "buy", 100, 150.0, date(2024, 1, 1))
        result = await pe.get_expected_drawdown(portfolio["id"])
        assert result["expected_drawdown_pct"] >= 0
        assert result["portfolio_volatility_pct"] >= 0


class TestRiskScore:
    @pytest.mark.asyncio
    async def test_empty_portfolio(self, pe: PortfolioEngine, portfolio: dict) -> None:
        result = await pe.get_portfolio_risk_score(portfolio["id"])
        assert result["risk_score"] == 0

    @pytest.mark.asyncio
    async def test_with_data(self, pe: PortfolioEngine, portfolio: dict, session: AsyncSession) -> None:
        _seed_prices(session)
        await session.flush()
        await pe.record_transaction(portfolio["id"], "AAPL", "buy", 100, 150.0, date(2024, 1, 1))
        result = await pe.get_portfolio_risk_score(portfolio["id"])
        assert result["risk_score"] >= 0
        assert result["risk_rating"] in ("very_low", "low", "medium", "high", "extreme")
        assert "components" in result


class TestRiskReport:
    @pytest.mark.asyncio
    async def test_no_portfolio(self, pe: PortfolioEngine) -> None:
        result = await pe.get_portfolio_risk_report(9999)
        assert "error" in result

    @pytest.mark.asyncio
    async def test_no_holdings(self, pe: PortfolioEngine, portfolio: dict) -> None:
        result = await pe.get_portfolio_risk_report(portfolio["id"])
        assert "error" in result

    @pytest.mark.asyncio
    async def test_full_report(self, pe: PortfolioEngine, portfolio: dict, session: AsyncSession) -> None:
        _seed_prices(session)
        await session.flush()
        await pe.record_transaction(portfolio["id"], "AAPL", "buy", 100, 150.0, date(2024, 1, 1))
        await pe.record_transaction(portfolio["id"], "GOOG", "buy", 100, 200.0, date(2024, 6, 1))
        result = await pe.get_portfolio_risk_report(portfolio["id"])
        assert "beta" in result
        assert "correlation" in result
        assert "diversification" in result
        assert "concentration_risk" in result
        assert "sector_exposure" in result
        assert "expected_drawdown" in result
        assert "risk_score" in result
        assert result["portfolio_name"] == "Risk Test Portfolio"
