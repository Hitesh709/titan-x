from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel, Field

from titan_x.api.dependencies import get_intraday_service, require_api_key
from titan_x.api.schemas import MessageResponse, PaginatedResponse
from titan_x.services.intraday_service import IntradayService

intraday_router = APIRouter(
    prefix="/intraday",
    tags=["intraday"],
    dependencies=[Depends(require_api_key)],
)

VALID_RESOLUTIONS: list[str] = ["1min", "5min", "15min", "hourly"]


class IntradayBarResponse(BaseModel):
    id: int
    symbol: str
    timestamp: datetime
    resolution: str
    open: float
    high: float
    low: float
    close: float
    volume: int


class IntradayBarCreateRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=16)
    timestamp: datetime
    resolution: str = Field(pattern=r"^(1min|5min|15min|hourly)$")
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    volume: int = Field(ge=0)


class IntradayBulkImportResponse(BaseModel):
    total: int
    created: int
    skipped_duplicates: int
    errors: list[dict[str, Any]]


class AggregateResponse(BaseModel):
    bars_created: int


@intraday_router.get("/{symbol}/{resolution}", response_model=PaginatedResponse[IntradayBarResponse])
async def list_bars(
    service: IntradayService = Depends(get_intraday_service),
    symbol: str = Path(...),
    resolution: str = Path(pattern=r"^(1min|5min|15min|hourly)$"),
    start: datetime | None = Query(None),
    end: datetime | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
) -> PaginatedResponse[IntradayBarResponse]:
    bars, total = await service.get_bars(symbol, resolution, start=start, end=end, skip=skip, limit=limit)
    items = [IntradayBarResponse(**b.__dict__) for b in bars]
    return PaginatedResponse(items=items, total=total, skip=skip, limit=limit)


@intraday_router.post("", response_model=IntradayBarResponse, status_code=status.HTTP_201_CREATED)
async def create_bar(
    body: IntradayBarCreateRequest,
    service: Annotated[IntradayService, Depends(get_intraday_service)],
) -> IntradayBarResponse:
    try:
        bar = await service.create_bar(
            symbol=body.symbol, timestamp=body.timestamp, resolution=body.resolution,
            open=body.open, high=body.high, low=body.low, close=body.close, volume=body.volume,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return IntradayBarResponse(**bar.__dict__)


@intraday_router.post("/bulk/{symbol}/{resolution}", response_model=IntradayBulkImportResponse)
async def bulk_import(
    service: IntradayService = Depends(get_intraday_service),
    symbol: str = Path(...),
    resolution: str = Path(pattern=r"^(1min|5min|15min|hourly)$"),
    records: list[dict[str, Any]] = [],
) -> IntradayBulkImportResponse:
    result = await service.bulk_import(symbol, resolution, records)
    return IntradayBulkImportResponse(**result)


@intraday_router.post("/aggregate/{symbol}", response_model=AggregateResponse)
async def aggregate_bars(
    service: IntradayService = Depends(get_intraday_service),
    symbol: str = Path(...),
    source: str = Query(pattern=r"^(1min|5min|15min|hourly)$"),
    target: str = Query(pattern=r"^(5min|15min|hourly)$"),
    start: datetime | None = Query(None),
    end: datetime | None = Query(None),
) -> AggregateResponse:
    try:
        count = await service.aggregate_resolution(symbol, source, target, start=start, end=end)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return AggregateResponse(bars_created=count)


@intraday_router.post("/aggregate/{symbol}/daily", response_model=AggregateResponse)
async def aggregate_to_daily(
    service: IntradayService = Depends(get_intraday_service),
    symbol: str = Path(...),
    trade_date: date | None = Query(None),
) -> AggregateResponse:
    count = await service.aggregate_to_daily(symbol, trade_date=trade_date)
    return AggregateResponse(bars_created=count)


@intraday_router.delete("/{symbol}", response_model=MessageResponse)
async def delete_bars(
    service: IntradayService = Depends(get_intraday_service),
    symbol: str = Path(...),
    resolution: str | None = Query(None, pattern=r"^(1min|5min|15min|hourly)$"),
) -> MessageResponse:
    count = await service.delete_bars(symbol, resolution=resolution)
    return MessageResponse(message=f"Deleted {count} bars")
