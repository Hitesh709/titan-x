from datetime import date

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from titan_x.api.v1 import v1_router
from titan_x.db.base import Base
from titan_x.main import app
from titan_x.models.company import Company
from titan_x.models.price import DailyPrice
from titan_x.models.technical import TechnicalIndicator
from titan_x.models.risk import RiskMetrics
from titan_x.services.explainability_engine import ExplainabilityEngine

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

    async def get_ee_override():
        return ExplainabilityEngine(db_session)

    from titan_x.api.dependencies import request_session, get_explainability_engine
    app.dependency_overrides[request_session] = get_session_override
    app.dependency_overrides[get_explainability_engine] = get_ee_override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
class TestExplainabilityAPI:
    async def _seed_data(self, db_session: AsyncSession, symbol: str = "TEST") -> None:
        db_session.add(Company(symbol=symbol, company_name="TestCorp", isin="US1234567890", exchange="NYSE", sector="Tech", status="active"))
        db_session.add(DailyPrice(symbol=symbol, trade_date=date(2024, 6, 1), open=100, high=105, low=99, close=102, volume=1000000))
        db_session.add(TechnicalIndicator(symbol=symbol, trade_date=date(2024, 6, 1), indicator="rsi", params_hash="a", value=65))
        db_session.add(TechnicalIndicator(symbol=symbol, trade_date=date(2024, 6, 1), indicator="sma_20", params_hash="a", value=105))
        db_session.add(TechnicalIndicator(symbol=symbol, trade_date=date(2024, 6, 1), indicator="sma_50", params_hash="a", value=95))
        db_session.add(TechnicalIndicator(symbol=symbol, trade_date=date(2024, 6, 1), indicator="ema_12", params_hash="a", value=102))
        db_session.add(RiskMetrics(symbol=symbol, as_of_date=date(2024, 6, 1), composite_risk_score=25, volatility_252d=22, liquidity_score=80, max_drawdown_1y=10, event_risk_score=3))
        await db_session.flush()

    async def test_create_explainability_unauthorized(self, client: AsyncClient) -> None:
        resp = await client.post("/api/v1/explainability/AAPL")
        assert resp.status_code == 401

    async def test_create_explainability_not_found(self, client: AsyncClient) -> None:
        resp = await client.post("/api/v1/explainability/NONEXIST", headers={"X-API-Key": API_KEY})
        assert resp.status_code == 404

    async def test_create_explainability_success(self, client: AsyncClient, db_session: AsyncSession) -> None:
        await self._seed_data(db_session)
        resp = await client.post("/api/v1/explainability/TEST", headers={"X-API-Key": API_KEY})
        assert resp.status_code == 200
        data = resp.json()
        assert data["symbol"] == "TEST"
        assert "why_buy" in data
        assert "why_not_buy" in data
        assert "strengths" in data
        assert "weaknesses" in data
        assert "risk_factors" in data
        assert "historical_evidence" in data
        assert data["overall_signal"] is not None

    async def test_create_and_store(self, client: AsyncClient, db_session: AsyncSession) -> None:
        await self._seed_data(db_session)
        resp = await client.post("/api/v1/explainability/TEST?store=true", headers={"X-API-Key": API_KEY})
        assert resp.status_code == 200
        assert resp.json()["id"] is not None

    async def test_get_stored(self, client: AsyncClient, db_session: AsyncSession) -> None:
        await self._seed_data(db_session)
        await client.post("/api/v1/explainability/TEST?store=true", headers={"X-API-Key": API_KEY})
        resp = await client.get("/api/v1/explainability/TEST", headers={"X-API-Key": API_KEY})
        assert resp.status_code == 200
        assert resp.json()["symbol"] == "TEST"

    async def test_get_stored_not_found(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/explainability/NONEXIST", headers={"X-API-Key": API_KEY})
        assert resp.status_code == 404

    async def test_list_explainability(self, client: AsyncClient, db_session: AsyncSession) -> None:
        await self._seed_data(db_session)
        await client.post("/api/v1/explainability/TEST?store=true", headers={"X-API-Key": API_KEY})
        resp = await client.get("/api/v1/explainability?symbol=TEST", headers={"X-API-Key": API_KEY})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        assert len(data["items"]) > 0

    async def test_delete_explainability(self, client: AsyncClient, db_session: AsyncSession) -> None:
        await self._seed_data(db_session)
        create_resp = await client.post("/api/v1/explainability/TEST?store=true", headers={"X-API-Key": API_KEY})
        analysis_id = create_resp.json()["id"]

        resp = await client.delete(f"/api/v1/explainability/{analysis_id}", headers={"X-API-Key": API_KEY})
        assert resp.status_code == 200

        resp = await client.delete(f"/api/v1/explainability/{analysis_id}", headers={"X-API-Key": API_KEY})
        assert resp.status_code == 404
