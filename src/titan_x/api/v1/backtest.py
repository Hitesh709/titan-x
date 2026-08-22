import json
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.api.dependencies import (
    get_current_active_user,
    require_api_key,
    request_session,
)
from titan_x.api.schemas import MessageResponse, PaginatedResponse
from titan_x.db.repository import BaseRepository
from titan_x.models.backtest import Backtest
from titan_x.models.user import User
from titan_x.services.backtest_engine_v2 import ProductionBacktestEngine

backtest_router = APIRouter(
    prefix="/backtests",
    tags=["backtests"],
    dependencies=[Depends(require_api_key)],
)


def _loads_json(value: str | None) -> Any:
    if value is None:
        return {}
    try:
        return json.loads(value)
    except (json.JSONDecodeError, ValueError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON in request")


async def get_production_backtest_engine(
    session: Annotated[AsyncSession, Depends(request_session)],
) -> ProductionBacktestEngine:
    return ProductionBacktestEngine(session)


async def _require_backtest_owner(
    backtest_id: int,
    engine: Annotated[ProductionBacktestEngine, Depends(get_production_backtest_engine)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> None:
    repo = BaseRepository(engine._session, Backtest)
    bt = await repo.get(backtest_id)
    if bt is None or bt.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backtest not found")


@backtest_router.post("", status_code=status.HTTP_201_CREATED)
async def create_backtest(
    engine: Annotated[ProductionBacktestEngine, Depends(get_production_backtest_engine)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    name: str = Query(..., min_length=1, max_length=256),
    symbol: str = Query(..., min_length=1, max_length=16),
    start_date: date = Query(...),
    end_date: date = Query(...),
    initial_capital: float = Query(10000.0, gt=0),
    strategy_type: str = Query("sma_crossover", pattern="^(sma_crossover|rsi|bollinger|custom)$"),
    strategy_params: str | None = Query(None),
    config: str | None = Query(None),
    description: str | None = Query(None, max_length=1000),
) -> dict:
    strategy_params_dict = _loads_json(strategy_params) if strategy_params else {}
    config_dict = _loads_json(config) if config else {}
    result = await engine.create_backtest(
        user_id=current_user.id,
        name=name,
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        initial_capital=initial_capital,
        strategy_type=strategy_type,
        strategy_params=strategy_params_dict,
        config=config_dict,
        description=description,
    )
    return result


@backtest_router.post("/{backtest_id}/run")
async def run_backtest(
    backtest_id: int,
    engine: Annotated[ProductionBacktestEngine, Depends(get_production_backtest_engine)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    _owner: None = Depends(_require_backtest_owner),
) -> dict:
    try:
        result = await engine.run_backtest(backtest_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@backtest_router.get("")
async def list_backtests(
    engine: Annotated[ProductionBacktestEngine, Depends(get_production_backtest_engine)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
) -> PaginatedResponse[dict]:
    rows, total = await engine.list_backtests(user_id=current_user.id, skip=skip, limit=limit)
    items = [{
        "id": r.id, "name": r.name, "symbol": r.symbol,
        "strategy_type": r.strategy_type, "status": r.status,
        "initial_capital": r.initial_capital,
        "start_date": r.start_date.isoformat() if r.start_date else None,
        "end_date": r.end_date.isoformat() if r.end_date else None,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r in rows]
    return PaginatedResponse(items=items, total=total, skip=skip, limit=limit)


@backtest_router.get("/{backtest_id}")
async def get_backtest(
    backtest_id: int,
    engine: Annotated[ProductionBacktestEngine, Depends(get_production_backtest_engine)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    _owner: None = Depends(_require_backtest_owner),
) -> dict:
    result = await engine.get_backtest_with_report(backtest_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backtest not found")
    return result


@backtest_router.get("/{backtest_id}/report")
async def get_backtest_report(
    backtest_id: int,
    engine: Annotated[ProductionBacktestEngine, Depends(get_production_backtest_engine)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    _owner: None = Depends(_require_backtest_owner),
) -> dict:
    result = await engine.get_backtest_with_report(backtest_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backtest not found")
    return result.get("report", {})


@backtest_router.get("/{backtest_id}/trades")
async def get_backtest_trades(
    backtest_id: int,
    engine: Annotated[ProductionBacktestEngine, Depends(get_production_backtest_engine)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    _owner: None = Depends(_require_backtest_owner),
) -> list[dict]:
    trades = await engine.get_trades(backtest_id)
    return [{
        "id": t.id,
        "trade_number": t.trade_number,
        "symbol": t.symbol,
        "side": t.side,
        "status": t.status,
        "entry_date": t.entry_date.isoformat() if t.entry_date else None,
        "entry_price": t.entry_price,
        "entry_signal": t.entry_signal,
        "exit_date": t.exit_date.isoformat() if t.exit_date else None,
        "exit_price": t.exit_price,
        "exit_reason": t.exit_reason,
        "exit_signal": t.exit_signal,
        "quantity": t.quantity,
        "pnl": t.pnl,
        "pnl_pct": t.pnl_pct,
        "holding_days": t.holding_days,
    } for t in trades]


@backtest_router.get("/{backtest_id}/equity-curve")
async def get_backtest_equity_curve(
    backtest_id: int,
    engine: Annotated[ProductionBacktestEngine, Depends(get_production_backtest_engine)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    _owner: None = Depends(_require_backtest_owner),
) -> list[dict]:
    curve = await engine.get_equity_curve(backtest_id)
    return [{
        "date": p.date.isoformat() if p.date else None,
        "equity": p.equity,
        "cash": p.cash,
        "holdings_value": p.holdings_value,
        "returns_pct": p.returns_pct,
        "drawdown_pct": p.drawdown_pct,
    } for p in curve]


@backtest_router.get("/{backtest_id}/signals")
async def get_backtest_signals(
    backtest_id: int,
    engine: Annotated[ProductionBacktestEngine, Depends(get_production_backtest_engine)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    _owner: None = Depends(_require_backtest_owner),
) -> list[dict]:
    signals = await engine.get_signals(backtest_id)
    return [{
        "id": s.id,
        "signal_date": s.signal_date.isoformat() if s.signal_date else None,
        "symbol": s.symbol,
        "action": s.action,
        "price": s.price,
        "confidence": s.confidence,
        "signal_type": s.signal_type,
        "source": s.source,
        "metadata_json": s.metadata_json,
    } for s in signals]


@backtest_router.delete("/{backtest_id}", response_model=MessageResponse)
async def delete_backtest(
    backtest_id: int,
    engine: Annotated[ProductionBacktestEngine, Depends(get_production_backtest_engine)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    _owner: None = Depends(_require_backtest_owner),
) -> MessageResponse:
    deleted = await engine.delete_backtest(backtest_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backtest not found")
    return MessageResponse(message="Backtest deleted")
