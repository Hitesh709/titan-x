from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import HTMLResponse

from titan_x.api.dependencies import get_current_active_user, request_session
from titan_x.models.user import User
from titan_x.services.report_generator import ReportGenerator
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/reports", tags=["reports"])


async def get_report_generator(
    session: Annotated[AsyncSession, Depends(request_session)],
) -> ReportGenerator:
    return ReportGenerator(session)


@router.get("/portfolio/{portfolio_id}", response_class=HTMLResponse)
async def portfolio_report(
    portfolio_id: int,
    user: Annotated[User, Depends(get_current_active_user)],
    svc: Annotated[ReportGenerator, Depends(get_report_generator)],
):
    try:
        return await svc.generate_portfolio_report(portfolio_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/pnl", response_class=HTMLResponse)
async def pnl_statement(
    user: Annotated[User, Depends(get_current_active_user)],
    svc: Annotated[ReportGenerator, Depends(get_report_generator)],
    start: date | None = Query(None),
    end: date | None = Query(None),
):
    return await svc.generate_pnl_statement(user.id, start=start, end=end)


@router.get("/tax/{fiscal_year}", response_class=HTMLResponse)
async def tax_report(
    fiscal_year: int,
    user: Annotated[User, Depends(get_current_active_user)],
    svc: Annotated[ReportGenerator, Depends(get_report_generator)],
):
    return await svc.generate_tax_report(user.id, fiscal_year)
