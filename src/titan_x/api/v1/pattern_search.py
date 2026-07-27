from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.api import deps
from titan_x.models.user import User
from titan_x.services.pattern_search_service import PatternSearchService

router = APIRouter(prefix="/pattern-search", tags=["pattern_search"])


async def _get_service(
    session: AsyncSession = Depends(deps.get_session),
) -> PatternSearchService:
    return PatternSearchService(session)


def _query_dict(q: Any) -> dict[str, Any]:
    return {
        "id": q.id,
        "symbol": q.symbol,
        "pattern_type": q.pattern_type,
        "window_days": q.window_days,
        "total_matches": q.total_matches,
        "avg_similarity": q.avg_similarity,
        "best_similarity": q.best_similarity,
        "avg_return": q.avg_return,
        "avg_loss": q.avg_loss,
        "win_rate": q.win_rate,
        "avg_return_5d": q.avg_return_5d,
        "avg_return_10d": q.avg_return_10d,
        "avg_return_20d": q.avg_return_20d,
        "avg_return_60d": q.avg_return_60d,
        "optimal_holding_days": q.optimal_holding_days,
    }


def _match_dict(m: Any) -> dict[str, Any]:
    return {
        "id": m.id,
        "match_rank": m.match_rank,
        "match_symbol": m.match_symbol,
        "match_start_date": m.match_start_date.isoformat() if m.match_start_date else None,
        "match_end_date": m.match_end_date.isoformat() if m.match_end_date else None,
        "similarity_score": m.similarity_score,
        "price_correlation": m.price_correlation,
        "price_distance": m.price_distance,
        "volume_similarity": m.volume_similarity,
        "forward_return_1d": m.forward_return_1d,
        "forward_return_5d": m.forward_return_5d,
        "forward_return_10d": m.forward_return_10d,
        "forward_return_20d": m.forward_return_20d,
        "forward_return_60d": m.forward_return_60d,
        "is_winning": m.is_winning,
    }


@router.post("/search", summary="Search historical patterns matching a query window")
async def search(
    symbol: str, pattern_type: str = "price",
    start_date: date = Query(...), end_date: date = Query(...),
    window_days: int = Query(20), lookback_years: int = Query(30),
    min_similarity: float = Query(0.8), max_matches: int = Query(50),
    service: PatternSearchService = Depends(_get_service),
    current_user: User = Depends(deps.get_current_active_superuser),
) -> dict[str, Any]:
    query = await service.search(symbol.upper(), pattern_type, start_date, end_date,
                                 window_days, lookback_years, min_similarity, max_matches)
    matches = await service.get_matches(query.id)
    return {
        "query": _query_dict(query),
        "matches": [_match_dict(m) for m in matches],
        "total_matches": len(matches),
    }


@router.get("/queries/{query_id}", summary="Get a pattern search query")
async def get_query(
    query_id: int,
    service: PatternSearchService = Depends(_get_service),
) -> dict[str, Any]:
    q = await service.get_query(query_id)
    if not q:
        return {"error": "Query not found"}
    return _query_dict(q)


@router.get("/queries/{query_id}/matches", summary="Get matches for a query")
async def get_matches(
    query_id: int,
    service: PatternSearchService = Depends(_get_service),
) -> dict[str, Any]:
    matches = await service.get_matches(query_id)
    return {"query_id": query_id, "total": len(matches), "matches": [_match_dict(m) for m in matches]}


@router.get("/history", summary="Search history")
async def search_history(
    symbol: str | None = Query(None),
    limit: int = Query(20),
    service: PatternSearchService = Depends(_get_service),
) -> dict[str, Any]:
    queries = await service.get_history(symbol, limit)
    return {"total": len(queries), "queries": [_query_dict(q) for q in queries]}
