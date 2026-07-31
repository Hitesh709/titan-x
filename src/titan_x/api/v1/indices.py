from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from titan_x.api.dependencies import get_current_active_user, get_db
from titan_x.models.user import User
from titan_x.services.index_service import IndexService
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/indices", tags=["indices"])


@router.get("")
async def list_indices(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    svc = IndexService(db)
    return {"items": await svc.list_all()}


@router.get("/{symbol}/history")
async def get_index_history(
    symbol: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    range: str = Query("3M", pattern=r"^(1W|1M|3M|6M|YTD|1Y)$"),
):
    svc = IndexService(db)
    points = await svc.get_history(symbol, range)
    if not points:
        raise HTTPException(404, f"No history for index {symbol}")
    return {"symbol": symbol.upper(), "range": range, "points": points}


@router.get("/{symbol}/performance")
async def get_index_performance(
    symbol: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    svc = IndexService(db)
    result = await svc.get_performance(symbol)
    if not result:
        raise HTTPException(404, f"No data for index {symbol}")
    return result
