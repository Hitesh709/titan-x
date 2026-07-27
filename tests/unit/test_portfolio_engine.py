from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from titan_x.db.base import Base
from titan_x.models.company import Company
from titan_x.models.portfolio import Portfolio, PortfolioHolding, PortfolioTransaction
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
    return await pe.create_portfolio("Test Portfolio")


class TestCreatePortfolio:
    @pytest.mark.asyncio
    async def test_create_minimal(self, pe: PortfolioEngine) -> None:
        result = await pe.create_portfolio("My Portfolio")
        assert result["name"] == "My Portfolio"
        assert result["id"] is not None

    @pytest.mark.asyncio
    async def test_create_with_description(self, pe: PortfolioEngine) -> None:
        result = await pe.create_portfolio("Tech", description="Tech stocks")
        assert result["description"] == "Tech stocks"

    @pytest.mark.asyncio
    async def test_list_portfolios(self, pe: PortfolioEngine) -> None:
        await pe.create_portfolio("A")
        await pe.create_portfolio("B")
        rows, total = await pe.list_portfolios()
        assert total >= 2

    @pytest.mark.asyncio
    async def test_get_portfolio(self, pe: PortfolioEngine, portfolio: dict) -> None:
        p = await pe.get_portfolio(portfolio["id"])
        assert p is not None
        assert p.name == "Test Portfolio"

    @pytest.mark.asyncio
    async def test_get_portfolio_not_found(self, pe: PortfolioEngine) -> None:
        assert await pe.get_portfolio(9999) is None

    @pytest.mark.asyncio
    async def test_delete_portfolio(self, pe: PortfolioEngine, portfolio: dict) -> None:
        assert await pe.delete_portfolio(portfolio["id"]) is True
        assert await pe.delete_portfolio(portfolio["id"]) is False


class TestRecordTransaction:
    @pytest.mark.asyncio
    async def test_buy_creates_holding(self, pe: PortfolioEngine, portfolio: dict) -> None:
        txn = await pe.record_transaction(portfolio["id"], "AAPL", "buy", 100, 150.0, date(2024, 6, 1))
        assert txn["transaction_type"] == "buy"
        assert txn["symbol"] == "AAPL"
        assert txn["realized_pnl"] is None

        avg = await pe.get_average_price(portfolio["id"], "AAPL")
        assert avg["quantity"] == 100
        assert avg["average_price"] == 150.0

    @pytest.mark.asyncio
    async def test_multiple_buys_average_price(self, pe: PortfolioEngine, portfolio: dict) -> None:
        await pe.record_transaction(portfolio["id"], "AAPL", "buy", 100, 100.0, date(2024, 1, 1))
        await pe.record_transaction(portfolio["id"], "AAPL", "buy", 100, 200.0, date(2024, 6, 1))
        avg = await pe.get_average_price(portfolio["id"], "AAPL")
        assert avg["quantity"] == 200
        assert avg["average_price"] == 150.0

    @pytest.mark.asyncio
    async def test_sell_reduces_quantity(self, pe: PortfolioEngine, portfolio: dict) -> None:
        await pe.record_transaction(portfolio["id"], "AAPL", "buy", 100, 100.0, date(2024, 1, 1))
        txn = await pe.record_transaction(portfolio["id"], "AAPL", "sell", 50, 150.0, date(2024, 6, 1))
        assert txn["realized_pnl"] == 2500.0
        avg = await pe.get_average_price(portfolio["id"], "AAPL")
        assert avg["quantity"] == 50
        assert avg["average_price"] == 100.0

    @pytest.mark.asyncio
    async def test_sell_all_clears_holding(self, pe: PortfolioEngine, portfolio: dict) -> None:
        await pe.record_transaction(portfolio["id"], "AAPL", "buy", 100, 100.0, date(2024, 1, 1))
        await pe.record_transaction(portfolio["id"], "AAPL", "sell", 100, 150.0, date(2024, 6, 1))
        avg = await pe.get_average_price(portfolio["id"], "AAPL")
        assert avg["quantity"] == 0
        assert avg["average_price"] is None

    @pytest.mark.asyncio
    async def test_sell_more_than_owned(self, pe: PortfolioEngine, portfolio: dict) -> None:
        await pe.record_transaction(portfolio["id"], "AAPL", "buy", 50, 100.0, date(2024, 1, 1))
        with pytest.raises(ValueError, match="Not enough shares"):
            await pe.record_transaction(portfolio["id"], "AAPL", "sell", 100, 150.0, date(2024, 6, 1))

    @pytest.mark.asyncio
    async def test_invalid_transaction_type(self, pe: PortfolioEngine, portfolio: dict) -> None:
        with pytest.raises(ValueError, match="must be 'buy' or 'sell'"):
            await pe.record_transaction(portfolio["id"], "AAPL", "invalid", 100, 100.0)

    @pytest.mark.asyncio
    async def test_negative_quantity(self, pe: PortfolioEngine, portfolio: dict) -> None:
        with pytest.raises(ValueError, match="quantity must be positive"):
            await pe.record_transaction(portfolio["id"], "AAPL", "buy", -1, 100.0)

    @pytest.mark.asyncio
    async def test_negative_price(self, pe: PortfolioEngine, portfolio: dict) -> None:
        with pytest.raises(ValueError, match="price must be positive"):
            await pe.record_transaction(portfolio["id"], "AAPL", "buy", 100, -1.0)

    @pytest.mark.asyncio
    async def test_nonexistent_portfolio(self, pe: PortfolioEngine) -> None:
        with pytest.raises(ValueError, match="Portfolio 9999 not found"):
            await pe.record_transaction(9999, "AAPL", "buy", 100, 100.0)

    @pytest.mark.asyncio
    async def test_default_as_of_date(self, pe: PortfolioEngine, portfolio: dict) -> None:
        txn = await pe.record_transaction(portfolio["id"], "AAPL", "buy", 100, 150.0)
        assert txn["transaction_date"] == date.today().isoformat()


