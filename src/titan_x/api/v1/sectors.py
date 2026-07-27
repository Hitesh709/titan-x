from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from titan_x.api.dependencies import get_sector_engine, require_api_key
from titan_x.api.schemas import MessageResponse, PaginatedResponse
from titan_x.services.sector_engine import SectorEngine

sector_router = APIRouter(
    prefix="/sectors",
    tags=["sectors"],
    dependencies=[Depends(require_api_key)],
)


class PeriodPerformance(BaseModel):
    return_pct: float | None
    momentum_score: float | None
    relative_strength: float | None
    rank: int | None
    constituent_count: int | None
    ytd_return: float | None
    rotation_signal: str | None


class SectorRankingResponse(BaseModel):
    rank: int | None
    sector: str
    momentum_score: float | None
    relative_strength: float | None
    ytd_return: float | None
    constituent_count: int | None
    periods: dict[str, float | None]
    rotation_signal: str | None


class RotationResponse(BaseModel):
    as_of_date: str
    leading: list[dict]
    lagging: list[dict]
    neutral: list[dict]
    rotation_breadth: float


class HistoricalPerfResponse(BaseModel):
    as_of_date: str
    return_pct: float | None
    momentum_score: float | None
    relative_strength: float | None
    rank: int | None


class StoredPerfResponse(BaseModel):
    id: int
    sector: str
    as_of_date: date
    period_label: str
    return_pct: float | None
    momentum_score: float | None
    relative_strength: float | None
    rank: int | None
    constituent_count: int | None
    total_return_pct: float | None


@sector_router.get("", response_model=list[str])
async def list_sectors(
    engine: Annotated[SectorEngine, Depends(get_sector_engine)],
) -> list[str]:
    return await engine.list_all_sectors()


@sector_router.get("/ranking", response_model=list[SectorRankingResponse])
async def get_sector_ranking(
    engine: Annotated[SectorEngine, Depends(get_sector_engine)],
    as_of_date: date | None = Query(None),
) -> list[SectorRankingResponse]:
    results = await engine.get_ranking(as_of_date)
    return [SectorRankingResponse(**r) for r in results]


@sector_router.get("/rotation", response_model=RotationResponse)
async def get_sector_rotation(
    engine: Annotated[SectorEngine, Depends(get_sector_engine)],
    as_of_date: date | None = Query(None),
) -> RotationResponse:
    return await engine.get_rotation(as_of_date)


@sector_router.get("/{sector}/performance", response_model=PeriodPerformance)
async def get_sector_performance(
    sector: str,
    engine: Annotated[SectorEngine, Depends(get_sector_engine)],
    as_of_date: date | None = Query(None),
) -> PeriodPerformance:
    perf = await engine.compute_sector_performance(sector, as_of_date)
    return PeriodPerformance(
        return_pct=perf["periods"].get("1M"),
        momentum_score=perf.get("momentum_score"),
        relative_strength=perf.get("relative_strength"),
        rank=perf.get("rank"),
        constituent_count=perf.get("constituent_count"),
        ytd_return=perf.get("ytd_return"),
        rotation_signal=perf.get("rotation_signal"),
    )


@sector_router.get("/{sector}/historical", response_model=list[HistoricalPerfResponse])
async def get_sector_historical(
    sector: str,
    engine: Annotated[SectorEngine, Depends(get_sector_engine)],
    period_label: str = Query("1M", pattern=r"^(1W|1M|3M|6M|YTD|1Y|3Y|5Y)$"),
    limit: int = Query(20, ge=1, le=100),
) -> list[HistoricalPerfResponse]:
    results = await engine.get_historical_performance(sector, period_label, limit)
    return [HistoricalPerfResponse(**r) for r in results]


@sector_router.post("/compute", response_model=dict[str, int])
async def compute_all_sectors(
    engine: Annotated[SectorEngine, Depends(get_sector_engine)],
    as_of_date: date | None = Query(None),
) -> dict[str, int]:
    results = await engine.compute_all_sectors(as_of_date, store=True)
    return {"sectors_computed": len(results), "stored": sum(1 for r in results if r.get("momentum_score") is not None)}


@sector_router.get("/stored", response_model=PaginatedResponse[StoredPerfResponse])
async def get_stored_performance(
    engine: Annotated[SectorEngine, Depends(get_sector_engine)],
    sector: str | None = Query(None),
    period_label: str | None = Query(None, pattern=r"^(1W|1M|3M|6M|YTD|1Y|3Y|5Y)$"),
    as_of_date: date | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
) -> PaginatedResponse[StoredPerfResponse]:
    rows, total = await engine.get_stored_performance(
        sector, period_label=period_label, as_of_date=as_of_date,
        skip=skip, limit=limit,
    )
    items = [StoredPerfResponse(**r.__dict__) for r in rows]
    return PaginatedResponse(items=items, total=total, skip=skip, limit=limit)


@sector_router.delete("/stored/{perf_id}", response_model=MessageResponse)
async def delete_stored_performance(
    perf_id: int,
    engine: Annotated[SectorEngine, Depends(get_sector_engine)],
) -> MessageResponse:
    deleted = await engine._repo.delete(perf_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Performance record not found")
    return MessageResponse(message="Sector performance record deleted")


@sector_router.get("/{sector}/summary", response_model=dict)
async def get_sector_summary(
    sector: str,
    engine: Annotated[SectorEngine, Depends(get_sector_engine)],
) -> dict:
    return await engine.get_sector_summary(sector)
