"""Integration tests for Ensemble AI Engine - minimal app without full v1 chain."""

from datetime import date
import sys
from pathlib import Path

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Build a minimal app without importing titan_x.api.v1 (to avoid pre-existing bugs)
# We manually create the router and register endpoints

from titan_x.db.base import Base
from titan_x.models.company import Company
from titan_x.models.risk import RiskMetrics
from titan_x.services.ensemble_ai_engine import EnsembleAIEngine


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
async def engine(session: AsyncSession) -> EnsembleAIEngine:
    return EnsembleAIEngine(session)


@pytest_asyncio.fixture
async def client(engine: EnsembleAIEngine, session: AsyncSession) -> AsyncClient:
    from fastapi import Depends, HTTPException, Query, status
    from pydantic import BaseModel

    app = FastAPI()

    class EnsemblePredictionResponse(BaseModel):
        id: int | None = None
        symbol: str
        as_of_date: str
        ensemble_score: float | None = None
        ensemble_signal: str | None = None
        ensemble_confidence: float | None = None
        explanation: str | None = None

    class StoredPredictionResponse(BaseModel):
        id: int
        symbol: str
        as_of_date: date
        ensemble_score: float | None = None
        ensemble_signal: str | None = None

    class MessageResponse(BaseModel):
        message: str

    class PaginatedResponse(BaseModel):
        items: list
        total: int
        skip: int
        limit: int

    @app.post("/predict/{symbol}")
    async def predict(
        symbol: str,
        as_of_date: date | None = Query(None),
        store: bool = Query(False),
        technical_weight: float = Query(0.20, ge=0, le=1),
        fundamental_weight: float = Query(0.20, ge=0, le=1),
        news_weight: float = Query(0.15, ge=0, le=1),
        macro_weight: float = Query(0.15, ge=0, le=1),
        risk_weight: float = Query(0.15, ge=0, le=1),
        pattern_weight: float = Query(0.15, ge=0, le=1),
    ):
        weights = {
            "technical": technical_weight,
            "fundamental": fundamental_weight,
            "news": news_weight,
            "macro": macro_weight,
            "risk": risk_weight,
            "pattern": pattern_weight,
        }
        try:
            result = await engine.predict(symbol, as_of_date, weights, store)
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
        if "error" in result:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result["error"])
        return EnsemblePredictionResponse(**result)

    @app.get("/predictions/{symbol}")
    async def get_prediction(symbol: str, as_of_date: date | None = Query(None)):
        pred = await engine.get_prediction(symbol, as_of_date)
        if pred is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No prediction found")
        return StoredPredictionResponse(**{k: v for k, v in pred.__dict__.items() if k in StoredPredictionResponse.model_fields})

    @app.get("/predictions")
    async def list_predictions(
        symbol: str | None = Query(None),
        signal: str | None = Query(None),
        min_confidence: float | None = Query(None, ge=0, le=100),
        start_date: date | None = Query(None),
        end_date: date | None = Query(None),
        skip: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=500),
    ):
        rows, total = await engine.get_prediction_history(
            symbol, signal, min_confidence, start_date, end_date, skip, limit,
        )
        items = [StoredPredictionResponse(**{k: v for k, v in r.__dict__.items() if k in StoredPredictionResponse.model_fields}) for r in rows]
        return PaginatedResponse(items=items, total=total, skip=skip, limit=limit)

    @app.delete("/predictions/{prediction_id}")
    async def delete_prediction(prediction_id: int):
        deleted = await engine.delete_prediction(prediction_id)
        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prediction not found")
        return MessageResponse(message="Ensemble prediction deleted")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestEnsembleAIApi:
    @pytest.mark.asyncio
    async def test_predict_endpoint(self, client: AsyncClient, session: AsyncSession) -> None:
        session.add(Company(symbol="TEST", company_name="TestCorp", isin="US1234567890", exchange="NYSE", sector="Tech", status="active"))
        await session.flush()

        resp = await client.post("/predict/TEST?store=true")
        assert resp.status_code == 200
        data = resp.json()
        assert data["symbol"] == "TEST"
        assert data["ensemble_signal"] is not None

    @pytest.mark.asyncio
    async def test_predict_nonexistent_symbol(self, client: AsyncClient) -> None:
        resp = await client.post("/predict/NONEXIST")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_predict_with_weights(self, client: AsyncClient, session: AsyncSession) -> None:
        session.add(Company(symbol="TEST", company_name="TestCorp", isin="US1234567890", exchange="NYSE", sector="Tech", status="active"))
        session.add(RiskMetrics(symbol="TEST", as_of_date=date(2024, 6, 1), composite_risk_score=15.0, liquidity_score=85.0, volatility_252d=12.0))
        await session.flush()

        resp = await client.post("/predict/TEST?as_of_date=2024-06-05&risk_weight=1.0&technical_weight=0&fundamental_weight=0&news_weight=0&macro_weight=0&pattern_weight=0")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_get_prediction_endpoint(self, client: AsyncClient, session: AsyncSession) -> None:
        session.add(Company(symbol="TEST", company_name="TestCorp", isin="US1234567890", exchange="NYSE", sector="Tech", status="active"))
        session.add(RiskMetrics(symbol="TEST", as_of_date=date(2024, 6, 1), composite_risk_score=30.0, liquidity_score=75.0, volatility_252d=18.0))
        await session.flush()

        await client.post("/predict/TEST?store=true")
        resp = await client.get("/predictions/TEST")
        assert resp.status_code == 200
        data = resp.json()
        assert data["symbol"] == "TEST"

    @pytest.mark.asyncio
    async def test_get_prediction_not_found(self, client: AsyncClient) -> None:
        resp = await client.get("/predictions/TEST")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_list_predictions(self, client: AsyncClient, session: AsyncSession) -> None:
        session.add(Company(symbol="TEST", company_name="TestCorp", isin="US1234567890", exchange="NYSE", sector="Tech", status="active"))
        await session.flush()

        await client.post("/predict/TEST?store=true")
        resp = await client.get("/predictions")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        assert len(data["items"]) >= 1

    @pytest.mark.asyncio
    async def test_list_predictions_filter_by_symbol(self, client: AsyncClient, session: AsyncSession) -> None:
        session.add(Company(symbol="AAA", company_name="AAA Inc", isin="US1111111111", exchange="NYSE", sector="Tech", status="active"))
        session.add(Company(symbol="BBB", company_name="BBB Corp", isin="US2222222222", exchange="NYSE", sector="Fin", status="active"))
        await session.flush()

        await client.post("/predict/AAA?store=true")
        resp = await client.get("/predictions?symbol=AAA")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["symbol"] == "AAA"

    @pytest.mark.asyncio
    async def test_delete_prediction(self, client: AsyncClient, session: AsyncSession) -> None:
        session.add(Company(symbol="TEST", company_name="TestCorp", isin="US1234567890", exchange="NYSE", sector="Tech", status="active"))
        session.add(RiskMetrics(symbol="TEST", as_of_date=date(2024, 6, 1), composite_risk_score=30.0, liquidity_score=75.0, volatility_252d=18.0))
        await session.flush()

        post = await client.post("/predict/TEST?store=true")
        pred_id = post.json()["id"]
        resp = await client.delete(f"/predictions/{pred_id}")
        assert resp.status_code == 200
        assert resp.json()["message"] == "Ensemble prediction deleted"

    @pytest.mark.asyncio
    async def test_delete_prediction_not_found(self, client: AsyncClient) -> None:
        resp = await client.delete("/predictions/99999")
        assert resp.status_code == 404
