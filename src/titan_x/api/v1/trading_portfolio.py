from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.api.dependencies import get_current_active_user, request_session
from titan_x.models.user import User
from titan_x.services.persistent_trading_portfolio_service import PersistentTradingPortfolioService

router = APIRouter(prefix="/trading-portfolio", tags=["trading-portfolio"])


async def get_service(
    session: Annotated[AsyncSession, Depends(request_session)],
) -> PersistentTradingPortfolioService:
    return PersistentTradingPortfolioService(session)


@router.get("/me")
async def get_my_trading_portfolio(
    user: Annotated[User, Depends(get_current_active_user)],
    svc: Annotated[PersistentTradingPortfolioService, Depends(get_service)],
):
    """Restore the authenticated user's persisted positions, orders and fills after login."""
    return await svc.snapshot(user.id)


@router.get("/me/positions")
async def get_my_positions(
    user: Annotated[User, Depends(get_current_active_user)],
    svc: Annotated[PersistentTradingPortfolioService, Depends(get_service)],
):
    return {"positions": await svc.positions(user.id)}


@router.get("/me/orders")
async def get_my_orders(
    user: Annotated[User, Depends(get_current_active_user)],
    svc: Annotated[PersistentTradingPortfolioService, Depends(get_service)],
    limit: int = Query(100, ge=1, le=500),
):
    return {"orders": await svc.orders(user.id, limit)}


@router.get("/me/fills")
async def get_my_fills(
    user: Annotated[User, Depends(get_current_active_user)],
    svc: Annotated[PersistentTradingPortfolioService, Depends(get_service)],
    limit: int = Query(100, ge=1, le=500),
):
    return {"fills": await svc.fills(user.id, limit)}
