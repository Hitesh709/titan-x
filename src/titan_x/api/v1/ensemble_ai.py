from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from titan_x.api.dependencies import get_ensemble_ai_engine, require_api_key
from titan_x.api.schemas import MessageResponse, PaginatedResponse
from titan_x.services.ensemble_ai_engine import EnsembleAIEngine

ensemble_router = APIRouter(
    prefix="/ensemble-ai",
    tags=["ensemble-ai"],
    dependencies=[Depends(require_api_key)],
)


class EnsemblePredictionResponse(BaseModel):
    id: int | None = None
    symbol: str
    as_of_date: str
    technical_score: float | None = None
    technical_signal: str | None = None
    technical_confidence: float | None = None
    fundamental_score: float | None = None
    fundamental_signal: str | None = None
    fundamental_confidence: float | None = None
    news_score: float | None = None
    news_signal: str | None = None
    news_confidence: float | None = None
    macro_score: float | None = None
    macro_signal: str | None = None
    macro_confidence: float | None = None
    risk_score: float | None = None
    risk_signal: str | None = None
    risk_confidence: float | None = None
    pattern_score: float | None = None
    pattern_signal: str | None = None
    pattern_confidence: float | None = None
    ensemble_score: float | None = None
    ensemble_signal: str | None = None
    ensemble_confidence: float | None = None
    agreement_level: str | None = None
    vote_breakdown_json: str | None = None
    weights_json: str | None = None
    explanation: str | None = None


class StoredPredictionResponse(BaseModel):
    id: int
    symbol: str
    as_of_date: date
    ensemble_score: float | None
    ensemble_signal: str | None
    ensemble_confidence: float | None
    agreement_level: str | None
    technical_signal: str | None
    fundamental_signal: str | None
    news_signal: str | None
    macro_signal: str | None
    risk_score: float | None
    pattern_signal: str | None


@ensemble_router.post("/predict/{symbol}", response_model=EnsemblePredictionResponse)
async def predict(
    symbol: str,
    engine: Annotated[EnsembleAIEngine, Depends(get_ensemble_ai_engine)],
    as_of_date: date | None = Query(None),
    store: bool = Query(False),
    technical_weight: float = Query(0.20, ge=0, le=1),
    fundamental_weight: float = Query(0.20, ge=0, le=1),
    news_weight: float = Query(0.15, ge=0, le=1),
    macro_weight: float = Query(0.15, ge=0, le=1),
    risk_weight: float = Query(0.15, ge=0, le=1),
    pattern_weight: float = Query(0.15, ge=0, le=1),
) -> EnsemblePredictionResponse:
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


@ensemble_router.get("/predictions/{symbol}", response_model=StoredPredictionResponse)
async def get_prediction(
    symbol: str,
    engine: Annotated[EnsembleAIEngine, Depends(get_ensemble_ai_engine)],
    as_of_date: date | None = Query(None),
) -> StoredPredictionResponse:
    pred = await engine.get_prediction(symbol, as_of_date)
    if pred is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No prediction found")
    return StoredPredictionResponse(**pred.__dict__)


@ensemble_router.get("/predictions", response_model=PaginatedResponse[StoredPredictionResponse])
async def list_predictions(
    engine: Annotated[EnsembleAIEngine, Depends(get_ensemble_ai_engine)],
    symbol: str | None = Query(None),
    signal: str | None = Query(None),
    min_confidence: float | None = Query(None, ge=0, le=100),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
) -> PaginatedResponse[StoredPredictionResponse]:
    rows, total = await engine.get_prediction_history(
        symbol, signal, min_confidence, start_date, end_date, skip, limit,
    )
    items = [StoredPredictionResponse(**r.__dict__) for r in rows]
    return PaginatedResponse(items=items, total=total, skip=skip, limit=limit)


@ensemble_router.delete("/predictions/{prediction_id}", response_model=MessageResponse)
async def delete_prediction(
    prediction_id: int,
    engine: Annotated[EnsembleAIEngine, Depends(get_ensemble_ai_engine)],
) -> MessageResponse:
    deleted = await engine.delete_prediction(prediction_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prediction not found")
    return MessageResponse(message="Ensemble prediction deleted")
