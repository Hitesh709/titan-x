from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.api.dependencies import get_current_active_user, get_db
from titan_x.models.user import User
from titan_x.services.global_market_service import GlobalMarketService

router = APIRouter(prefix="/global-markets", tags=["global-markets"])


class DataCreate(BaseModel):
    data_type: str
    region: str
    symbol: str
    as_of_date: date
    value: float
    change_pct: float | None = None
    source: str | None = None


@router.post("/data")
async def record_data(body: DataCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    svc = GlobalMarketService(db)
    result = await svc.record_data(body.data_type, body.region, body.symbol, body.as_of_date, body.value, body.change_pct, body.source)
    return result


@router.get("/data")
async def list_data(
    region: str | None = Query(None), data_type: str | None = Query(None), limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user),
):
    svc = GlobalMarketService(db)
    return await svc.list_data(region, data_type, limit)


@router.get("/data/{symbol}/latest")
async def get_latest_data(symbol: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    svc = GlobalMarketService(db)
    result = await svc.get_data(symbol.upper())
    if not result:
        raise HTTPException(404, f"No data for {symbol}")
    return result


@router.post("/analyze")
async def analyze_global(
    as_of_date: date | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    svc = GlobalMarketService(db)
    result = await svc.analyze(as_of_date)
    return {
        "id": result.id,
        "as_of_date": result.as_of_date.isoformat(),
        "us_score": result.us_score,
        "europe_score": result.europe_score,
        "asia_score": result.asia_score,
        "futures_score": result.futures_score,
        "vix_score": result.vix_score,
        "dxy_score": result.dxy_score,
        "global_score": result.global_score,
        "global_sentiment": result.global_sentiment,
    }


@router.get("/analyze")
async def get_analysis(
    as_of_date: date | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    svc = GlobalMarketService(db)
    result = await svc.get_analysis(as_of_date)
    if not result:
        raise HTTPException(404, "Analysis not found")
    return result


@router.get("/analyze/history")
async def list_analyses(
    limit: int = Query(30, le=100), offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user),
):
    svc = GlobalMarketService(db)
    return await svc.list_analyses(limit, offset)


@router.post("/conditions")
async def build_condition(
    as_of_date: date | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    svc = GlobalMarketService(db)
    result = await svc.build_condition_snapshot(as_of_date)
    return {
        "id": result.id,
        "snapshot_date": result.snapshot_date.isoformat(),
        "feature_vector": result.feature_vector,
        "region_scores": result.region_scores_json,
        "outcomes": result.outcome_returns_json,
    }


@router.post("/search-similar")
async def search_similar(
    as_of_date: date | None = Query(None),
    top_n: int = Query(5, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    svc = GlobalMarketService(db)
    results = await svc.search_similar(as_of_date, top_n)
    return [
        {
            "id": r.id,
            "query_date": r.query_date.isoformat(),
            "matched_date": r.matched_date.isoformat(),
            "similarity_pct": r.similarity_pct,
            "avg_return_1d": r.avg_return_1d,
            "avg_return_5d": r.avg_return_5d,
            "avg_return_20d": r.avg_return_20d,
            "avg_return_60d": r.avg_return_60d,
            "winning_stocks": r.winning_stocks_json,
            "losing_stocks": r.losing_stocks_json,
            "historical_outcomes": r.historical_outcomes_json,
        }
        for r in results
    ]


@router.get("/search-similar")
async def get_similarity_results(
    query_date: date | None = Query(None), limit: int = Query(10, le=50),
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user),
):
    svc = GlobalMarketService(db)
    return await svc.get_similarity_results(query_date, limit)
