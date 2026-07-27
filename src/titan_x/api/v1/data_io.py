from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import PlainTextResponse

from titan_x.api.dependencies import get_current_active_user, request_session
from titan_x.models.user import User
from titan_x.services.data_io_service import DataImportExportService
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/data-io", tags=["data-io"])


async def get_data_io_service(
    session: Annotated[AsyncSession, Depends(request_session)],
) -> DataImportExportService:
    return DataImportExportService(session)


@router.post("/import/prices")
async def import_prices(
    user: Annotated[User, Depends(get_current_active_user)],
    svc: Annotated[DataImportExportService, Depends(get_data_io_service)],
    body: str = Query(..., description="CSV content"),
):
    try:
        result = await svc.import_daily_prices_csv(body)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return result


@router.post("/import/companies")
async def import_companies(
    user: Annotated[User, Depends(get_current_active_user)],
    svc: Annotated[DataImportExportService, Depends(get_data_io_service)],
    body: str = Query(..., description="CSV content"),
):
    try:
        result = await svc.import_companies_csv(body)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return result


@router.get("/export/prices/{symbol}", response_class=PlainTextResponse)
async def export_prices(
    symbol: str,
    user: Annotated[User, Depends(get_current_active_user)],
    svc: Annotated[DataImportExportService, Depends(get_data_io_service)],
    start: date | None = Query(None),
    end: date | None = Query(None),
):
    return await svc.export_daily_prices_csv(symbol, start=start, end=end)


@router.get("/export/positions", response_class=PlainTextResponse)
async def export_positions(
    user: Annotated[User, Depends(get_current_active_user)],
    svc: Annotated[DataImportExportService, Depends(get_data_io_service)],
):
    return await svc.export_positions_csv(user.id)


@router.get("/export/orders", response_class=PlainTextResponse)
async def export_orders(
    user: Annotated[User, Depends(get_current_active_user)],
    svc: Annotated[DataImportExportService, Depends(get_data_io_service)],
):
    return await svc.export_orders_csv(user.id)