class TestGetTransactions:
    @pytest.mark.asyncio
    async def test_list_transactions(self, pe: PortfolioEngine, portfolio: dict) -> None:
        await pe.record_transaction(portfolio["id"], "AAPL", "buy", 100, 100.0, date(2024, 1, 1))
        await pe.record_transaction(portfolio["id"], "GOOG", "buy", 50, 200.0, date(2024, 6, 1))
        rows, total = await pe.get_transactions(portfolio["id"])
        assert total == 2

    @pytest.mark.asyncio
    async def test_filter_by_symbol(self, pe: PortfolioEngine, portfolio: dict) -> None:
        await pe.record_transaction(portfolio["id"], "AAPL", "buy", 100, 100.0, date(2024, 1, 1))
        await pe.record_transaction(portfolio["id"], "GOOG", "buy", 50, 200.0, date(2024, 6, 1))
        rows, total = await pe.get_transactions(portfolio["id"], symbol="AAPL")
        assert total == 1

    @pytest.mark.asyncio
    async def test_filter_by_type(self, pe: PortfolioEngine, portfolio: dict) -> None:
        await pe.record_transaction(portfolio["id"], "AAPL", "buy", 100, 100.0, date(2024, 1, 1))
        await pe.record_transaction(portfolio["id"], "AAPL", "sell", 50, 150.0, date(2024, 6, 1))
        rows, total = await pe.get_transactions(portfolio["id"], transaction_type="sell")
        assert total == 1


class TestPnL:
    @pytest.mark.asyncio
    async def test_realized_pnl(self, pe: PortfolioEngine, portfolio: dict) -> None:
        await pe.record_transaction(portfolio["id"], "AAPL", "buy", 100, 100.0, date(2024, 1, 1))
        await pe.record_transaction(portfolio["id"], "AAPL", "sell", 50, 150.0, date(2024, 6, 1))
        pnl = await pe.get_pnl(portfolio["id"])
        assert pnl["realized_pnl"] == 2500.0

    @pytest.mark.asyncio
    async def test_no_transactions(self, pe: PortfolioEngine, portfolio: dict) -> None:
        pnl = await pe.get_pnl(portfolio["id"])
        assert pnl["realized_pnl"] == 0
        assert pnl["total_pnl"] == 0

    @pytest.mark.asyncio
    async def test_unrealized_pnl_with_price(self, pe: PortfolioEngine, portfolio: dict, session: AsyncSession) -> None:
        session.add(Company(symbol="AAPL", company_name="Apple", isin="US0378331005", exchange="NASDAQ", sector="Tech", status="active"))
        session.add(DailyPrice(symbol="AAPL", trade_date=date(2024, 6, 1), open=100, high=105, low=99, close=180, volume=1000000))
        await session.flush()

        await pe.record_transaction(portfolio["id"], "AAPL", "buy", 100, 150.0, date(2024, 1, 1))
        pnl = await pe.get_pnl(portfolio["id"])
        assert pnl["unrealized_pnl"] == 3000.0
        assert pnl["total_pnl"] == 3000.0


