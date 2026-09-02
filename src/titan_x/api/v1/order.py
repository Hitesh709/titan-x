from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.api.dependencies import get_current_active_user, request_session
from titan_x.models.user import User
from titan_x.services.order_service import OrderService

router = APIRouter(prefix="/orders", tags=["orders"])


async def get_order_service(
    session: Annotated[AsyncSession, Depends(request_session)],
) -> OrderService:
    return OrderService(session)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_order(
    user: Annotated[User, Depends(get_current_active_user)],
    svc: Annotated[OrderService, Depends(get_order_service)],
    symbol: str = Query(...),
    side: str = Query(...),
    order_type: str = Query(...),
    quantity: int = Query(..., gt=0),
    price: float | None = Query(None),
    stop_price: float | None = Query(None),
    time_in_force: str = Query("day"),
):
    try:
        order = await svc.create_order(
            user_id=user.id,
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=Decimal(str(price)) if price is not None else None,
            stop_price=Decimal(str(stop_price)) if stop_price is not None else None,
            time_in_force=time_in_force,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return order


@router.get("")
async def list_orders(
    user: Annotated[User, Depends(get_current_active_user)],
    svc: Annotated[OrderService, Depends(get_order_service)],
    status_filter: str | None = Query(None, alias="status"),
    symbol: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    rows, total = await svc.list_orders(
        user_id=user.id,
        status=status_filter,
        symbol=symbol,
        limit=limit,
        offset=offset,
    )
    return {"items": rows, "total": total}


# Static paths must be declared before /{order_id}; otherwise FastAPI can try
# to parse "positions" or "book" as an integer and return a misleading 422.
@router.get("/positions/me")
async def get_positions(
    user: Annotated[User, Depends(get_current_active_user)],
    svc: Annotated[OrderService, Depends(get_order_service)],
):
    return await svc.get_positions(user.id)


@router.get("/positions/{symbol}")
async def get_position(
    symbol: str,
    user: Annotated[User, Depends(get_current_active_user)],
    svc: Annotated[OrderService, Depends(get_order_service)],
):
    pos = await svc.get_position(user.id, symbol)
    if pos is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Position not found")
    return pos


@router.get("/book/me")
async def get_order_book(
    user: Annotated[User, Depends(get_current_active_user)],
    svc: Annotated[OrderService, Depends(get_order_service)],
):
    return await svc.get_order_book(user.id)


@router.get("/{order_id}")
async def get_order(
    order_id: int,
    user: Annotated[User, Depends(get_current_active_user)],
    svc: Annotated[OrderService, Depends(get_order_service)],
):
    order = await svc.get_order(order_id)
    if order is None or order.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return order


@router.post("/{order_id}/cancel")
async def cancel_order(
    order_id: int,
    user: Annotated[User, Depends(get_current_active_user)],
    svc: Annotated[OrderService, Depends(get_order_service)],
):
    order = await svc.get_order(order_id)
    if order is None or order.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    try:
        order = await svc.cancel_order(order_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return order


@router.post("/{order_id}/execute")
async def execute_order(
    order_id: int,
    user: Annotated[User, Depends(get_current_active_user)],
    svc: Annotated[OrderService, Depends(get_order_service)],
    fill_price: float = Query(...),
    fill_quantity: int | None = Query(None),
    commission: float | None = Query(None),
):
    order = await svc.get_order(order_id)
    if order is None or order.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    try:
        order_obj, fill, pos = await svc.execute_order(
            order_id,
            fill_price=Decimal(str(fill_price)),
            fill_quantity=fill_quantity,
            commission=Decimal(str(commission)) if commission is not None else None,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return {"order": order_obj, "fill": fill, "position": pos}
