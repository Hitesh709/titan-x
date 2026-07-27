from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from titan_x.api.dependencies import get_decision_engine, require_api_key
from titan_x.api.schemas import MessageResponse, PaginatedResponse
from titan_x.services.decision_engine import DecisionEngine

decision_router = APIRouter(
    prefix="/decisions",
    tags=["decisions"],
    dependencies=[Depends(require_api_key)],
)


class DecisionResponse(BaseModel):
    id: int | None = None
    symbol: str
    as_of_date: str
    decision_type: str | None = "daily"
    opportunity_score: float | None = None
    confidence_score: float | None = None
    recommendation: str | None = None
    recommendation_code: int | None = None
    explanation: str | None = None
    pattern_score: float | None = None
    similarity_score: float | None = None
    technical_score: float | None = None
    sector_score: float | None = None
    sentiment_score: float | None = None
    breadth_score: float | None = None
    risk_score: float | None = None
    fundamental_score: float | None = None
    input_scores: dict | None = None


class StoredDecisionResponse(BaseModel):
    id: int
    symbol: str
    as_of_date: date
    decision_type: str
    opportunity_score: float | None
    confidence_score: float | None
    recommendation: str | None
    recommendation_code: int | None
    explanation: str | None
    pattern_score: float | None
    similarity_score: float | None
    technical_score: float | None
    sector_score: float | None
    sentiment_score: float | None
    breadth_score: float | None
    risk_score: float | None
    fundamental_score: float | None


@decision_router.post("/generate/{symbol}", response_model=DecisionResponse)
async def generate_decision(
    symbol: str,
    scores: dict,
    engine: Annotated[DecisionEngine, Depends(get_decision_engine)],
    as_of_date: date | None = Query(None),
    store: bool = Query(False),
    decision_type: str = Query("daily"),
) -> DecisionResponse:
    try:
        result = await engine.generate_decision(symbol, scores, as_of_date, store, decision_type)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return DecisionResponse(**result)


@decision_router.get("/{symbol}", response_model=StoredDecisionResponse)
async def get_latest_decision(
    symbol: str,
    engine: Annotated[DecisionEngine, Depends(get_decision_engine)],
    as_of_date: date | None = Query(None),
) -> StoredDecisionResponse:
    decision = await engine.get_decision(symbol, as_of_date)
    if decision is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No decision found")
    return StoredDecisionResponse(**decision.__dict__)


@decision_router.get("", response_model=PaginatedResponse[StoredDecisionResponse])
async def list_decisions(
    engine: Annotated[DecisionEngine, Depends(get_decision_engine)],
    symbol: str | None = Query(None),
    recommendation: str | None = Query(None),
    min_opportunity: float | None = Query(None, ge=0, le=100),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
) -> PaginatedResponse[StoredDecisionResponse]:
    rows, total = await engine.get_decision_history(
        symbol, recommendation, min_opportunity,
        start_date, end_date, skip, limit,
    )
    items = [StoredDecisionResponse(**r.__dict__) for r in rows]
    return PaginatedResponse(items=items, total=total, skip=skip, limit=limit)


@decision_router.get("/recommendation/{recommendation}", response_model=list[StoredDecisionResponse])
async def get_decisions_by_recommendation(
    recommendation: str,
    engine: Annotated[DecisionEngine, Depends(get_decision_engine)],
    limit: int = Query(20, ge=1, le=100),
) -> list[StoredDecisionResponse]:
    results = await engine.get_latest_by_recommendation(recommendation, limit)
    return [StoredDecisionResponse(**r.__dict__) for r in results]


@decision_router.delete("/{decision_id}", response_model=MessageResponse)
async def delete_decision(
    decision_id: int,
    engine: Annotated[DecisionEngine, Depends(get_decision_engine)],
) -> MessageResponse:
    deleted = await engine.delete_decision(decision_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Decision not found")
    return MessageResponse(message="Decision deleted")
