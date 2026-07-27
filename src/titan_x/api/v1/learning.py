from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from titan_x.api.dependencies import (
    get_current_active_user,
    get_learning_engine,
    require_api_key,
)
from titan_x.api.schemas import MessageResponse, PaginatedResponse
from titan_x.models.user import User
from titan_x.services.learning_engine import LearningEngine

learning_router = APIRouter(
    prefix="/learning",
    tags=["learning"],
    dependencies=[Depends(require_api_key)],
)


@learning_router.post("/evaluate/{prediction_id}")
async def evaluate_prediction(
    prediction_id: int,
    engine: Annotated[LearningEngine, Depends(get_learning_engine)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> dict:
    try:
        result = await engine.evaluate_prediction(prediction_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@learning_router.post("/evaluate")
async def evaluate_outdated(
    engine: Annotated[LearningEngine, Depends(get_learning_engine)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    max_records: int = Query(50, ge=1, le=500),
) -> list[dict]:
    results = await engine.evaluate_outdated_predictions(max_records=max_records)
    return results


@learning_router.get("/summary")
async def get_learning_summary(
    engine: Annotated[LearningEngine, Depends(get_learning_engine)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    symbol: str | None = Query(None, max_length=16),
    horizon_days: int | None = Query(None, ge=1, le=365),
) -> dict:
    return await engine.compute_summary(symbol=symbol, horizon_days=horizon_days)


@learning_router.get("/history")
async def get_learning_history(
    engine: Annotated[LearningEngine, Depends(get_learning_engine)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    symbol: str | None = Query(None, max_length=16),
    horizon_days: int | None = Query(None, ge=1, le=365),
    was_correct: bool | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
) -> PaginatedResponse[dict]:
    rows, total = await engine.get_history(
        symbol=symbol, horizon_days=horizon_days,
        was_correct=was_correct, skip=skip, limit=limit,
    )
    items = [
        {
            "id": r.id,
            "symbol": r.symbol,
            "as_of_date": r.as_of_date.isoformat() if r.as_of_date else None,
            "horizon_days": r.horizon_days,
            "predicted_return_pct": r.predicted_return_pct,
            "actual_return_pct": r.actual_return_pct,
            "predicted_signal": r.predicted_signal,
            "actual_signal": r.actual_signal,
            "was_correct": r.was_correct,
            "absolute_error": r.absolute_error,
            "evaluated_at": r.evaluated_at.isoformat() if r.evaluated_at else None,
        }
        for r in rows
    ]
    return PaginatedResponse(items=items, total=total, skip=skip, limit=limit)


@learning_router.get("/history/{record_id}")
async def get_learning_record(
    record_id: int,
    engine: Annotated[LearningEngine, Depends(get_learning_engine)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> dict:
    result = await engine.get_history_record(record_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Record not found")
    return result


@learning_router.delete("/history/{record_id}", response_model=MessageResponse)
async def delete_learning_record(
    record_id: int,
    engine: Annotated[LearningEngine, Depends(get_learning_engine)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> MessageResponse:
    deleted = await engine.delete_history(record_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Record not found")
    return MessageResponse(message="Record deleted")


@learning_router.get("/weights")
async def get_weights(
    engine: Annotated[LearningEngine, Depends(get_learning_engine)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    source_name: str | None = Query(None, max_length=32),
) -> list[dict]:
    return await engine.get_weights(source_name=source_name)


@learning_router.post("/weights/update/{source_name}")
async def update_source_weight(
    source_name: str,
    engine: Annotated[LearningEngine, Depends(get_learning_engine)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> dict:
    return await engine.update_source_weights(source_name)


@learning_router.post("/weights/update")
async def update_all_weights(
    engine: Annotated[LearningEngine, Depends(get_learning_engine)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> dict:
    return await engine.update_all_weights()


@learning_router.post("/weights/normalize")
async def normalize_weights(
    engine: Annotated[LearningEngine, Depends(get_learning_engine)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> dict:
    return await engine.normalize_weights()
