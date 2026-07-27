import json
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from titan_x.api.dependencies import (
    get_backtest_engine,
    get_current_active_user,
    require_api_key,
)
from titan_x.api.schemas import MessageResponse, PaginatedResponse
from titan_x.models.user import User
from titan_x.services.backtest_engine import BacktestEngine
from titan_x.services.optimization_engine import OptimizationEngine
from titan_x.services.strategy_builder import StrategyBuilder
from titan_x.services.strategy_service import StrategyService
from titan_x.services.strategy_execution_service import StrategyExecutionService

strategy_router = APIRouter(
    prefix="/strategies",
    tags=["strategies"],
    dependencies=[Depends(require_api_key)],
)


def _get_strategy_builder(
    engine: Annotated[BacktestEngine, Depends(get_backtest_engine)],
) -> StrategyBuilder:
    return StrategyBuilder(engine._session)


def _get_optimization_engine(
    engine: Annotated[BacktestEngine, Depends(get_backtest_engine)],
) -> OptimizationEngine:
    return OptimizationEngine(engine._session)


def _get_strategy_service(
    engine: Annotated[BacktestEngine, Depends(get_backtest_engine)],
) -> StrategyService:
    return StrategyService(engine._session)


def _get_execution_service(
    engine: Annotated[BacktestEngine, Depends(get_backtest_engine)],
) -> StrategyExecutionService:
    return StrategyExecutionService(engine._session)


