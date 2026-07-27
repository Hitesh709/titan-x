from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.api.dependencies import get_current_active_user, get_db
from titan_x.models.user import User
from titan_x.services.ranking_service import RankingService

router = APIRouter(prefix="/rankings", tags=["rankings"])


@router.post("/run")
async def run_ranking(
    as_of_date: date | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    svc = RankingService(db)
    rankings = await svc.rank_all(as_of_date)
    top5 = [r for r in rankings if r.tier == "top_5"]
    return {
        "total_ranked": len(rankings),
        "as_of_date": (as_of_date or date.today()).isoformat(),
        "summary": {
            "top_5": len(top5),
            "top_10": sum(1 for r in rankings if r.tier == "top_10"),
            "top_25": sum(1 for r in rankings if r.tier == "top_25"),
            "top_50": sum(1 for r in rankings if r.tier == "top_50"),
            "top_100": sum(1 for r in rankings if r.tier == "top_100"),
        },
    }


@router.get("/top/{tier}")
async def get_top_rankings(
    tier: str = Path(..., pattern="^(top_5|top_10|top_25|top_50|top_100)$"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    as_of_date: date | None = Query(None),
):
    svc = RankingService(db)
    results = await svc.get_top(tier, as_of_date)
    return [
        {
            "rank": r.rank,
            "symbol": r.symbol,
            "company_name": r.company_name,
            "sector": r.sector,
            "composite_score": r.composite_score,
            "risk_adjusted_score": r.risk_adjusted_score,
            "financial_health": r.financial_health_score,
            "valuation": r.valuation_score,
            "momentum": r.momentum_score,
            "liquidity": r.liquidity_score,
            "corporate": r.corporate_score,
            "institutional": r.institutional_score,
            "tier": r.tier,
            "is_best_opportunity": r.is_best_opportunity,
        }
        for r in results
    ]


@router.get("/best-opportunity")
async def get_best_opportunity(
    as_of_date: date | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    svc = RankingService(db)
    result = await svc.get_best_opportunity(as_of_date)
    if not result:
        raise HTTPException(404, "No ranking data available")
    return {
        "rank": result.rank,
        "symbol": result.symbol,
        "company_name": result.company_name,
        "composite_score": result.composite_score,
        "risk_adjusted_score": result.risk_adjusted_score,
        "tier": result.tier,
        "explanation": result.explanation_json,
    }


@router.get("/{symbol}")
async def get_stock_ranking(
    symbol: str,
    as_of_date: date | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    svc = RankingService(db)
    result = await svc.get_ranking(symbol.upper(), as_of_date)
    if not result:
        raise HTTPException(404, "Stock not ranked")
    return {
        "rank": result.rank,
        "symbol": result.symbol,
        "company_name": result.company_name,
        "sector": result.sector,
        "composite_score": result.composite_score,
        "risk_adjusted_score": result.risk_adjusted_score,
        "tier": result.tier,
        "is_best_opportunity": result.is_best_opportunity,
        "explanation": result.explanation_json,
    }
