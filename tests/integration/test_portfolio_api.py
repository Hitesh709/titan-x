from datetime import date

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
class TestPortfolioAPI:
    async def _create_portfolio(self, client: AsyncClient, name: str = "Test Portfolio") -> dict:
        resp = await client.post(f"/api/v1/portfolio?name={name}", headers={"X-API-Key": API_KEY})
        assert resp.status_code == 201
        return resp.json()

    async def test_unauthorized(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/portfolio")
        assert resp.status_code == 401

    async def test_create_portfolio(self, client: AsyncClient) -> None:
        resp = await client.post("/api/v1/portfolio?name=MyPortfolio", headers={"X-API-Key": API_KEY})
        assert resp.status_code == 201
        assert resp.json()["name"] == "MyPortfolio"
        assert resp.json()["id"] is not None

    async def test_list_portfolios(self, client: AsyncClient) -> None:
        await self._create_portfolio(client, "A")
        await self._create_portfolio(client, "B")
        resp = await client.get("/api/v1/portfolio", headers={"X-API-Key": API_KEY})
        assert resp.status_code == 200
        assert resp.json()["total"] >= 2

    async def test_get_portfolio(self, client: AsyncClient) -> None:
        p = await self._create_portfolio(client)
        resp = await client.get(f"/api/v1/portfolio/{p['id']}", headers={"X-API-Key": API_KEY})
        assert resp.status_code == 200

    async def test_get_portfolio_not_found(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/portfolio/9999", headers={"X-API-Key": API_KEY})
        assert resp.status_code == 404

    async def test_delete_portfolio(self, client: AsyncClient) -> None:
        p = await self._create_portfolio(client)
        resp = await client.delete(f"/api/v1/portfolio/{p['id']}", headers={"X-API-Key": API_KEY})
        assert resp.status_code == 200

    async def test_add_buy_transaction(self, client: AsyncClient, db_session: AsyncSession) -> None:
        p = await self._create_portfolio(client)
        db_session.add(Company(symbol="AAPL", company_name="Apple", isin="US0378331005", exchange="NASDAQ", sector="Tech", status="active"))
        await db_session.flush()

        resp = await client.post(
            f"/api/v1/portfolio/{p['id']}/transactions?symbol=AAPL&transaction_type=buy&quantity=100&price=150.0&transaction_date=2024-06-01",
            headers={"X-API-Key": API_KEY},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["symbol"] == "AAPL"
        assert data["transaction_type"] == "buy"

    async def test_add_sell_transaction(self, client: AsyncClient, db_session: AsyncSession) -> None:
        p = await self._create_portfolio(client)
        await client.post(
            f"/api/v1/portfolio/{p['id']}/transactions?symbol=AAPL&transaction_type=buy&quantity=100&price=100.0&transaction_date=2024-01-01",
            headers={"X-API-Key": API_KEY},
        )
        resp = await client.post(
            f"/api/v1/portfolio/{p['id']}/transactions?symbol=AAPL&transaction_type=sell&quantity=50&price=150.0&transaction_date=2024-06-01",
            headers={"X-API-Key": API_KEY},
        )
        assert resp.status_code == 201
        assert resp.json()["realized_pnl"] == 2500.0

    async def test_sell_more_than_owned(self, client: AsyncClient) -> None:
        p = await self._create_portfolio(client)
        resp = await client.post(
            f"/api/v1/portfolio/{p['id']}/transactions?symbol=AAPL&transaction_type=sell&quantity=100&price=150.0",
            headers={"X-API-Key": API_KEY},
        )
        assert resp.status_code == 400

    async def test_list_transactions(self, client: AsyncClient, db_session: AsyncSession) -> None:
        p = await self._create_portfolio(client)
        await client.post(
            f"/api/v1/portfolio/{p['id']}/transactions?symbol=AAPL&transaction_type=buy&quantity=100&price=150.0&transaction_date=2024-06-01",
            headers={"X-API-Key": API_KEY},
        )
        resp = await client.get(f"/api/v1/portfolio/{p['id']}/transactions", headers={"X-API-Key": API_KEY})
        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    async def test_get_holdings(self, client: AsyncClient, db_session: AsyncSession) -> None:
        p = await self._create_portfolio(client)
        await client.post(
            f"/api/v1/portfolio/{p['id']}/transactions?symbol=AAPL&transaction_type=buy&quantity=100&price=150.0&transaction_date=2024-06-01",
            headers={"X-API-Key": API_KEY},
        )
        resp = await client.get(f"/api/v1/portfolio/{p['id']}/holdings", headers={"X-API-Key": API_KEY})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["holdings"]) == 1

    async def test_get_pnl(self, client: AsyncClient, db_session: AsyncSession) -> None:
        p = await self._create_portfolio(client)
        db_session.add(Company(symbol="AAPL", company_name="Apple", isin="US0378331005", exchange="NASDAQ", sector="Tech", status="active"))
        db_session.add(DailyPrice(symbol="AAPL", trade_date=date(2024, 6, 1), open=100, high=105, low=99, close=180, volume=1000000))
        await db_session.flush()
        await client.post(
            f"/api/v1/portfolio/{p['id']}/transactions?symbol=AAPL&transaction_type=buy&quantity=100&price=150.0&transaction_date=2024-01-01",
            headers={"X-API-Key": API_KEY},
        )
        await client.post(
            f"/api/v1/portfolio/{p['id']}/transactions?symbol=AAPL&transaction_type=sell&quantity=50&price=200.0&transaction_date=2024-06-01",
            headers={"X-API-Key": API_KEY},
        )
        resp = await client.get(f"/api/v1/portfolio/{p['id']}/pnl", headers={"X-API-Key": API_KEY})
        assert resp.status_code == 200
        data = resp.json()
        assert data["realized_pnl"] == 2500.0
        assert data["unrealized_pnl"] == 1500.0

    async def test_get_allocation(self, client: AsyncClient, db_session: AsyncSession) -> None:
        p = await self._create_portfolio(client)
        await client.post(
            f"/api/v1/portfolio/{p['id']}/transactions?symbol=AAPL&transaction_type=buy&quantity=100&price=100.0&transaction_date=2024-01-01",
            headers={"X-API-Key": API_KEY},
        )
        await client.post(
            f"/api/v1/portfolio/{p['id']}/transactions?symbol=GOOG&transaction_type=buy&quantity=100&price=100.0&transaction_date=2024-06-01",
            headers={"X-API-Key": API_KEY},
        )
        resp = await client.get(f"/api/v1/portfolio/{p['id']}/allocation", headers={"X-API-Key": API_KEY})
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    async def test_get_sector_allocation(self, client: AsyncClient, db_session: AsyncSession) -> None:
        p = await self._create_portfolio(client)
        db_session.add(Company(symbol="AAPL", company_name="Apple", isin="US0378331005", exchange="NASDAQ", sector="Tech", status="active"))
        db_session.add(Company(symbol="XOM", company_name="Exxon", isin="US30231G1022", exchange="NYSE", sector="Energy", status="active"))
        await db_session.flush()
        await client.post(
            f"/api/v1/portfolio/{p['id']}/transactions?symbol=AAPL&transaction_type=buy&quantity=100&price=100.0&transaction_date=2024-01-01",
            headers={"X-API-Key": API_KEY},
        )
        await client.post(
            f"/api/v1/portfolio/{p['id']}/transactions?symbol=XOM&transaction_type=buy&quantity=100&price=100.0&transaction_date=2024-06-01",
            headers={"X-API-Key": API_KEY},
        )
        resp = await client.get(f"/api/v1/portfolio/{p['id']}/sector-allocation", headers={"X-API-Key": API_KEY})
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    async def test_get_average_price(self, client: AsyncClient, db_session: AsyncSession) -> None:
        p = await self._create_portfolio(client)
        await client.post(
            f"/api/v1/portfolio/{p['id']}/transactions?symbol=AAPL&transaction_type=buy&quantity=100&price=150.0&transaction_date=2024-06-01",
            headers={"X-API-Key": API_KEY},
        )
        resp = await client.get(f"/api/v1/portfolio/{p['id']}/average-price/AAPL", headers={"X-API-Key": API_KEY})
        assert resp.status_code == 200
        assert resp.json()["average_price"] == 150.0

    async def test_get_summary(self, client: AsyncClient, db_session: AsyncSession) -> None:
        p = await self._create_portfolio(client)
        await client.post(
            f"/api/v1/portfolio/{p['id']}/transactions?symbol=AAPL&transaction_type=buy&quantity=100&price=150.0&transaction_date=2024-06-01",
            headers={"X-API-Key": API_KEY},
        )
        resp = await client.get(f"/api/v1/portfolio/{p['id']}/summary", headers={"X-API-Key": API_KEY})
        assert resp.status_code == 200
        data = resp.json()
        assert "holdings" in data
        assert "pnl" in data

    async def test_get_summary_not_found(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/portfolio/9999/summary", headers={"X-API-Key": API_KEY})
        assert resp.status_code == 404
