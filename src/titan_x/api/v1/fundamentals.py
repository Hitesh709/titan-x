from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from titan_x.api.dependencies import get_fundamental_engine, require_api_key
from titan_x.api.schemas import MessageResponse, PaginatedResponse
from titan_x.services.fundamental_engine import FundamentalEngine

fund_router = APIRouter(
    prefix="/fundamentals",
    tags=["fundamentals"],
    dependencies=[Depends(require_api_key)],
)


class MetricDefResponse(BaseModel):
    name: str
    category: str
    description: str
    default_params: dict[str, Any]


class StoredMetricResponse(BaseModel):
    id: int
    symbol: str
    fiscal_year: int
    fiscal_period: int
    period_type: str
    metric_name: str
    value: float | None
    metadata_json: str | None


class ComputeResponse(BaseModel):
    symbol: str
    fiscal_year: int
    period_type: str
    metrics: dict[str, Any]


class ScreenResult(BaseModel):
    symbol: str
    value: float | None
    fiscal_year: int
    metric: str


@fund_router.get("/metrics", response_model=list[MetricDefResponse])
async def list_metrics(
    engine: Annotated[FundamentalEngine, Depends(get_fundamental_engine)],
) -> list[MetricDefResponse]:
    return [MetricDefResponse(**m) for m in engine.list_metrics()]


@fund_router.post("/compute/{symbol}/{fiscal_year}", response_model=ComputeResponse)
async def compute_fundamentals(
    symbol: str, fiscal_year: int,
    engine: Annotated[FundamentalEngine, Depends(get_fundamental_engine)],
    period_type: str = Query("annual", pattern=r"^(annual|quarterly)$"),
) -> ComputeResponse:
    try:
        metrics = await engine.compute_all(symbol, fiscal_year, period_type)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return ComputeResponse(symbol=symbol.upper(), fiscal_year=fiscal_year, period_type=period_type, metrics=metrics)


@fund_router.get("/stored/{symbol}", response_model=PaginatedResponse[StoredMetricResponse])
async def get_stored_metrics(
    symbol: str,
    engine: Annotated[FundamentalEngine, Depends(get_fundamental_engine)],
    metric_name: str | None = Query(None, min_length=1),
    fiscal_year: int | None = Query(None, ge=1900, le=2100),
    period_type: str | None = Query(None, pattern=r"^(annual|quarterly)$"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
) -> PaginatedResponse[StoredMetricResponse]:
    metrics, total = await engine.get_stored(
        symbol, metric_name=metric_name, fiscal_year=fiscal_year,
        period_type=period_type, skip=skip, limit=limit,
    )
    items = [StoredMetricResponse(**m.__dict__) for m in metrics]
    return PaginatedResponse(items=items, total=total, skip=skip, limit=limit)


@fund_router.get("/screen", response_model=list[ScreenResult])
async def screen_by_metric(
    engine: Annotated[FundamentalEngine, Depends(get_fundamental_engine)],
    metric_name: str = Query(min_length=1),
    min_val: float | None = Query(None),
    max_val: float | None = Query(None),
    fiscal_year: int | None = Query(None, ge=1900, le=2100),
    period_type: str = Query("annual", pattern=r"^(annual|quarterly)$"),
    limit: int = Query(50, ge=1, le=200),
) -> list[ScreenResult]:
    results = await engine.screen(metric_name, min_val=min_val, max_val=max_val,
                                   fiscal_year=fiscal_year, period_type=period_type, limit=limit)
    return [ScreenResult(**r) for r in results]


@fund_router.delete("/stored/{metric_id}", response_model=MessageResponse)
async def delete_metric(
    metric_id: int,
    engine: Annotated[FundamentalEngine, Depends(get_fundamental_engine)],
) -> MessageResponse:
    deleted = await engine.delete_stored(metric_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Metric not found")
    return MessageResponse(message="Fundamental metric deleted")
