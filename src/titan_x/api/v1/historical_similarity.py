from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from titan_x.api.dependencies import get_historical_similarity_engine, require_api_key
from titan_x.api.schemas import MessageResponse, PaginatedResponse
from titan_x.services.historical_similarity_engine import HistoricalSimilarityEngine

hist_sim_router = APIRouter(
    prefix="/historical-similarity",
    tags=["historical-similarity"],
    dependencies=[Depends(require_api_key)],
)


class MatchResult(BaseModel):
    match_rank: int | None = None
    match_symbol: str | None = None
    match_start_date: str
    match_end_date: str
    similarity_score: float
    price_correlation: float | None
    price_distance: float | None
    volume_similarity: float | None
    forward_return_1d: float | None = None
    forward_return_5d: float | None = None
    forward_return_10d: float | None = None
    forward_return_20d: float | None = None
    forward_return_60d: float | None = None


class SearchStatistics(BaseModel):
    total_matches: int
    avg_similarity: float | None
    best_similarity: float | None
    worst_similarity: float | None
    avg_return_1d: float | None = None
    avg_return_5d: float | None = None
    avg_return_10d: float | None = None
    avg_return_20d: float | None = None
    avg_return_60d: float | None = None
    avg_holding_period: float | None = None
    optimal_holding_period: int | None = None
    optimal_return: float | None = None


class SearchResponse(BaseModel):
    symbol: str
    query_end_date: str
    query_window_days: int | None = None
    query_close_range: dict | None = None
    total_candidates: int | None = None
    matches: list[MatchResult]
    statistics: SearchStatistics | None
    error: str | None = None


class AnalysisResponse(BaseModel):
    id: int
    symbol: str
    query_start_date: date
    query_end_date: date
    window_days: int
    lookback_days: int
    max_matches: int
    min_similarity: float
    total_matches: int
    avg_similarity: float | None
    best_similarity: float | None
    worst_similarity: float | None
    avg_return_1d: float | None
    avg_return_5d: float | None
    avg_return_10d: float | None
    avg_return_20d: float | None
    avg_return_60d: float | None
    avg_holding_period: float | None
    optimal_holding_period: int | None
    optimal_return: float | None


class MatchResponse(BaseModel):
    id: int
    analysis_id: int
    match_rank: int
    match_symbol: str
    match_start_date: date
    match_end_date: date
    similarity_score: float
    price_correlation: float | None
    price_distance: float | None
    volume_similarity: float | None
    forward_return_1d: float | None
    forward_return_5d: float | None
    forward_return_10d: float | None
    forward_return_20d: float | None
    forward_return_60d: float | None


@hist_sim_router.post("/search/{symbol}", response_model=SearchResponse)
async def search_similar(
    symbol: str,
    engine: Annotated[HistoricalSimilarityEngine, Depends(get_historical_similarity_engine)],
    end_date: date | None = Query(None),
    window_days: int = Query(20, ge=5, le=100),
    lookback_days: int = Query(3650, ge=100, le=7300),
    max_matches: int = Query(50, ge=1, le=200),
    min_similarity: float = Query(0.0, ge=0.0, le=1.0),
    store: bool = Query(False),
) -> SearchResponse:
    result = await engine.search(symbol, end_date, window_days, lookback_days, max_matches, min_similarity, store)
    return SearchResponse(**result)


@hist_sim_router.post("/search-cross", response_model=dict)
async def search_cross_symbol(
    symbol: str,
    engine: Annotated[HistoricalSimilarityEngine, Depends(get_historical_similarity_engine)],
    compare_symbols: str = Query(..., description="Comma-separated symbols"),
    end_date: date | None = Query(None),
    window_days: int = Query(20, ge=5, le=100),
    lookback_days: int = Query(3650, ge=100, le=7300),
    max_matches: int = Query(50, ge=1, le=200),
    min_similarity: float = Query(0.0, ge=0.0, le=1.0),
) -> dict:
    symbols = [s.strip() for s in compare_symbols.split(",") if s.strip()]
    return await engine.search_cross_symbol(symbol, symbols, end_date, window_days, lookback_days, max_matches, min_similarity)


@hist_sim_router.get("/analyses", response_model=PaginatedResponse[AnalysisResponse])
async def list_analyses(
    engine: Annotated[HistoricalSimilarityEngine, Depends(get_historical_similarity_engine)],
    symbol: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
) -> PaginatedResponse[AnalysisResponse]:
    rows, total = await engine.get_analyses(symbol, skip, limit)
    items = [AnalysisResponse(**r.__dict__) for r in rows]
    return PaginatedResponse(items=items, total=total, skip=skip, limit=limit)


@hist_sim_router.get("/analyses/{analysis_id}", response_model=AnalysisResponse)
async def get_analysis(
    analysis_id: int,
    engine: Annotated[HistoricalSimilarityEngine, Depends(get_historical_similarity_engine)],
) -> AnalysisResponse:
    analysis = await engine.get_analysis_by_id(analysis_id)
    if analysis is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis not found")
    return AnalysisResponse(**analysis.__dict__)


@hist_sim_router.get("/analyses/{analysis_id}/matches", response_model=PaginatedResponse[MatchResponse])
async def get_analysis_matches(
    analysis_id: int,
    engine: Annotated[HistoricalSimilarityEngine, Depends(get_historical_similarity_engine)],
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
) -> PaginatedResponse[MatchResponse]:
    analysis = await engine.get_analysis_by_id(analysis_id)
    if analysis is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis not found")
    rows, total = await engine.get_matches_for_analysis(analysis_id, skip, limit)
    items = [MatchResponse(**r.__dict__) for r in rows]
    return PaginatedResponse(items=items, total=total, skip=skip, limit=limit)


@hist_sim_router.post("/analyses/{analysis_id}/recalculate", response_model=dict)
async def recalculate_analysis(
    analysis_id: int,
    engine: Annotated[HistoricalSimilarityEngine, Depends(get_historical_similarity_engine)],
) -> dict:
    return await engine.calculate_forward_returns_for_analysis(analysis_id)


@hist_sim_router.delete("/analyses/{analysis_id}", response_model=MessageResponse)
async def delete_analysis(
    analysis_id: int,
    engine: Annotated[HistoricalSimilarityEngine, Depends(get_historical_similarity_engine)],
) -> MessageResponse:
    deleted = await engine.delete_analysis(analysis_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis not found")
    return MessageResponse(message="Analysis deleted")
