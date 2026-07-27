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
from titan_x.models.fundamental import FundamentalMetric
from titan_x.models.risk import RiskMetrics
from titan_x.models.historical_similarity import SimilarityAnalysis
from titan_x.models.chart_pattern import ChartPattern
from titan_x.models.sector import SectorPerformance
from titan_x.models.market_breadth import MarketBreadth
from titan_x.models.prediction import Prediction

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

    from titan_x.api.dependencies import request_session
    app.dependency_overrides[request_session] = get_session_override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def seed_data(db_session: AsyncSession) -> None:
    db_session.add(Company(symbol="TEST", company_name="TestCorp", isin="US1234567890", exchange="NYSE", sector="Tech", status="active"))
    db_session.add(DailyPrice(symbol="TEST", trade_date=date(2024, 6, 1), open=100, high=105, low=99, close=102, volume=1000000))
    db_session.add(TechnicalIndicator(symbol="TEST", trade_date=date(2024, 6, 1), indicator="rsi", params_hash="a", value=60))
    db_session.add(TechnicalIndicator(symbol="TEST", trade_date=date(2024, 6, 1), indicator="sma_20", params_hash="a", value=100))
    db_session.add(TechnicalIndicator(symbol="TEST", trade_date=date(2024, 6, 1), indicator="sma_50", params_hash="a", value=95))
    db_session.add(RiskMetrics(symbol="TEST", as_of_date=date(2024, 6, 1), composite_risk_score=25, volatility_252d=22, max_drawdown_1y=12, event_risk_score=3, liquidity_score=80))

    sa = SimilarityAnalysis(
        symbol="TEST", query_start_date=date(2024, 1, 1), query_end_date=date(2024, 6, 1),
        window_days=20, lookback_days=365, max_matches=50, min_similarity=60,
        avg_return_5d=2.0, avg_return_10d=4.0, avg_return_20d=6.0, avg_return_60d=10.0,
        avg_similarity=70.0, optimal_holding_period=10,
    )
    db_session.add(sa)
    db_session.add(SectorPerformance(sector="Tech", as_of_date=date(2024, 6, 1), period_label="1M", momentum_score=12.0, relative_strength=55.0))
    db_session.add(MarketBreadth(trade_date=date(2024, 6, 1), advancing=300, declining=200, unchanged=50, total_stocks=550, advancing_volume=100000, declining_volume=80000, unchanged_volume=5000, total_volume=185000, new_highs=30, new_lows=10, index_strength_score=65))
    await db_session.flush()


@pytest.mark.asyncio
async def test_create_prediction_no_auth(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/predictions/TEST")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_create_prediction_not_found(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/predictions/NONEXIST", headers={"X-API-Key": API_KEY})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_prediction_success(client: AsyncClient, seed_data: None) -> None:
    resp = await client.post("/api/v1/predictions/TEST", headers={"X-API-Key": API_KEY})
    assert resp.status_code == 200
    data = resp.json()
    assert data["symbol"] == "TEST"
    assert data["overall_signal"] is not None
    assert data["overall_confidence"] >= 20
    assert data["probability_5d"] is not None
    assert data["expected_return_10d"] is not None
    assert data["expected_drawdown_15d"] is not None
    assert data["confidence_20d"] is not None
    assert data["signal_30d"] is not None
    assert data["holding_period"] is not None
    assert data["explanation"] is not None


@pytest.mark.asyncio
async def test_create_prediction_with_specific_date(client: AsyncClient, seed_data: None) -> None:
    resp = await client.post("/api/v1/predictions/TEST", params={"as_of_date": "2024-06-10"}, headers={"X-API-Key": API_KEY})
    assert resp.status_code == 200
    data = resp.json()
    assert data["symbol"] == "TEST"


@pytest.mark.asyncio
async def test_create_prediction_twice_conflict(client: AsyncClient, seed_data: None) -> None:
    resp = await client.post("/api/v1/predictions/TEST", headers={"X-API-Key": API_KEY})
    assert resp.status_code == 200
    resp2 = await client.post("/api/v1/predictions/TEST", headers={"X-API-Key": API_KEY})
    assert resp2.status_code == 409


@pytest.mark.asyncio
async def test_get_prediction_not_found(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/predictions/NONEXIST", headers={"X-API-Key": API_KEY})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_prediction_found(client: AsyncClient, seed_data: None) -> None:
    await client.post("/api/v1/predictions/TEST", headers={"X-API-Key": API_KEY})
    resp = await client.get("/api/v1/predictions/TEST", headers={"X-API-Key": API_KEY})
    assert resp.status_code == 200
    data = resp.json()
    assert data["symbol"] == "TEST"


@pytest.mark.asyncio
async def test_list_predictions(client: AsyncClient, seed_data: None) -> None:
    await client.post("/api/v1/predictions/TEST", headers={"X-API-Key": API_KEY})
    resp = await client.get("/api/v1/predictions", headers={"X-API-Key": API_KEY})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert any(p["symbol"] == "TEST" for p in data["items"])

    # add another company
    from titan_x.api.dependencies import request_session
    db_session = app.dependency_overrides[request_session]()
    async for s in db_session:
        s.add(Company(symbol="TEST2", company_name="TestCorp2", isin="US0987654321", exchange="NYSE", sector="Tech", status="active"))
        s.add(DailyPrice(symbol="TEST2", trade_date=date(2024, 6, 1), open=50, high=52, low=49, close=51, volume=500000))
        await s.flush()
    resp2 = await client.post("/api/v1/predictions/TEST2", headers={"X-API-Key": API_KEY})
    assert resp2.status_code == 200

    resp3 = await client.get("/api/v1/predictions", headers={"X-API-Key": API_KEY})
    assert resp3.status_code == 200
    data3 = resp3.json()
    assert data3["total"] >= 2


@pytest.mark.asyncio
async def test_delete_prediction(client: AsyncClient, seed_data: None) -> None:
    resp = await client.post("/api/v1/predictions/TEST", headers={"X-API-Key": API_KEY})
    assert resp.status_code == 200
    pred_id = resp.json()["id"]

    resp2 = await client.delete(f"/api/v1/predictions/{pred_id}", headers={"X-API-Key": API_KEY})
    assert resp2.status_code == 200
    assert resp2.json()["message"] == "Prediction deleted"

    resp3 = await client.delete(f"/api/v1/predictions/{pred_id}", headers={"X-API-Key": API_KEY})
    assert resp3.status_code == 404


@pytest.mark.asyncio
async def test_delete_prediction_invalid_id(client: AsyncClient) -> None:
    resp = await client.delete("/api/v1/predictions/99999", headers={"X-API-Key": API_KEY})
    assert resp.status_code == 404
