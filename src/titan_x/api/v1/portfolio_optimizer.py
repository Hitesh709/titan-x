from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.api import deps
from titan_x.models.user import User
from titan_x.services.portfolio_optimizer_service import PortfolioOptimizerService

router = APIRouter(prefix="/portfolio-optimizer", tags=["portfolio_optimizer"])


async def _get_service(
    session: AsyncSession = Depends(deps.get_session),
) -> PortfolioOptimizerService:
    return PortfolioOptimizerService(session)


def _opt_dict(o: Any) -> dict[str, Any]:
    return {
        "id": o.id,
        "portfolio_id": o.portfolio_id,
        "optimization_date": o.optimization_date.isoformat() if o.optimization_date else None,
        "strategy": o.strategy,
        "expected_return": o.expected_return,
        "expected_volatility": o.expected_volatility,
        "sharpe_ratio": o.sharpe_ratio,
        "diversification_score": o.diversification_score,
        "risk_score": o.risk_score,
        "sector_balance_score": o.sector_balance_score,
        "total_holdings": o.total_holdings,
    }


def _alloc_dict(a: Any) -> dict[str, Any]:
    return {
        "id": a.id,
        "symbol": a.symbol,
        "sector": a.sector,
        "allocation_pct": a.allocation_pct,
        "expected_return": a.expected_return,
        "expected_risk": a.expected_risk,
        "weight": a.weight,
        "rank": a.rank,
    }


@router.post("/optimize/{portfolio_id}", summary="Run portfolio optimization")
async def optimize(
    portfolio_id: int,
    strategy: str = Query("risk_parity"),
    service: PortfolioOptimizerService = Depends(_get_service),
    current_user: User = Depends(deps.get_current_active_superuser),
) -> dict[str, Any]:
    try:
        opt = await service.optimize(portfolio_id, strategy)
        allocations = await service.get_allocations(opt.id)
        return {
            "optimization": _opt_dict(opt),
            "allocations": [_alloc_dict(a) for a in allocations],
            "report": opt.report_json,
        }
    except ValueError as e:
        return {"error": str(e)}


@router.get("/optimizations/{optimization_id}", summary="Get optimization result")
async def get_optimization(
    optimization_id: int,
    service: PortfolioOptimizerService = Depends(_get_service),
) -> dict[str, Any]:
    opt = await service.get_optimization(optimization_id)
    if not opt:
        return {"error": "Optimization not found"}
    allocations = await service.get_allocations(optimization_id)
    return {
        "optimization": _opt_dict(opt),
        "allocations": [_alloc_dict(a) for a in allocations],
    }


@router.get("/history/{portfolio_id}", summary="Optimization history for a portfolio")
async def optimization_history(
    portfolio_id: int,
    limit: int = Query(20),
    service: PortfolioOptimizerService = Depends(_get_service),
) -> dict[str, Any]:
    history = await service.get_history(portfolio_id, limit)
    return {"total": len(history), "optimizations": [_opt_dict(o) for o in history]}
