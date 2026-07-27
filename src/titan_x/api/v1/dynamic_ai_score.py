from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.api import deps
from titan_x.models.user import User
from titan_x.api.schemas import PaginatedResponse
from titan_x.services.dynamic_ai_score_service import DynamicAIScoreService

router = APIRouter(prefix="/dynamic-ai-score", tags=["dynamic-ai-score"])


@router.post("/compute/{symbol}")
async def compute_dynamic_ai_score(
    symbol: str,
    as_of_date: date | None = Query(None),
    store: bool = Query(False),
    session: AsyncSession = Depends(deps.get_session),
    current_user: User = Depends(deps.get_current_active_user),
):
    service = DynamicAIScoreService(session)
    result = await service.compute_score(symbol, as_of_date, store=store)
    return result


@router.post("/adjust-weights/{symbol}")
async def adjust_weights(
    symbol: str,
    as_of_date: date = Query(...),
    actual_return_pct: float = Query(...),
    session: AsyncSession = Depends(deps.get_session),
    current_user: User = Depends(deps.get_current_active_user),
):
    service = DynamicAIScoreService(session)
    result = await service.adjust_weights(symbol, as_of_date, actual_return_pct)
    return result


@router.get("/scores/{symbol}")
async def get_dynamic_ai_score(
    symbol: str,
    as_of_date: date | None = Query(None),
    session: AsyncSession = Depends(deps.get_session),
    current_user: User = Depends(deps.get_current_active_user),
):
    service = DynamicAIScoreService(session)
    if as_of_date:
        score = await service.get_score(symbol, as_of_date)
        return score
    scores, total = await service.get_score_history(symbol=symbol)
    return PaginatedResponse(items=scores, total=total, skip=0, limit=100)


@router.get("/history")
async def get_dynamic_ai_score_history(
    symbol: str | None = Query(None),
    signal: str | None = Query(None),
    min_score: float | None = Query(None),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    session: AsyncSession = Depends(deps.get_session),
    current_user: User = Depends(deps.get_current_active_user),
):
    service = DynamicAIScoreService(session)
    scores, total = await service.get_score_history(
        symbol=symbol, signal=signal, min_score=min_score,
        start_date=start_date, end_date=end_date,
        skip=skip, limit=limit,
    )
    return PaginatedResponse(items=scores, total=total, skip=skip, limit=limit)


@router.get("/weights")
async def get_dynamic_weights(
    session: AsyncSession = Depends(deps.get_session),
    current_user: User = Depends(deps.get_current_active_user),
):
    service = DynamicAIScoreService(session)
    return await service.get_weights()


@router.delete("/scores/{score_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_dynamic_ai_score(
    score_id: int,
    session: AsyncSession = Depends(deps.get_session),
    current_user: User = Depends(deps.get_current_active_user),
):
    service = DynamicAIScoreService(session)
    deleted = await service.delete_score(score_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Score not found")
