from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from titan_x.api.dependencies import get_current_active_user, request_session
from titan_x.models.user import User
from titan_x.services.broker_service import BrokerIntegrationService
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/brokers", tags=["brokers"])


async def get_broker_service(
    session: Annotated[AsyncSession, Depends(request_session)],
) -> BrokerIntegrationService:
    return BrokerIntegrationService(session)


@router.get("/available")
async def list_available_brokers(
    svc: Annotated[BrokerIntegrationService, Depends(get_broker_service)],
):
    return {"brokers": svc.get_available_brokers()}


@router.post("/connections")
async def create_connection(
    user: Annotated[User, Depends(get_current_active_user)],
    svc: Annotated[BrokerIntegrationService, Depends(get_broker_service)],
    broker_name: str = Query(...),
    label: str = Query(""),
    api_key: str | None = Query(None),
    api_secret: str | None = Query(None),
    metadata_json: str | None = Query(None),
):
    try:
        conn = await svc.create_connection(
            user_id=user.id,
            broker_name=broker_name,
            label=label,
            api_key=api_key,
            api_secret=api_secret,
            metadata_json=metadata_json,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return conn


@router.get("/connections")
async def list_connections(
    user: Annotated[User, Depends(get_current_active_user)],
    svc: Annotated[BrokerIntegrationService, Depends(get_broker_service)],
):
    return await svc.list_connections(user.id)


@router.get("/connections/{connection_id}")
async def get_connection(
    connection_id: int,
    user: Annotated[User, Depends(get_current_active_user)],
    svc: Annotated[BrokerIntegrationService, Depends(get_broker_service)],
):
    conn = await svc.get_connection(connection_id)
    if conn is None or conn.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")
    return conn


@router.put("/connections/{connection_id}")
async def update_connection(
    connection_id: int,
    user: Annotated[User, Depends(get_current_active_user)],
    svc: Annotated[BrokerIntegrationService, Depends(get_broker_service)],
    label: str | None = Query(None),
    api_key: str | None = Query(None),
    api_secret: str | None = Query(None),
    metadata_json: str | None = Query(None),
    is_active: bool | None = Query(None),
):
    conn = await svc.get_connection(connection_id)
    if conn is None or conn.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")
    updated = await svc.update_connection(
        connection_id,
        label=label,
        api_key=api_key,
        api_secret=api_secret,
        metadata_json=metadata_json,
        is_active=is_active,
    )
    return updated


@router.delete("/connections/{connection_id}")
async def delete_connection(
    connection_id: int,
    user: Annotated[User, Depends(get_current_active_user)],
    svc: Annotated[BrokerIntegrationService, Depends(get_broker_service)],
):
    conn = await svc.get_connection(connection_id)
    if conn is None or conn.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")
    ok = await svc.delete_connection(connection_id)
    return {"deleted": ok}


@router.post("/connections/{connection_id}/authenticate")
async def authenticate(
    connection_id: int,
    user: Annotated[User, Depends(get_current_active_user)],
    svc: Annotated[BrokerIntegrationService, Depends(get_broker_service)],
    request_token: str | None = Query(None),
):
    conn = await svc.get_connection(connection_id)
    if conn is None or conn.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")
    result = await svc.authenticate(connection_id, request_token)
    if result is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Authentication failed")
    return result


@router.post("/connections/{connection_id}/orders")
async def place_order(
    connection_id: int,
    user: Annotated[User, Depends(get_current_active_user)],
    svc: Annotated[BrokerIntegrationService, Depends(get_broker_service)],
    symbol: str = Query(...),
    side: str = Query(...),
    quantity: int = Query(..., gt=0),
    order_type: str = Query("market"),
    price: float | None = Query(None),
):
    conn = await svc.get_connection(connection_id)
    if conn is None or conn.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")
    try:
        result = await svc.place_order(connection_id, {
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "order_type": order_type,
            "price": price,
        })
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return result


@router.post("/connections/{connection_id}/orders/{broker_order_id}/cancel")
async def cancel_order(
    connection_id: int,
    broker_order_id: str,
    user: Annotated[User, Depends(get_current_active_user)],
    svc: Annotated[BrokerIntegrationService, Depends(get_broker_service)],
):
    conn = await svc.get_connection(connection_id)
    if conn is None or conn.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")
    try:
        result = await svc.cancel_order(connection_id, broker_order_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return result


@router.get("/connections/{connection_id}/positions")
async def get_positions(
    connection_id: int,
    user: Annotated[User, Depends(get_current_active_user)],
    svc: Annotated[BrokerIntegrationService, Depends(get_broker_service)],
):
    conn = await svc.get_connection(connection_id)
    if conn is None or conn.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")
    try:
        return await svc.get_positions(connection_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/connections/{connection_id}/holdings")
async def get_holdings(
    connection_id: int,
    user: Annotated[User, Depends(get_current_active_user)],
    svc: Annotated[BrokerIntegrationService, Depends(get_broker_service)],
):
    conn = await svc.get_connection(connection_id)
    if conn is None or conn.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")
    try:
        return await svc.get_holdings(connection_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/connections/{connection_id}/profile")
async def get_profile(
    connection_id: int,
    user: Annotated[User, Depends(get_current_active_user)],
    svc: Annotated[BrokerIntegrationService, Depends(get_broker_service)],
):
    conn = await svc.get_connection(connection_id)
    if conn is None or conn.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")
    try:
        return await svc.get_profile(connection_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/connections/{connection_id}/sync")
async def sync_orders(
    connection_id: int,
    user: Annotated[User, Depends(get_current_active_user)],
    svc: Annotated[BrokerIntegrationService, Depends(get_broker_service)],
):
    conn = await svc.get_connection(connection_id)
    if conn is None or conn.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")
    try:
        return await svc.sync_orders(connection_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
