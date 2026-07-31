from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.api.dependencies import get_current_active_user, request_session
from titan_x.api.schemas import MessageResponse, PaginatedResponse
from titan_x.models.user import User
from titan_x.services.paper_analytics_service import PaperAnalyticsService
from titan_x.services.paper_trading_service import PaperTradingError, PaperTradingService

router = APIRouter(
    prefix="/paper-trading",
    tags=["paper-trading"],
)


@router.post("/account", status_code=status.HTTP_201_CREATED)
async def create_account(
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[AsyncSession, Depends(request_session)],
    initial_capital: float = Query(100000.0, gt=0),
) -> dict:
    svc = PaperTradingService(session)
    try:
        account = await svc.create_account(current_user.id, Decimal(str(initial_capital)))
        return {"id": account.id, "initial_capital": float(account.initial_capital), "cash_balance": float(account.cash_balance)}
    except PaperTradingError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/account")
async def get_account(
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[AsyncSession, Depends(request_session)],
) -> dict:
    svc = PaperTradingService(session)
    summary = await svc.get_account_summary(current_user.id)
    if summary is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No paper account")
    return summary


@router.post("/orders", status_code=status.HTTP_201_CREATED)
async def place_order(
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[AsyncSession, Depends(request_session)],
    symbol: str = Query(..., min_length=1, max_length=20),
    side: str = Query(..., pattern="^(buy|sell)$"),
    order_type: str = Query(..., pattern="^(market|limit|stop|stop_limit)$"),
    quantity: int = Query(..., gt=0),
    price: float | None = Query(None, gt=0),
    stop_price: float | None = Query(None, gt=0),
    time_in_force: str = Query("day", pattern="^(day|gtc)$"),
) -> dict:
    svc = PaperTradingService(session)
    try:
        order = await svc.place_order(
            current_user.id, symbol, side, order_type, quantity,
            price=Decimal(str(price)) if price is not None else None,
            stop_price=Decimal(str(stop_price)) if stop_price is not None else None,
            time_in_force=time_in_force,
        )
        return {
            "id": order.id,
            "symbol": order.symbol,
            "side": order.side,
            "order_type": order.order_type,
            "quantity": order.quantity,
            "filled_quantity": order.filled_quantity,
            "price": float(order.price) if order.price else None,
            "stop_price": float(order.stop_price) if order.stop_price else None,
            "status": order.status,
            "rejection_reason": order.rejection_reason,
        }
    except PaperTradingError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/orders")
