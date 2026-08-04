from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from titan_x.api.dependencies import get_market_breadth_engine, require_api_key
from titan_x.api.schemas import MessageResponse, PaginatedResponse
from titan_x.services.market_breadth_engine import MarketBreadthEngine

market_breadth_router = APIRouter(
    prefix="/market-breadth",
    tags=["market-breadth"],
    dependencies=[Depends(require_api_key)],
)


class BreadthSummaryResponse(BaseModel):
    trade_date: str
    advancing: int
    declining: int
    advance_decline_ratio: float | None
    advance_decline_line: float | None
    new_highs: int
    new_lows: int
    advancing_volume: int
    declining_volume: int
    volume_breadth_ratio: float | None
    breadth_oscillator: float | None
    index_strength_score: float | None


class BreadthDetailResponse(BaseModel):
    trade_date: str
    advancing: int
    declining: int
    unchanged: int
    total_stocks: int
    advancing_volume: int
    declining_volume: int
    unchanged_volume: int
    total_volume: int
    new_highs: int
    new_lows: int
    advance_decline_ratio: float | None
    advance_decline_line: float | None
    volume_breadth_ratio: float | None
    breadth_oscillator: float | None
    index_strength_score: float | None


class ADLinePoint(BaseModel):
    trade_date: str
    advance_decline_line: float | None


class OscillatorPoint(BaseModel):
    trade_date: str
    breadth_oscillator: float | None


class HighLowPoint(BaseModel):
    trade_date: str
    new_highs: int
    new_lows: int


class VolumeBreadthPoint(BaseModel):
    trade_date: str
    advancing_volume: int
    declining_volume: int
    volume_breadth_ratio: float | None


class StoredBreadthResponse(BaseModel):
    id: int
    trade_date: date
    advancing: int
    declining: int
    unchanged: int
    total_stocks: int
    advancing_volume: int
    declining_volume: int
    unchanged_volume: int
    total_volume: int
    new_highs: int
    new_lows: int
    advance_decline_ratio: float | None
    advance_decline_line: float | None
    volume_breadth_ratio: float | None
    breadth_oscillator: float | None
    index_strength_score: float | None


@market_breadth_router.get("/summary", response_model=BreadthSummaryResponse)
async def get_breadth_summary(
    engine: Annotated[MarketBreadthEngine, Depends(get_market_breadth_engine)],
    as_of_date: date | None = Query(None),
) -> BreadthSummaryResponse:
    result = await engine.get_breadth_summary(as_of_date)
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No breadth data found")
    return BreadthSummaryResponse(**result)


@market_breadth_router.post("/compute", response_model=BreadthDetailResponse)
async def compute_market_breadth(
    engine: Annotated[MarketBreadthEngine, Depends(get_market_breadth_engine)],
    trade_date: date = Query(...),
) -> BreadthDetailResponse:
    try:
        result = await engine.compute_and_store(trade_date)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return BreadthDetailResponse(**result)


@market_breadth_router.get("/advance-decline", response_model=ADLinePoint)
async def get_advance_decline(
    engine: Annotated[MarketBreadthEngine, Depends(get_market_breadth_engine)],
    as_of_date: date | None = Query(None),
) -> ADLinePoint:
    summary = await engine.get_breadth_summary(as_of_date)
    if not summary:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No breadth data found")
    return ADLinePoint(
        trade_date=summary["trade_date"],
        advance_decline_line=summary["advance_decline_line"],
    )


@market_breadth_router.get("/advance-decline/line", response_model=list[ADLinePoint])
async def get_ad_line_history(
    engine: Annotated[MarketBreadthEngine, Depends(get_market_breadth_engine)],
    limit: int = Query(100, ge=1, le=500),
) -> list[ADLinePoint]:
    return await engine.get_advance_decline_line(limit)


