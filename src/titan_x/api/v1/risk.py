from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from titan_x.api.dependencies import get_risk_engine, require_api_key
from titan_x.api.schemas import MessageResponse, PaginatedResponse
from titan_x.services.risk_engine import RiskEngine

risk_router = APIRouter(
    prefix="/risk",
    tags=["risk"],
    dependencies=[Depends(require_api_key)],
)


class RiskMetricsResponse(BaseModel):
    id: int | None = None
    symbol: str
    as_of_date: str
    max_drawdown_1m: float | None = None
    max_drawdown_3m: float | None = None
    max_drawdown_6m: float | None = None
    max_drawdown_1y: float | None = None
    max_drawdown_ytd: float | None = None
    volatility_20d: float | None = None
    volatility_60d: float | None = None
    volatility_252d: float | None = None
    avg_daily_volume_20d: int | None = None
    avg_dollar_volume_20d: float | None = None
    liquidity_score: float | None = None
    gap_frequency_20d: float | None = None
    avg_gap_pct: float | None = None
    max_gap_pct: float | None = None
    event_risk_score: float | None = None
    news_count_30d: int | None = None
    composite_risk_score: float | None = None
    risk_rating: str | None = None


class PortfolioRiskResponse(BaseModel):
    id: int | None = None
    portfolio_id: str
    as_of_date: str
    num_positions: int
    total_value: float | None = None
    weighted_volatility: float | None = None
    portfolio_volatility: float | None = None
    portfolio_var_95: float | None = None
    portfolio_var_99: float | None = None
    expected_shortfall_95: float | None = None
    diversification_ratio: float | None = None
    concentration_risk: float | None = None
    average_correlation: float | None = None
    weighted_drawdown: float | None = None
    weighted_gap_risk: float | None = None
    composite_risk_score: float | None = None
    risk_rating: str | None = None
    holdings: list[dict] | None = None


class HoldingInput(BaseModel):
    weight: float | None = None
    value: float | None = None


@risk_router.post("/compute/{symbol}", response_model=RiskMetricsResponse)
async def compute_risk(
    symbol: str,
    engine: Annotated[RiskEngine, Depends(get_risk_engine)],
    as_of_date: date | None = Query(None),
    store: bool = Query(False),
) -> RiskMetricsResponse:
    if store:
        result = await engine.compute_and_store(symbol, as_of_date)
    else:
        result = await engine.compute_risk_metrics(symbol, as_of_date)
    if "error" in result:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result["error"])
    return RiskMetricsResponse(**result)


@risk_router.get("/metrics/{symbol}", response_model=RiskMetricsResponse)
async def get_risk_metrics(
    symbol: str,
    engine: Annotated[RiskEngine, Depends(get_risk_engine)],
    as_of_date: date | None = Query(None),
) -> RiskMetricsResponse:
    metrics = await engine.get_risk_metrics(symbol, as_of_date)
    if metrics is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Risk metrics not found")
    return RiskMetricsResponse(**{
        k: getattr(metrics, k, None)
        for k in RiskMetricsResponse.model_fields
        if hasattr(metrics, k)
    })


@risk_router.get("/metrics/{symbol}/history", response_model=PaginatedResponse[RiskMetricsResponse])
async def get_risk_history(
    symbol: str,
    engine: Annotated[RiskEngine, Depends(get_risk_engine)],
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
) -> PaginatedResponse[RiskMetricsResponse]:
    rows, total = await engine.get_historical_risk(symbol, start_date, end_date, skip, limit)
    items = [RiskMetricsResponse(**r.__dict__) for r in rows]
    return PaginatedResponse(items=items, total=total, skip=skip, limit=limit)


@risk_router.post("/portfolio/{portfolio_id}", response_model=PortfolioRiskResponse)
async def compute_portfolio_risk(
    portfolio_id: str,
    holdings: dict[str, HoldingInput],
    engine: Annotated[RiskEngine, Depends(get_risk_engine)],
    as_of_date: date | None = Query(None),
    store: bool = Query(False),
) -> PortfolioRiskResponse:
    h_dict = {sym: {"weight": h.weight, "value": h.value} for sym, h in holdings.items()}
    result = await engine.compute_portfolio_risk(portfolio_id, h_dict, as_of_date, store)
    if "error" in result:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result["error"])
    return PortfolioRiskResponse(**result)


@risk_router.get("/portfolio/{portfolio_id}", response_model=PortfolioRiskResponse)
async def get_portfolio_risk(
    portfolio_id: str,
    engine: Annotated[RiskEngine, Depends(get_risk_engine)],
    as_of_date: date | None = Query(None),
) -> PortfolioRiskResponse:
    pr = await engine.get_portfolio_risk(portfolio_id, as_of_date)
    if pr is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Portfolio risk not found")
    return PortfolioRiskResponse(**{
        k: getattr(pr, k, None) for k in PortfolioRiskResponse.model_fields if hasattr(pr, k)
    })


@risk_router.get("/portfolio/{portfolio_id}/history", response_model=PaginatedResponse[PortfolioRiskResponse])
async def get_portfolio_risk_history(
    portfolio_id: str,
    engine: Annotated[RiskEngine, Depends(get_risk_engine)],
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
) -> PaginatedResponse[PortfolioRiskResponse]:
    rows, total = await engine.get_portfolio_history(portfolio_id, skip, limit)
    items = [PortfolioRiskResponse(**r.__dict__) for r in rows]
    return PaginatedResponse(items=items, total=total, skip=skip, limit=limit)


@risk_router.delete("/metrics/{risk_id}", response_model=MessageResponse)
async def delete_risk_metrics(
    risk_id: int,
    engine: Annotated[RiskEngine, Depends(get_risk_engine)],
) -> MessageResponse:
    deleted = await engine.delete_risk_metrics(risk_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Risk metrics not found")
    return MessageResponse(message="Risk metrics deleted")


@risk_router.delete("/portfolio/{pr_id}", response_model=MessageResponse)
async def delete_portfolio_risk(
    pr_id: int,
    engine: Annotated[RiskEngine, Depends(get_risk_engine)],
) -> MessageResponse:
    deleted = await engine.delete_portfolio_risk(pr_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Portfolio risk not found")
    return MessageResponse(message="Portfolio risk deleted")