async def list_orders(
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[AsyncSession, Depends(request_session)],
    status: str | None = Query(None, pattern="^(pending|open|filled|partially_filled|cancelled|rejected)$"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
) -> PaginatedResponse[dict]:
    svc = PaperTradingService(session)
    rows, total = await svc.list_orders(current_user.id, status, skip, limit)
    items = [{
        "id": r.id, "symbol": r.symbol, "side": r.side,
        "order_type": r.order_type, "quantity": r.quantity,
        "filled_quantity": r.filled_quantity,
        "price": float(r.price) if r.price else None,
        "stop_price": float(r.stop_price) if r.stop_price else None,
        "status": r.status, "time_in_force": r.time_in_force,
        "rejection_reason": r.rejection_reason,
        "filled_at": r.filled_at.isoformat() if r.filled_at else None,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r in rows]
    return PaginatedResponse(items=items, total=total, skip=skip, limit=limit)


@router.get("/orders/{order_id}")
async def get_order(
    order_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[AsyncSession, Depends(request_session)],
) -> dict:
    svc = PaperTradingService(session)
    order = await svc.get_order(order_id, current_user.id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return {
        "id": order.id, "symbol": order.symbol, "side": order.side,
        "order_type": order.order_type, "quantity": order.quantity,
        "filled_quantity": order.filled_quantity,
        "price": float(order.price) if order.price else None,
        "stop_price": float(order.stop_price) if order.stop_price else None,
        "status": order.status, "time_in_force": order.time_in_force,
        "rejection_reason": order.rejection_reason,
        "filled_at": order.filled_at.isoformat() if order.filled_at else None,
        "created_at": order.created_at.isoformat() if order.created_at else None,
    }


@router.delete("/orders/{order_id}", response_model=MessageResponse)
async def cancel_order(
    order_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[AsyncSession, Depends(request_session)],
) -> MessageResponse:
    svc = PaperTradingService(session)
    ok = await svc.cancel_order(order_id, current_user.id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot cancel order")
    return MessageResponse(message="Order cancelled")


@router.get("/portfolio")
async def get_portfolio(
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[AsyncSession, Depends(request_session)],
) -> list[dict]:
    svc = PaperTradingService(session)
    return await svc.get_portfolio(current_user.id)


@router.get("/sector-exposure")
async def get_sector_exposure(
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[AsyncSession, Depends(request_session)],
) -> list[dict]:
    svc = PaperTradingService(session)
    return await svc.get_sector_exposure(current_user.id)


@router.get("/equity-curve")
async def get_equity_curve(
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[AsyncSession, Depends(request_session)],
) -> list[dict]:
    svc = PaperTradingService(session)
    return await svc.get_equity_curve(current_user.id)


@router.post("/portfolio/refresh")
async def refresh_portfolio_prices(
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[AsyncSession, Depends(request_session)],
) -> dict:
    svc = PaperTradingService(session)
    updated = await svc.refresh_prices(current_user.id)
    return {"updated_positions": updated}


@router.get("/pnl")
async def get_pnl(
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[AsyncSession, Depends(request_session)],
) -> dict:
    svc = PaperTradingService(session)
    return await svc.get_pnl_summary(current_user.id)


@router.get("/trades")
async def get_trade_history(
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[AsyncSession, Depends(request_session)],
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
) -> PaginatedResponse[dict]:
    svc = PaperTradingService(session)
    rows, total = await svc.get_trade_history(current_user.id, skip, limit)
    items = [{
        "id": r.id, "symbol": r.symbol, "side": r.side,
        "quantity": r.quantity, "price": float(r.price),
        "commission": float(r.commission),
        "realized_pnl": float(r.realized_pnl) if r.realized_pnl else None,
        "trade_time": r.trade_time.isoformat() if r.trade_time else None,
    } for r in rows]
    return PaginatedResponse(items=items, total=total, skip=skip, limit=limit)


@router.get("/simulated-orders")
async def list_simulated_orders(
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[AsyncSession, Depends(request_session)],
    status: str | None = Query(None, pattern="^(open|closed)$"),
    outcome: str | None = Query(None, pattern="^(win|loss|breakeven)$"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
) -> PaginatedResponse[dict]:
    svc = PaperTradingService(session)
    rows, total = await svc.list_simulated_orders(current_user.id, status, outcome, skip, limit)
    items = [{
        "id": r.id, "symbol": r.symbol, "direction": r.direction,
        "status": r.status, "outcome": r.outcome,
        "entry_price": float(r.entry_price),
        "exit_price": float(r.exit_price) if r.exit_price else None,
        "quantity": r.quantity,
        "entry_fee": float(r.entry_fee),
        "exit_fee": float(r.exit_fee) if r.exit_fee else None,
        "total_fees": float(r.total_fees),
        "slippage": float(r.slippage) if r.slippage else None,
        "gross_pnl": float(r.gross_pnl) if r.gross_pnl else None,
        "net_pnl": float(r.net_pnl) if r.net_pnl else None,
        "entry_date": r.entry_date.isoformat() if r.entry_date else None,
        "exit_date": r.exit_date.isoformat() if r.exit_date else None,
    } for r in rows]
    return PaginatedResponse(items=items, total=total, skip=skip, limit=limit)


@router.get("/simulated-orders/{order_id}")
async def get_simulated_order(
    order_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[AsyncSession, Depends(request_session)],
) -> dict:
    svc = PaperTradingService(session)
    sim = await svc.get_simulated_order(order_id, current_user.id)
    if sim is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Simulated order not found")
    return {
        "id": sim.id, "symbol": sim.symbol, "direction": sim.direction,
        "status": sim.status, "outcome": sim.outcome,
        "entry_price": float(sim.entry_price),
        "exit_price": float(sim.exit_price) if sim.exit_price else None,
        "quantity": sim.quantity,
        "entry_fee": float(sim.entry_fee),
        "exit_fee": float(sim.exit_fee) if sim.exit_fee else None,
        "total_fees": float(sim.total_fees),
        "slippage": float(sim.slippage) if sim.slippage else None,
        "gross_pnl": float(sim.gross_pnl) if sim.gross_pnl else None,
        "net_pnl": float(sim.net_pnl) if sim.net_pnl else None,
        "entry_date": sim.entry_date.isoformat() if sim.entry_date else None,
        "exit_date": sim.exit_date.isoformat() if sim.exit_date else None,
    }


@router.get("/analytics")
async def get_analytics(
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[AsyncSession, Depends(request_session)],
    risk_free_rate: float = Query(0.05, ge=0, le=1),
) -> dict:
    svc = PaperAnalyticsService(session)
    analytics = await svc.compute_analytics(current_user.id, risk_free_rate)
    if not analytics:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No paper account")
    return analytics


@router.get("/reports/performance")
async def get_performance_report(
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[AsyncSession, Depends(request_session)],
) -> dict:
    svc = PaperTradingService(session)
    report = await svc.get_performance_report(current_user.id)
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No paper account")
    return report
