from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.api import deps
from titan_x.models.user import User
from titan_x.services.opportunity_rejection_service import OpportunityRejectionService

router = APIRouter(prefix="/opportunity-rejection", tags=["opportunity_rejection"])


async def _get_service(
    session: AsyncSession = Depends(deps.get_session),
) -> OpportunityRejectionService:
    return OpportunityRejectionService(session)


def _orj_dict(o: Any) -> dict[str, Any]:
    return {
        "id": o.id,
        "symbol": o.symbol,
        "trade_date": o.trade_date.isoformat() if o.trade_date else None,
        "direction": o.direction,
        "scores": {
            "liquidity": o.liquidity_score,
            "risk": o.risk_score,
            "news": o.news_score,
            "financial": o.financial_score,
            "trend": o.trend_score,
            "market": o.market_score,
        },
        "reasons": {
            "liquidity": o.liquidity_reason,
            "risk": o.risk_reason,
            "news": o.news_reason,
            "financial": o.financial_reason,
            "trend": o.trend_reason,
            "market": o.market_reason,
        },
        "composite_score": o.composite_score,
        "is_rejected": o.is_rejected,
        "rejection_reason": o.rejection_reason,
    }


@router.post("/evaluate/{symbol}", summary="Evaluate an opportunity and generate rejection reason")
async def evaluate(
    symbol: str,
    direction: str = Query("bullish"),
    service: OpportunityRejectionService = Depends(_get_service),
    current_user: User = Depends(deps.get_current_active_superuser),
) -> dict[str, Any]:
    result = await service.evaluate(symbol=symbol, direction=direction)
    return {"evaluation": _orj_dict(result)}


@router.get("/evaluations/{symbol}", summary="Get evaluation history for a symbol")
async def get_evaluations(
    symbol: str,
    limit: int = Query(20),
    offset: int = Query(0),
    service: OpportunityRejectionService = Depends(_get_service),
) -> dict[str, Any]:
    evals = await service.get_evaluations(symbol, limit=limit, offset=offset)
    return {"total": len(evals), "evaluations": [_orj_dict(e) for e in evals]}


@router.get("/{evaluation_id}", summary="Get a specific evaluation")
async def get_evaluation(
    evaluation_id: int,
    service: OpportunityRejectionService = Depends(_get_service),
) -> dict[str, Any]:
    ev = await service.get_evaluation(evaluation_id)
    if not ev:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evaluation not found")
    return {"evaluation": _orj_dict(ev)}
