from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.api import deps
from titan_x.models.user import User
from titan_x.services.ai_ranking_v2_service import AIRankingServiceV2

router = APIRouter(prefix="/ai-ranking-v2", tags=["ai_ranking_v2"])


async def _get_service(
    session: AsyncSession = Depends(deps.get_session),
) -> AIRankingServiceV2:
    return AIRankingServiceV2(session)


def _rank_dict(r: Any) -> dict[str, Any]:
    return {
        "id": r.id,
        "as_of_date": r.as_of_date.isoformat() if r.as_of_date else None,
        "rank": r.rank,
        "symbol": r.symbol,
        "company_name": r.company_name,
        "sector": r.sector,
        "weighted_ai_score": r.weighted_ai_score,
        "base_score": r.base_score,
        "technical_score": r.technical_score,
        "fundamental_score": r.fundamental_score,
        "sentiment_score": r.sentiment_score,
        "momentum_score": r.momentum_score,
        "dynamic_weight_technical": r.dynamic_weight_technical,
        "dynamic_weight_fundamental": r.dynamic_weight_fundamental,
        "dynamic_weight_sentiment": r.dynamic_weight_sentiment,
        "dynamic_weight_momentum": r.dynamic_weight_momentum,
        "model_confidence": r.model_confidence,
        "market_regime": r.market_regime,
        "regime_confidence": r.regime_confidence,
        "historical_success_rate": r.historical_success_rate,
        "historical_avg_return": r.historical_avg_return,
        "historical_sharpe": r.historical_sharpe,
        "tier": r.tier,
        "is_best_opportunity": r.is_best_opportunity,
    }


@router.post("/rank-all", summary="Run AI ranking V2 for all active symbols")
async def rank_all(
    as_of_date: date | None = None,
    service: AIRankingServiceV2 = Depends(_get_service),
    current_user: User = Depends(deps.get_current_active_superuser),
) -> dict[str, Any]:
    rankings = await service.rank_all(as_of_date)
    return {"ranked": len(rankings), "as_of_date": (as_of_date or date.today()).isoformat()}


@router.get("/rankings/{symbol}", summary="Get AI ranking V2 for a symbol")
async def get_ranking(
    symbol: str,
    as_of_date: date | None = None,
    service: AIRankingServiceV2 = Depends(_get_service),
) -> dict[str, Any]:
    r = await service.get_ranking(symbol.upper(), as_of_date)
    if not r:
        return {"error": "Ranking not found"}
    return _rank_dict(r)


@router.get("/top", summary="Get top ranked symbols")
async def get_top(
    limit: int = Query(20),
    as_of_date: date | None = None,
    service: AIRankingServiceV2 = Depends(_get_service),
) -> dict[str, Any]:
    rankings = await service.get_top(limit, as_of_date)
    return {"total": len(rankings), "rankings": [_rank_dict(r) for r in rankings]}


@router.get("/weights", summary="Get model weight history")
async def get_weights(
    model_name: str = Query("ensemble_v2"),
    service: AIRankingServiceV2 = Depends(_get_service),
) -> dict[str, Any]:
    weights = await service.get_weights(model_name)
    return {
        "model_name": model_name,
        "total": len(weights),
        "weights": [
            {
                "as_of_date": w.as_of_date.isoformat() if w.as_of_date else None,
                "weight_technical": w.weight_technical,
                "weight_fundamental": w.weight_fundamental,
                "weight_sentiment": w.weight_sentiment,
                "weight_momentum": w.weight_momentum,
                "market_regime": w.market_regime,
                "model_confidence": w.model_confidence,
            }
            for w in weights
        ],
    }
