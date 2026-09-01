import json
from datetime import date, datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.api import deps
from titan_x.api.dependencies import get_prediction_engine, require_api_key
from titan_x.api.schemas import MessageResponse, PaginatedResponse
from titan_x.services.point_in_time_prediction_engine import PointInTimePredictionEngine
from titan_x.services.prediction_audit_service import PredictionAuditService
from titan_x.services.prediction_engine import PredictionEngine

prediction_router = APIRouter(
    prefix="/predictions",
    tags=["predictions"],
    dependencies=[Depends(require_api_key)],
)


class HorizonPredictionResponse(BaseModel):
    probability: float | None = None
    expected_return: float | None = None
    expected_drawdown: float | None = None
    confidence: float | None = None
    signal: str | None = None


class PredictionResponse(BaseModel):
    id: int | None = None
    symbol: str
    as_of_date: str

    probability_5d: float | None = None
    expected_return_5d: float | None = None
    expected_drawdown_5d: float | None = None
    confidence_5d: float | None = None
    signal_5d: str | None = None

    probability_10d: float | None = None
    expected_return_10d: float | None = None
    expected_drawdown_10d: float | None = None
    confidence_10d: float | None = None
    signal_10d: str | None = None

    probability_15d: float | None = None
    expected_return_15d: float | None = None
    expected_drawdown_15d: float | None = None
    confidence_15d: float | None = None
    signal_15d: str | None = None

    probability_20d: float | None = None
    expected_return_20d: float | None = None
    expected_drawdown_20d: float | None = None
    confidence_20d: float | None = None
    signal_20d: str | None = None

    probability_30d: float | None = None
    expected_return_30d: float | None = None
    expected_drawdown_30d: float | None = None
    confidence_30d: float | None = None
    signal_30d: str | None = None

    holding_period: int | None = None
    overall_signal: str | None = None
    overall_score: float | None = None
    overall_confidence: float | None = None
    explanation: str | None = None


class StoredPredictionResponse(BaseModel):
    id: int
    symbol: str
    as_of_date: date
    overall_signal: str | None = None
    overall_confidence: float | None = None
    holding_period: int | None = None


async def get_point_in_time_prediction_engine(
    session: Annotated[AsyncSession, Depends(deps.request_session)],
) -> PointInTimePredictionEngine:
    """Provide the existing prediction engine with leakage-safe data access."""
    return PointInTimePredictionEngine(session)


@prediction_router.post("/{symbol}", response_model=PredictionResponse)
async def create_prediction(
    symbol: str,
    engine: Annotated[PointInTimePredictionEngine, Depends(get_point_in_time_prediction_engine)],
    session: Annotated[AsyncSession, Depends(deps.request_session)],
    as_of_date: date | None = Query(None),
    store: bool = Query(True),
) -> PredictionResponse:
    try:
        result = await engine.predict(symbol, as_of_date, store=store)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e
    if "error" in result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result["error"])

    if store and result.get("id") is not None:
        effective_date = result.get("as_of_date")
        if not isinstance(effective_date, date):
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Prediction audit date missing")

        try:
            horizon_summary = json.loads(result.get("horizon_summary_json", "{}"))
            data_sources = json.loads(result.get("data_sources_json", "{}"))
            audit_input = {
                "symbol": symbol.upper(),
                "as_of_date": effective_date.isoformat(),
                "engine": "prediction-engine:deterministic-v1",
                "feature_contract": "prediction-inputs:v1",
                "horizons": horizon_summary,
                "data_sources": data_sources,
            }
            await PredictionAuditService(session).record_prediction(
                prediction_id=int(result["id"]),
                symbol=symbol.upper(),
                as_of_date=effective_date,
                generated_at=datetime.now(timezone.utc),
                input_payload=audit_input,
                data_snapshot_ref={
                    "as_of_date": effective_date.isoformat(),
                    "inputs_used": sorted(k for k, enabled in data_sources.items() if enabled),
                },
                data_source_ref=data_sources,
                feature_version_ref="prediction-inputs:v1",
                model_version_ref="prediction-engine:deterministic-v1",
                market_regime=None,
                explanation_payload=result.get("explanation"),
            )
        except Exception:
            await session.rollback()
            raise

    if isinstance(result.get("as_of_date"), date):
        result["as_of_date"] = result["as_of_date"].isoformat()
    return PredictionResponse(**result)


@prediction_router.get("/{symbol}", response_model=StoredPredictionResponse)
async def get_prediction(
    symbol: str,
    engine: Annotated[PredictionEngine, Depends(get_prediction_engine)],
    as_of_date: date | None = Query(None),
) -> StoredPredictionResponse:
    pred = await engine.get_prediction(symbol, as_of_date)
    if pred is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No prediction found")
    return StoredPredictionResponse(**{k: v for k, v in pred.__dict__.items() if k in StoredPredictionResponse.model_fields})


@prediction_router.get("", response_model=PaginatedResponse[StoredPredictionResponse])
async def list_predictions(
    engine: Annotated[PredictionEngine, Depends(get_prediction_engine)],
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
    items = [StoredPredictionResponse(**{k: v for k, v in r.__dict__.items() if k in StoredPredictionResponse.model_fields}) for r in rows]
    return PaginatedResponse(items=items, total=total, skip=skip, limit=limit)


@prediction_router.delete("/{prediction_id}", response_model=MessageResponse)
async def delete_prediction(
    prediction_id: int,
    engine: Annotated[PredictionEngine, Depends(get_prediction_engine)],
) -> MessageResponse:
    deleted = await engine.delete_prediction(prediction_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prediction not found")
    return MessageResponse(message="Prediction deleted")
