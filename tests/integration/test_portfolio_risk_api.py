from datetime import date, timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from titan_x.db.base import Base
from titan_x.main import app
from titan_x.models.company import Company
from titan_x.models.price import DailyPrice
from titan_x.services.portfolio_engine import PortfolioEngine

API_KEY = "test-key-123456789012345678901234567890"


def _add_price(session: AsyncSession, symbol: str, trade_date: date, close: float) -> None:
    session.add(DailyPrice(symbol=symbol, trade_date=trade_date, open=close, high=close, low=close, close=close, volume=1000000))


def _seed_prices(session: AsyncSession) -> None:
    base = date.today() - timedelta(days=400)
    for i in range(400):
        d = base + timedelta(days=i)
        _add_price(session, "SPY", d, 100 + i * 0.2 + (i % 10))
        _add_price(session, "AAPL", d, 150 + i * 0.15 + (i % 8))
        _add_price(session, "GOOG", d, 200 + i * 0.1 + (i % 6))
    session.add(Company(symbol="AAPL", company_name="Apple", isin="US0378331005", exchange="NASDAQ", sector="Tech", status="active"))
    session.add(Company(symbol="GOOG", company_name="Google", isin="US02079K3059", exchange="NASDAQ", sector="Tech", status="active"))


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as sess:
        yield sess
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncClient:
    app.dependency_overrides.clear()

    async def get_session_override():
        yield db_session

    async def get_pe_override():
        return PortfolioEngine(db_session)

    from titan_x.api.dependencies import request_session, get_portfolio_engine
    app.dependency_overrides[request_session] = get_session_override
    app.dependency_overrides[get_portfolio_engine] = get_pe_override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
class TestPortfolioRiskAPI:
    async def _create_and_seed(self, client: AsyncClient, db_session: AsyncSession) -> int:
        _seed_prices(db_session)
        await db_session.flush()
        resp = await client.post("/api/v1/portfolio?name=RiskTest", headers={"X-API-Key": API_KEY})
        pid = resp.json()["id"]
        await client.post(
            f"/api/v1/portfolio/{pid}/transactions?symbol=AAPL&transaction_type=buy&quantity=100&price=150.0&transaction_date=2024-01-01",
            headers={"X-API-Key": API_KEY},
        )
        await client.post(
            f"/api/v1/portfolio/{pid}/transactions?symbol=GOOG&transaction_type=buy&quantity=100&price=200.0&transaction_date=2024-06-01",
            headers={"X-API-Key": API_KEY},
        )
        return pid

    async def test_beta(self, client: AsyncClient, db_session: AsyncSession) -> None:
        pid = await self._create_and_seed(client, db_session)
        resp = await client.get(f"/api/v1/portfolio/{pid}/beta", headers={"X-API-Key": API_KEY})
        assert resp.status_code == 200
        data = resp.json()
        assert "portfolio_beta" in data
        assert data["benchmark_symbol"] == "SPY"

    async def test_beta_custom_benchmark(self, client: AsyncClient, db_session: AsyncSession) -> None:
        pid = await self._create_and_seed(client, db_session)
        resp = await client.get(f"/api/v1/portfolio/{pid}/beta?benchmark=SPY&days=100", headers={"X-API-Key": API_KEY})
        assert resp.status_code == 200

    async def test_correlation(self, client: AsyncClient, db_session: AsyncSession) -> None:
        pid = await self._create_and_seed(client, db_session)
        resp = await client.get(f"/api/v1/portfolio/{pid}/correlation", headers={"X-API-Key": API_KEY})
        assert resp.status_code == 200
        data = resp.json()
        assert "average_correlation" in data
        assert len(data["symbols"]) == 2

    async def test_diversification(self, client: AsyncClient, db_session: AsyncSession) -> None:
        pid = await self._create_and_seed(client, db_session)
        resp = await client.get(f"/api/v1/portfolio/{pid}/diversification", headers={"X-API-Key": API_KEY})
        assert resp.status_code == 200
        data = resp.json()
        assert "diversification_score" in data
        assert data["holding_count"] == 2

    async def test_concentration(self, client: AsyncClient, db_session: AsyncSession) -> None:
        pid = await self._create_and_seed(client, db_session)
        resp = await client.get(f"/api/v1/portfolio/{pid}/concentration", headers={"X-API-Key": API_KEY})
        assert resp.status_code == 200
        data = resp.json()
        assert "concentration_score" in data
        assert data["top_1_pct"] > 0

    async def test_sector_exposure(self, client: AsyncClient, db_session: AsyncSession) -> None:
        pid = await self._create_and_seed(client, db_session)
        resp = await client.get(f"/api/v1/portfolio/{pid}/sector-exposure", headers={"X-API-Key": API_KEY})
        assert resp.status_code == 200
        data = resp.json()
        assert "sector_count" in data
        assert data["sectors"][0]["sector"] == "Tech"

    async def test_drawdown(self, client: AsyncClient, db_session: AsyncSession) -> None:
        pid = await self._create_and_seed(client, db_session)
        resp = await client.get(f"/api/v1/portfolio/{pid}/drawdown", headers={"X-API-Key": API_KEY})
        assert resp.status_code == 200
        data = resp.json()
        assert "expected_drawdown_pct" in data

    async def test_risk_score(self, client: AsyncClient, db_session: AsyncSession) -> None:
        pid = await self._create_and_seed(client, db_session)
        resp = await client.get(f"/api/v1/portfolio/{pid}/risk-score", headers={"X-API-Key": API_KEY})
        assert resp.status_code == 200
        data = resp.json()
        assert "risk_score" in data
        assert "risk_rating" in data

    async def test_risk_report(self, client: AsyncClient, db_session: AsyncSession) -> None:
        pid = await self._create_and_seed(client, db_session)
        resp = await client.get(f"/api/v1/portfolio/{pid}/risk-report", headers={"X-API-Key": API_KEY})
        assert resp.status_code == 200
        data = resp.json()
        assert "beta" in data
        assert "correlation" in data
        assert "diversification" in data
        assert "concentration_risk" in data
        assert "sector_exposure" in data
        assert "expected_drawdown" in data
        assert "risk_score" in data

    async def test_risk_report_not_found(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/portfolio/9999/risk-report", headers={"X-API-Key": API_KEY})
        assert resp.status_code == 404
