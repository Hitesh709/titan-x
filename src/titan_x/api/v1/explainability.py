from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from titan_x.api.dependencies import (
    get_explainability_dashboard_service,
    get_explainability_engine,
    require_api_key,
)
from titan_x.api.schemas import MessageResponse, PaginatedResponse
from titan_x.services.explainability_dashboard_service import ExplainabilityDashboardService
from titan_x.services.explainability_engine import ExplainabilityEngine

explainability_router = APIRouter(
    prefix="/explainability",
    tags=["explainability"],
    dependencies=[Depends(require_api_key)],
)


class ExplanationFactorResponse(BaseModel):
    factor: str
    score: float
    impact: str
    source: str
    weight: str


class ExplainabilityResponse(BaseModel):
    id: int | None = None
    symbol: str
    as_of_date: str
    why_buy: list[ExplanationFactorResponse]
    why_not_buy: list[ExplanationFactorResponse]
    strengths: list[ExplanationFactorResponse]
    weaknesses: list[ExplanationFactorResponse]
    risk_factors: list[ExplanationFactorResponse]
    historical_evidence: list[ExplanationFactorResponse]
    overall_score: float | None = None
    overall_signal: str | None = None
    overall_confidence: float | None = None


class StoredExplainabilityResponse(BaseModel):
    id: int
    symbol: str
    as_of_date: date
    overall_signal: str | None = None
    overall_score: float | None = None
    overall_confidence: float | None = None


@explainability_router.post("/{symbol}", response_model=ExplainabilityResponse)
async def create_explainability(
    symbol: str,
    engine: Annotated[ExplainabilityEngine, Depends(get_explainability_engine)],
    as_of_date: date | None = Query(None),
    store: bool = Query(True),
) -> ExplainabilityResponse:
    try:
        result = await engine.analyze(symbol, as_of_date, store=store)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    if "error" in result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result["error"])
    if isinstance(result.get("as_of_date"), date):
        result["as_of_date"] = result["as_of_date"].isoformat()
    return ExplainabilityResponse(**result)


@explainability_router.get("/{symbol}", response_model=StoredExplainabilityResponse)
async def get_explainability(
    symbol: str,
    engine: Annotated[ExplainabilityEngine, Depends(get_explainability_engine)],
    as_of_date: date | None = Query(None),
) -> StoredExplainabilityResponse:
    analysis = await engine.get_analysis(symbol, as_of_date)
    if analysis is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No explainability analysis found")
    return StoredExplainabilityResponse(**analysis.__dict__)


@explainability_router.get("", response_model=PaginatedResponse[StoredExplainabilityResponse])
async def list_explainability(
    engine: Annotated[ExplainabilityEngine, Depends(get_explainability_engine)],
    symbol: str | None = Query(None),
    signal: str | None = Query(None),
    min_confidence: float | None = Query(None, ge=0, le=100),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
) -> PaginatedResponse[StoredExplainabilityResponse]:
    rows, total = await engine.get_analysis_history(
        symbol, signal, min_confidence, start_date, end_date, skip, limit,
    )
    items = [StoredExplainabilityResponse(**r.__dict__) for r in rows]
    return PaginatedResponse(items=items, total=total, skip=skip, limit=limit)


@explainability_router.get("/dashboard/{symbol}")
async def get_explainability_dashboard(
    symbol: str,
    svc: Annotated[ExplainabilityDashboardService, Depends(get_explainability_dashboard_service)],
    as_of_date: date | None = Query(None),
):
    result = await svc.get_dashboard(symbol, as_of_date)
    if "error" in result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result["error"])
    return result


@explainability_router.delete("/{analysis_id}", response_model=MessageResponse)
async def delete_explainability(
    analysis_id: int,
    engine: Annotated[ExplainabilityEngine, Depends(get_explainability_engine)],
) -> MessageResponse:
    deleted = await engine.delete_analysis(analysis_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Explainability analysis not found")
    return MessageResponse(message="Explainability analysis deleted")
