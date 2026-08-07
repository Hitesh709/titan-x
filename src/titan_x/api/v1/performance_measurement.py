from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.api import deps
from titan_x.models.user import User
from titan_x.services.performance_measurement_service import PerformanceMeasurementService

router = APIRouter(prefix="/performance-measurement", tags=["performance_measurement"])


async def _get_service(
    session: AsyncSession = Depends(deps.get_session),
) -> PerformanceMeasurementService:
    return PerformanceMeasurementService(session)


def _snapshot_dict(s: Any) -> dict[str, Any]:
    return {
        "id": s.id,
        "snapshot_date": s.snapshot_date.isoformat() if s.snapshot_date else None,
        "period_label": s.period_label,
        "symbol": s.symbol,
        "total_trades": s.total_trades,
        "winning_trades": s.winning_trades,
        "losing_trades": s.losing_trades,
        "win_rate": s.win_rate,
        "accuracy": s.accuracy,
        "total_pnl": s.total_pnl,
        "total_pnl_pct": s.total_pnl_pct,
        "avg_return": s.avg_return,
        "avg_win": s.avg_win,
        "avg_loss": s.avg_loss,
        "best_trade": s.best_trade,
        "worst_trade": s.worst_trade,
        "profit_factor": s.profit_factor,
        "max_drawdown": s.max_drawdown,
        "max_drawdown_pct": s.max_drawdown_pct,
        "avg_drawdown_pct": s.avg_drawdown_pct,
        "sharpe_ratio": s.sharpe_ratio,
        "sortino_ratio": s.sortino_ratio,
        "calmar_ratio": s.calmar_ratio,
        "annualized_return_pct": s.annualized_return_pct,
        "avg_holding_days": s.avg_holding_days,
        "risk_free_rate": s.risk_free_rate,
    }


@router.post("/snapshot", summary="Take a performance measurement snapshot")
async def take_snapshot(
    snapshot_date: date | None = Query(None),
    symbol: str | None = Query(None),
    period_label: str = Query("all"),
    initial_capital: float = Query(100_000.0),
    risk_free_rate: float = Query(0.02),
    service: PerformanceMeasurementService = Depends(_get_service),
    current_user: User = Depends(deps.get_current_active_user),
):
    snapshot = await service.take_snapshot(
        user_id=current_user.id,
        snapshot_date=snapshot_date,
        symbol=symbol,
        period_label=period_label,
        initial_capital=initial_capital,
        risk_free_rate=risk_free_rate,
    )
    return {"snapshot": _snapshot_dict(snapshot)}


@router.get("/snapshots", summary="List performance snapshots")
async def list_snapshots(
    symbol: str | None = Query(None),
    period_label: str | None = Query(None),
    limit: int = Query(50),
    offset: int = Query(0),
    service: PerformanceMeasurementService = Depends(_get_service),
    current_user: User = Depends(deps.get_current_active_user),
):
    snapshots = await service.get_snapshots(
        user_id=current_user.id, symbol=symbol,
        period_label=period_label, limit=limit, offset=offset,
    )
    return {"total": await service.count_snapshots(user_id=current_user.id, symbol=symbol, period_label=period_label), "snapshots": [_snapshot_dict(s) for s in snapshots]}


@router.get("/snapshots/latest", summary="Get latest performance snapshot")
async def get_latest(
    symbol: str | None = Query(None),
    period_label: str | None = Query(None),
    service: PerformanceMeasurementService = Depends(_get_service),
    current_user: User = Depends(deps.get_current_active_user),
):
    snapshot = await service.get_latest(
        user_id=current_user.id, symbol=symbol, period_label=period_label,
    )
    if not snapshot:
        raise HTTPException(status_code=404, detail="No performance snapshot found")
    return {"snapshot": _snapshot_dict(snapshot)}


@router.get("/snapshots/{snapshot_id}", summary="Get a specific snapshot")
async def get_snapshot(
    snapshot_id: int,
    service: PerformanceMeasurementService = Depends(_get_service),
    current_user: User = Depends(deps.get_current_active_user),
):
    snapshot = await service.get_snapshot(snapshot_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    if snapshot.user_id != current_user.id and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Not your snapshot")
    return {"snapshot": _snapshot_dict(snapshot)}


@router.get("/trend", summary="Get performance trend over recent snapshots")
async def get_trend(
    symbol: str | None = Query(None),
    limit: int = Query(30),
    service: PerformanceMeasurementService = Depends(_get_service),
    current_user: User = Depends(deps.get_current_active_user),
):
    trend = await service.get_trend(
        user_id=current_user.id, symbol=symbol, limit=limit,
    )
    return {"trend": trend}
