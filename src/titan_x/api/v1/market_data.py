from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from titan_x.api.dependencies import get_current_active_user, request_session
from titan_x.models.user import User
from titan_x.services.market_data_service import MarketDataService
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/market-data", tags=["market-data"])


async def get_market_data_service(
    session: Annotated[AsyncSession, Depends(request_session)],
) -> MarketDataService:
    return MarketDataService(session)


@router.get("/providers")
async def list_providers(
    svc: Annotated[MarketDataService, Depends(get_market_data_service)],
):
    return {"providers": svc.get_available_providers()}


@router.post("/fetch/{symbol}")
async def fetch_historical(
    symbol: str,
    user: Annotated[User, Depends(get_current_active_user)],
    svc: Annotated[MarketDataService, Depends(get_market_data_service)],
    provider: str = Query("mock"),
    api_key: str | None = Query(None),
    start: date | None = Query(None),
    end: date | None = Query(None),
):
    try:
        result = await svc.fetch_and_store_historical(
            symbol=symbol,
            provider_name=provider,
            api_key=api_key,
            start=start,
            end=end,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return result


@router.get("/quote/{symbol}")
async def get_quote(
    symbol: str,
    user: Annotated[User, Depends(get_current_active_user)],
    svc: Annotated[MarketDataService, Depends(get_market_data_service)],
    provider: str = Query("mock"),
    api_key: str | None = Query(None),
):
    try:
        return await svc.get_quote(symbol, provider_name=provider, api_key=api_key)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/profile/{symbol}")
async def get_company_profile(
    symbol: str,
    user: Annotated[User, Depends(get_current_active_user)],
    svc: Annotated[MarketDataService, Depends(get_market_data_service)],
    provider: str = Query("mock"),
    api_key: str | None = Query(None),
):
    try:
        result = await svc.get_company_profile(symbol, provider_name=provider, api_key=api_key)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return result
