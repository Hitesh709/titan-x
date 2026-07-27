from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from titan_x.api.dependencies import get_technical_indicator_engine, require_api_key
from titan_x.api.schemas import MessageResponse, PaginatedResponse
from titan_x.services.technical_indicator_engine import TechnicalIndicatorEngine

tech_ind_router = APIRouter(
    prefix="/technical-indicators",
    tags=["technical-indicators"],
    dependencies=[Depends(require_api_key)],
)


class IndicatorDefResponse(BaseModel):
    name: str
    category: str
    description: str
    default_params: dict[str, Any]


class IndicatorValueResponse(BaseModel):
    trade_date: str
    indicator: str
    value: float | None = None
    value_secondary: float | None = None
    value_tertiary: float | None = None


class StoredIndicatorResponse(BaseModel):
    id: int
    symbol: str
    trade_date: date
    indicator: str
    period: int | None
    params: str | None
    value: float | None
    value_secondary: float | None
    value_tertiary: float | None
    metadata_json: str | None


class ComputeRequest(BaseModel):
    params: dict[str, Any] | None = None
    store: bool = True


@tech_ind_router.get("/indicators", response_model=list[IndicatorDefResponse])
async def list_indicators(
    engine: Annotated[TechnicalIndicatorEngine, Depends(get_technical_indicator_engine)],
) -> list[IndicatorDefResponse]:
    return [IndicatorDefResponse(**ind) for ind in engine.list_indicators()]


@tech_ind_router.get("/indicators/{indicator}", response_model=IndicatorDefResponse)
async def get_indicator_def(
    indicator: str,
    engine: Annotated[TechnicalIndicatorEngine, Depends(get_technical_indicator_engine)],
) -> IndicatorDefResponse:
    indicators = engine.list_indicators()
    for ind in indicators:
        if ind["name"].upper() == indicator.upper():
            return IndicatorDefResponse(**ind)
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Indicator '{indicator}' not found")


@tech_ind_router.post("/compute/{symbol}/{indicator}", response_model=list[IndicatorValueResponse])
async def compute_indicator(
    symbol: str, indicator: str,
    body: ComputeRequest,
    engine: Annotated[TechnicalIndicatorEngine, Depends(get_technical_indicator_engine)],
) -> list[IndicatorValueResponse]:
    try:
        results = await engine.compute(symbol, indicator, params=body.params, store=body.store)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return [IndicatorValueResponse(**r) for r in results]


@tech_ind_router.get("/stored/{symbol}/{indicator}", response_model=PaginatedResponse[StoredIndicatorResponse])
async def get_stored_indicators(
    symbol: str, indicator: str,
    engine: Annotated[TechnicalIndicatorEngine, Depends(get_technical_indicator_engine)],
    period: int | None = Query(None, ge=1),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(500, ge=1, le=2000),
) -> PaginatedResponse[StoredIndicatorResponse]:
    indicators, total = await engine.get_stored(
        symbol, indicator, period=period,
        date_from=date_from, date_to=date_to,
        skip=skip, limit=limit,
    )
    items = [StoredIndicatorResponse(**i.__dict__) for i in indicators]
    return PaginatedResponse(items=items, total=total, skip=skip, limit=limit)


@tech_ind_router.delete("/stored/{indicator_id}", response_model=MessageResponse)
async def delete_stored_indicator(
    indicator_id: int,
    engine: Annotated[TechnicalIndicatorEngine, Depends(get_technical_indicator_engine)],
) -> MessageResponse:
    deleted = await engine.delete_stored(indicator_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Indicator not found")
    return MessageResponse(message="Stored indicator deleted")