@strategy_router.post("", status_code=status.HTTP_201_CREATED)
async def create_strategy(
    builder: Annotated[StrategyBuilder, Depends(_get_strategy_builder)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    name: str = Query(..., min_length=1, max_length=256),
    description: str | None = Query(None, max_length=1000),
    entry_criteria: str = Query("[]"),
    exit_criteria: str = Query("[]"),
    risk_rules: str = Query("{}"),
    position_rules: str = Query("{}"),
    tags: str = Query("[]"),
) -> dict:
    result = await builder.create_strategy(
        user_id=current_user.id,
        name=name,
        description=description,
        entry_criteria=json.loads(entry_criteria),
        exit_criteria=json.loads(exit_criteria),
        risk_rules=json.loads(risk_rules),
        position_rules=json.loads(position_rules),
        tags=json.loads(tags),
    )
    return result


@strategy_router.get("")
async def list_strategies(
    builder: Annotated[StrategyBuilder, Depends(_get_strategy_builder)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
) -> PaginatedResponse[dict]:
    rows, total = await builder.list_strategies(user_id=current_user.id, skip=skip, limit=limit)
    items = [{
        "id": r.id,
        "name": r.name,
        "description": r.description,
        "version": r.version,
        "is_active": r.is_active,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    } for r in rows]
    return PaginatedResponse(items=items, total=total, skip=skip, limit=limit)


@strategy_router.get("/{strategy_id}")
async def get_strategy(
    strategy_id: int,
    builder: Annotated[StrategyBuilder, Depends(_get_strategy_builder)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> dict:
    result = await builder.get_strategy(strategy_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found")
    return result


@strategy_router.put("/{strategy_id}")
async def update_strategy(
    strategy_id: int,
    builder: Annotated[StrategyBuilder, Depends(_get_strategy_builder)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    name: str | None = Query(None, min_length=1, max_length=256),
    description: str | None = Query(None, max_length=1000),
    entry_criteria: str | None = Query(None),
    exit_criteria: str | None = Query(None),
    risk_rules: str | None = Query(None),
    position_rules: str | None = Query(None),
    tags: str | None = Query(None),
    is_active: bool | None = Query(None),
) -> dict:
    result = await builder.update_strategy(
        strategy_id=strategy_id,
        name=name,
        description=description,
        entry_criteria=json.loads(entry_criteria) if entry_criteria else None,
        exit_criteria=json.loads(exit_criteria) if exit_criteria else None,
        risk_rules=json.loads(risk_rules) if risk_rules else None,
        position_rules=json.loads(position_rules) if position_rules else None,
        tags=json.loads(tags) if tags else None,
        is_active=is_active,
    )
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found")
    return result


@strategy_router.delete("/{strategy_id}", response_model=MessageResponse)
async def delete_strategy(
    strategy_id: int,
    builder: Annotated[StrategyBuilder, Depends(_get_strategy_builder)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> MessageResponse:
    deleted = await builder.delete_strategy(strategy_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found")
    return MessageResponse(message="Strategy deleted")


@strategy_router.post("/{strategy_id}/backtest", status_code=status.HTTP_201_CREATED)
async def run_strategy_backtest(
    strategy_id: int,
    builder: Annotated[StrategyBuilder, Depends(_get_strategy_builder)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    symbol: str = Query(..., min_length=1, max_length=16),
    start_date: date = Query(...),
    end_date: date = Query(...),
    initial_capital: float = Query(10000.0, gt=0),
    commission_pct: float = Query(0.001, ge=0),
    slippage_pct: float = Query(0.001, ge=0),
) -> dict:
    try:
        result = await builder.run_backtest(
            strategy_id=strategy_id,
            user_id=current_user.id,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
            commission_pct=commission_pct,
            slippage_pct=slippage_pct,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@strategy_router.post("/{strategy_id}/optimize", status_code=status.HTTP_201_CREATED)
async def optimize_strategy(
    strategy_id: int,
    optimizer: Annotated[OptimizationEngine, Depends(_get_optimization_engine)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    symbol: str = Query(..., min_length=1, max_length=16),
    start_date: date = Query(...),
    end_date: date = Query(...),
    parameter_ranges: str = Query(...),
    metric: str = Query("sharpe_ratio"),
    direction: str = Query("maximize", pattern="^(maximize|minimize)$"),
    initial_capital: float = Query(10000.0, gt=0),
    commission_pct: float = Query(0.001, ge=0),
    slippage_pct: float = Query(0.001, ge=0),
) -> dict:
    try:
        result = await optimizer.run_optimization(
            strategy_id=strategy_id,
            user_id=current_user.id,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            parameter_ranges=json.loads(parameter_ranges),
            metric=metric,
            direction=direction,
            initial_capital=initial_capital,
            commission_pct=commission_pct,
            slippage_pct=slippage_pct,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@strategy_router.get("/optimizations/{opt_id}")
async def get_optimization(
    opt_id: int,
    optimizer: Annotated[OptimizationEngine, Depends(_get_optimization_engine)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> dict:
    result = await optimizer.get_optimization(opt_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Optimization not found")
    return result


@strategy_router.get("/{strategy_id}/optimizations")
async def list_optimizations(
    strategy_id: int,
    optimizer: Annotated[OptimizationEngine, Depends(_get_optimization_engine)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
) -> PaginatedResponse[dict]:
    rows, total = await optimizer.list_optimizations(strategy_id=strategy_id, skip=skip, limit=limit)
    items = [{
        "id": r.id,
        "symbol": r.symbol,
        "metric": r.metric,
        "direction": r.direction,
        "total_combinations": r.total_combinations,
        "completed_combinations": r.completed_combinations,
        "best_score": r.best_score,
        "status": r.status,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r in rows]
    return PaginatedResponse(items=items, total=total, skip=skip, limit=limit)


# ── Clone, Share, Run, Schedule ──


@strategy_router.post("/{strategy_id}/clone", status_code=status.HTTP_201_CREATED)
async def clone_strategy(
    strategy_id: int,
    svc: Annotated[StrategyService, Depends(_get_strategy_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    name: str | None = Query(None, min_length=1, max_length=256),
) -> dict:
    result = await svc.clone_strategy(strategy_id, current_user.id, name)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found or access denied")
    return result


@strategy_router.put("/{strategy_id}/schedule")
async def set_strategy_schedule(
    strategy_id: int,
    svc: Annotated[StrategyService, Depends(_get_strategy_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    cron: str = Query(..., min_length=1, max_length=64),
    enabled: bool = Query(True),
) -> dict:
    result = await svc.set_schedule(strategy_id, current_user.id, cron, enabled)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found")
    return result


@strategy_router.put("/{strategy_id}/schedule/disable")
async def disable_strategy_schedule(
    strategy_id: int,
    svc: Annotated[StrategyService, Depends(_get_strategy_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> dict:
    result = await svc.set_schedule(strategy_id, current_user.id, None, False)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found")
    return result


@strategy_router.post("/{strategy_id}/run")
async def run_strategy(
    strategy_id: int,
    svc: Annotated[StrategyService, Depends(_get_strategy_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
) -> dict:
    result = await svc.run_strategy(strategy_id, current_user.id, skip, limit)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found or access denied")
    return result


@strategy_router.post("/{strategy_id}/share", status_code=status.HTTP_201_CREATED)
async def share_strategy(
    strategy_id: int,
    svc: Annotated[StrategyService, Depends(_get_strategy_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    target_user_id: int = Query(...),
    permission: str = Query("view", pattern="^(view|run|edit)$"),
) -> dict:
    result = await svc.share_strategy(strategy_id, current_user.id, target_user_id, permission)
    if result is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot share or strategy not found")
    return result


@strategy_router.delete("/{strategy_id}/share/{target_user_id}", response_model=MessageResponse)
async def unshare_strategy(
    strategy_id: int,
    target_user_id: int,
    svc: Annotated[StrategyService, Depends(_get_strategy_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> MessageResponse:
    ok = await svc.unshare_strategy(strategy_id, current_user.id, target_user_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Share not found")
    return MessageResponse(message="Share removed")


@strategy_router.get("/{strategy_id}/shares")
async def list_strategy_shares(
    strategy_id: int,
    svc: Annotated[StrategyService, Depends(_get_strategy_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> list[dict[str, Any]]:
    shares = await svc.list_shares(strategy_id, current_user.id)
    return shares


# ── Execute, Batch, Schedule, Replay, Results ──


@strategy_router.post("/{strategy_id}/execute", status_code=status.HTTP_201_CREATED)
async def execute_strategy(
    strategy_id: int,
    exec_svc: Annotated[StrategyExecutionService, Depends(_get_execution_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    as_of_date: date | None = Query(None),
) -> dict:
    result = await exec_svc.execute_strategy(
        strategy_id, current_user.id,
        execution_type="manual",
        as_of_date=as_of_date,
    )
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found or access denied")
    return result


@strategy_router.post("/execute-batch", status_code=status.HTTP_201_CREATED)
async def execute_strategy_batch(
    exec_svc: Annotated[StrategyExecutionService, Depends(_get_execution_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    strategy_ids: list[int] = Query(...),
    as_of_date: date | None = Query(None),
) -> list[dict]:
    return await exec_svc.execute_batch(strategy_ids, current_user.id, as_of_date)


@strategy_router.post("/execute-scheduled", status_code=status.HTTP_201_CREATED)
async def execute_scheduled_strategies(
    exec_svc: Annotated[StrategyExecutionService, Depends(_get_execution_service)],
) -> list[dict]:
    return await exec_svc.execute_scheduled()


@strategy_router.get("/{strategy_id}/executions")
async def list_strategy_executions(
    strategy_id: int,
    exec_svc: Annotated[StrategyExecutionService, Depends(_get_execution_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
) -> PaginatedResponse[dict]:
    rows, total = await exec_svc.get_executions(strategy_id, current_user.id, skip, limit)
    items = [{
        "id": r.id,
        "strategy_id": r.strategy_id,
        "execution_type": r.execution_type,
        "batch_id": r.batch_id,
        "as_of_date": r.as_of_date.isoformat() if r.as_of_date else None,
        "status": r.status,
        "total_results": r.total_results,
        "error_message": r.error_message,
        "started_at": r.started_at.isoformat() if r.started_at else None,
        "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        "execution_time_ms": r.execution_time_ms,
    } for r in rows]
    return PaginatedResponse(items=items, total=total, skip=skip, limit=limit)


@strategy_router.get("/executions/{execution_id}")
async def get_execution_detail(
    execution_id: int,
    exec_svc: Annotated[StrategyExecutionService, Depends(_get_execution_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> dict:
    result = await exec_svc.get_execution(execution_id, current_user.id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution not found")
    return result


@strategy_router.get("/executions/batch/{batch_id}")
async def get_batch_executions(
    batch_id: str,
    exec_svc: Annotated[StrategyExecutionService, Depends(_get_execution_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> list[dict]:
    return await exec_svc.get_batch_executions(batch_id, current_user.id)