class TestHoldings:
    @pytest.mark.asyncio
    async def test_get_holdings(self, pe: PortfolioEngine, portfolio: dict) -> None:
        await pe.record_transaction(portfolio["id"], "AAPL", "buy", 100, 150.0, date(2024, 1, 1))
        holdings, summary = await pe.get_holdings(portfolio["id"])
        assert len(holdings) == 1
        assert holdings[0]["symbol"] == "AAPL"
        assert holdings[0]["quantity"] == 100

    @pytest.mark.asyncio
    async def test_holdings_multiple_symbols(self, pe: PortfolioEngine, portfolio: dict) -> None:
        await pe.record_transaction(portfolio["id"], "AAPL", "buy", 100, 150.0, date(2024, 1, 1))
        await pe.record_transaction(portfolio["id"], "GOOG", "buy", 50, 200.0, date(2024, 6, 1))
        holdings, summary = await pe.get_holdings(portfolio["id"])
        assert len(holdings) == 2

    @pytest.mark.asyncio
    async def test_empty_holdings(self, pe: PortfolioEngine, portfolio: dict) -> None:
        holdings, summary = await pe.get_holdings(portfolio["id"])
        assert len(holdings) == 0

    @pytest.mark.asyncio
    async def test_sell_removes_from_holdings(self, pe: PortfolioEngine, portfolio: dict) -> None:
        await pe.record_transaction(portfolio["id"], "AAPL", "buy", 100, 100.0, date(2024, 1, 1))
        holdings, _ = await pe.get_holdings(portfolio["id"])
        assert len(holdings) == 1
        await pe.record_transaction(portfolio["id"], "AAPL", "sell", 100, 150.0, date(2024, 6, 1))
        holdings, _ = await pe.get_holdings(portfolio["id"])
        assert len(holdings) == 0


class TestAllocation:
    @pytest.mark.asyncio
    async def test_portfolio_allocation(self, pe: PortfolioEngine, portfolio: dict, session: AsyncSession) -> None:
        session.add(DailyPrice(symbol="AAPL", trade_date=date(2024, 6, 1), open=100, high=105, low=99, close=100, volume=1000000))
        session.add(DailyPrice(symbol="GOOG", trade_date=date(2024, 6, 1), open=100, high=105, low=99, close=100, volume=1000000))
        await session.flush()
        await pe.record_transaction(portfolio["id"], "AAPL", "buy", 100, 100.0, date(2024, 1, 1))
        await pe.record_transaction(portfolio["id"], "GOOG", "buy", 100, 100.0, date(2024, 6, 1))
        alloc = await pe.get_portfolio_allocation(portfolio["id"])
        assert len(alloc) == 2
        assert alloc[0]["allocation_pct"] == 50.0
        assert alloc[1]["allocation_pct"] == 50.0

    @pytest.mark.asyncio
    async def test_sector_allocation(self, pe: PortfolioEngine, portfolio: dict, session: AsyncSession) -> None:
        session.add(Company(symbol="AAPL", company_name="Apple", isin="US0378331005", exchange="NASDAQ", sector="Tech", status="active"))
        session.add(Company(symbol="XOM", company_name="Exxon", isin="US30231G1022", exchange="NYSE", sector="Energy", status="active"))
        await session.flush()

        await pe.record_transaction(portfolio["id"], "AAPL", "buy", 100, 100.0, date(2024, 1, 1))
        await pe.record_transaction(portfolio["id"], "XOM", "buy", 100, 100.0, date(2024, 6, 1))
        alloc = await pe.get_sector_allocation(portfolio["id"])
        assert len(alloc) == 2
        sectors = {a["sector"] for a in alloc}
        assert sectors == {"Tech", "Energy"}

    @pytest.mark.asyncio
    async def test_sector_allocation_empty(self, pe: PortfolioEngine, portfolio: dict) -> None:
        alloc = await pe.get_sector_allocation(portfolio["id"])
        assert alloc == []


class TestAveragePrice:
    @pytest.mark.asyncio
    async def test_no_holding(self, pe: PortfolioEngine, portfolio: dict) -> None:
        avg = await pe.get_average_price(portfolio["id"], "AAPL")
        assert avg["quantity"] == 0
        assert avg["average_price"] is None

    @pytest.mark.asyncio
    async def test_after_multiple_buys(self, pe: PortfolioEngine, portfolio: dict) -> None:
        await pe.record_transaction(portfolio["id"], "AAPL", "buy", 100, 100.0, date(2024, 1, 1))
        await pe.record_transaction(portfolio["id"], "AAPL", "buy", 100, 200.0, date(2024, 6, 1))
        avg = await pe.get_average_price(portfolio["id"], "AAPL")
        assert avg["average_price"] == 150.0
        assert avg["cost_basis"] == 30000.0


class TestPortfolioSummary:
    @pytest.mark.asyncio
    async def test_summary_not_found(self, pe: PortfolioEngine) -> None:
        result = await pe.get_portfolio_summary(9999)
        assert result == {}

    @pytest.mark.asyncio
    async def test_summary_with_data(self, pe: PortfolioEngine, portfolio: dict) -> None:
        await pe.record_transaction(portfolio["id"], "AAPL", "buy", 100, 100.0, date(2024, 1, 1))
        summary = await pe.get_portfolio_summary(portfolio["id"])
        assert summary["portfolio"]["name"] == "Test Portfolio"
        assert len(summary["holdings"]) == 1
        assert summary["pnl"]["total_pnl"] == 0
        assert len(summary["allocation"]) == 1