@market_breadth_router.get("/high-low", response_model=HighLowPoint)
async def get_high_low(
    engine: Annotated[MarketBreadthEngine, Depends(get_market_breadth_engine)],
    as_of_date: date | None = Query(None),
) -> HighLowPoint:
    summary = await engine.get_breadth_summary(as_of_date)
    if not summary:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No breadth data found")
    return HighLowPoint(
        trade_date=summary["trade_date"],
        new_highs=summary["new_highs"],
        new_lows=summary["new_lows"],
    )


@market_breadth_router.get("/high-low/history", response_model=list[HighLowPoint])
async def get_high_low_history(
    engine: Annotated[MarketBreadthEngine, Depends(get_market_breadth_engine)],
    limit: int = Query(100, ge=1, le=500),
) -> list[HighLowPoint]:
    return await engine.get_high_low_data(limit)


@market_breadth_router.get("/volume-breadth", response_model=VolumeBreadthPoint)
async def get_volume_breadth(
    engine: Annotated[MarketBreadthEngine, Depends(get_market_breadth_engine)],
    as_of_date: date | None = Query(None),
) -> VolumeBreadthPoint:
    summary = await engine.get_breadth_summary(as_of_date)
    if not summary:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No breadth data found")
    return VolumeBreadthPoint(
        trade_date=summary["trade_date"],
        advancing_volume=summary["advancing_volume"],
        declining_volume=summary["declining_volume"],
        volume_breadth_ratio=summary["volume_breadth_ratio"],
    )


@market_breadth_router.get("/volume-breadth/history", response_model=list[VolumeBreadthPoint])
async def get_volume_breadth_history(
    engine: Annotated[MarketBreadthEngine, Depends(get_market_breadth_engine)],
    limit: int = Query(100, ge=1, le=500),
) -> list[VolumeBreadthPoint]:
    return await engine.get_volume_breadth_data(limit)


@market_breadth_router.get("/oscillator", response_model=OscillatorPoint)
async def get_breadth_oscillator(
    engine: Annotated[MarketBreadthEngine, Depends(get_market_breadth_engine)],
    as_of_date: date | None = Query(None),
) -> OscillatorPoint:
    summary = await engine.get_breadth_summary(as_of_date)
    if not summary:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No breadth data found")
    return OscillatorPoint(
        trade_date=summary["trade_date"],
        breadth_oscillator=summary["breadth_oscillator"],
    )


@market_breadth_router.get("/oscillator/history", response_model=list[OscillatorPoint])
async def get_oscillator_history(
    engine: Annotated[MarketBreadthEngine, Depends(get_market_breadth_engine)],
    limit: int = Query(100, ge=1, le=500),
) -> list[OscillatorPoint]:
    return await engine.get_oscillator_history(limit)


@market_breadth_router.get("/index-strength", response_model=dict)
async def get_index_strength(
    engine: Annotated[MarketBreadthEngine, Depends(get_market_breadth_engine)],
    as_of_date: date | None = Query(None),
) -> dict:
    summary = await engine.get_breadth_summary(as_of_date)
    if not summary:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No breadth data found")
    return {
        "trade_date": summary["trade_date"],
        "index_strength_score": summary["index_strength_score"],
    }


@market_breadth_router.get("/historical", response_model=PaginatedResponse[StoredBreadthResponse])
async def get_historical_breadth(
    engine: Annotated[MarketBreadthEngine, Depends(get_market_breadth_engine)],
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
) -> PaginatedResponse[StoredBreadthResponse]:
    rows, total = await engine.get_historical(start_date, end_date, skip, limit)
    items = [StoredBreadthResponse(**r.__dict__) for r in rows]
    return PaginatedResponse(items=items, total=total, skip=skip, limit=limit)


@market_breadth_router.delete("/{trade_date}", response_model=MessageResponse)
async def delete_breadth(
    trade_date: date,
    engine: Annotated[MarketBreadthEngine, Depends(get_market_breadth_engine)],
) -> MessageResponse:
    deleted = await engine.delete(trade_date)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Breadth data not found")
    return MessageResponse(message="Market breadth data deleted")
