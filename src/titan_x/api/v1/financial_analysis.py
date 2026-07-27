from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from titan_x.api.dependencies import get_current_active_user, request_session
from titan_x.models.user import User
from titan_x.services.financial_analysis_service import FinancialAnalysisService
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/financial-analysis", tags=["financial-analysis"])


async def get_fa_service(
    session: Annotated[AsyncSession, Depends(request_session)],
) -> FinancialAnalysisService:
    return FinancialAnalysisService(session)


# --- Quarterly Results ---

@router.post("/quarterly")
async def record_quarterly(
    user: Annotated[User, Depends(get_current_active_user)],
    svc: Annotated[FinancialAnalysisService, Depends(get_fa_service)],
    symbol: str = Query(...),
    fiscal_year: int = Query(...),
    quarter: int = Query(..., ge=1, le=4),
    revenue: float | None = Query(None),
    cost_of_revenue: float | None = Query(None),
    gross_profit: float | None = Query(None),
    operating_expenses: float | None = Query(None),
    operating_income: float | None = Query(None),
    net_income: float | None = Query(None),
    eps_basic: float | None = Query(None),
    eps_diluted: float | None = Query(None),
    filing_date: date | None = Query(None),
):
    try:
        qr = await svc.record_quarterly(
            symbol=symbol, fiscal_year=fiscal_year, quarter=quarter,
            revenue=revenue, cost_of_revenue=cost_of_revenue,
            gross_profit=gross_profit, operating_expenses=operating_expenses,
            operating_income=operating_income, net_income=net_income,
            eps_basic=eps_basic, eps_diluted=eps_diluted,
            filing_date=filing_date,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return qr


@router.get("/quarterly/{symbol}")
async def get_quarterly(
    symbol: str,
    svc: Annotated[FinancialAnalysisService, Depends(get_fa_service)],
    limit: int = Query(8, ge=1, le=40),
):
    return await svc.get_quarterly(symbol, limit=limit)


@router.delete("/quarterly/{result_id}")
async def delete_quarterly(
    result_id: int,
    user: Annotated[User, Depends(get_current_active_user)],
    svc: Annotated[FinancialAnalysisService, Depends(get_fa_service)],
):
    ok = await svc.delete_quarterly(result_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return {"deleted": True}


# --- Annual Results ---

@router.post("/annual")
async def record_annual(
    user: Annotated[User, Depends(get_current_active_user)],
    svc: Annotated[FinancialAnalysisService, Depends(get_fa_service)],
    symbol: str = Query(...),
    fiscal_year: int = Query(...),
    revenue: float | None = Query(None),
    cost_of_revenue: float | None = Query(None),
    gross_profit: float | None = Query(None),
    operating_expenses: float | None = Query(None),
    operating_income: float | None = Query(None),
    net_income: float | None = Query(None),
    eps_basic: float | None = Query(None),
    eps_diluted: float | None = Query(None),
    filing_date: date | None = Query(None),
):
    ar = await svc.record_annual(
        symbol=symbol, fiscal_year=fiscal_year,
        revenue=revenue, cost_of_revenue=cost_of_revenue,
        gross_profit=gross_profit, operating_expenses=operating_expenses,
        operating_income=operating_income, net_income=net_income,
        eps_basic=eps_basic, eps_diluted=eps_diluted,
        filing_date=filing_date,
    )
    return ar


@router.get("/annual/{symbol}")
async def get_annual(
    symbol: str,
    svc: Annotated[FinancialAnalysisService, Depends(get_fa_service)],
    limit: int = Query(5, ge=1, le=20),
):
    return await svc.get_annual(symbol, limit=limit)


@router.delete("/annual/{result_id}")
async def delete_annual(
    result_id: int,
    user: Annotated[User, Depends(get_current_active_user)],
    svc: Annotated[FinancialAnalysisService, Depends(get_fa_service)],
):
    ok = await svc.delete_annual(result_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return {"deleted": True}


# --- Guidance ---

@router.post("/guidance")
async def record_guidance(
    user: Annotated[User, Depends(get_current_active_user)],
    svc: Annotated[FinancialAnalysisService, Depends(get_fa_service)],
    symbol: str = Query(...),
    fiscal_year: int = Query(...),
    period_type: str = Query(...),
    revenue_low: float | None = Query(None),
    revenue_high: float | None = Query(None),
    eps_low: float | None = Query(None),
    eps_high: float | None = Query(None),
    operating_margin_low: float | None = Query(None),
    operating_margin_high: float | None = Query(None),
    guidance_notes: str | None = Query(None),
    issued_date: date | None = Query(None),
):
    g = await svc.record_guidance(
        symbol=symbol, fiscal_year=fiscal_year, period_type=period_type,
        revenue_low=revenue_low, revenue_high=revenue_high,
        eps_low=eps_low, eps_high=eps_high,
        operating_margin_low=operating_margin_low, operating_margin_high=operating_margin_high,
        guidance_notes=guidance_notes, issued_date=issued_date,
    )
    return g


@router.get("/guidance/{symbol}")
async def get_guidance(
    symbol: str,
    svc: Annotated[FinancialAnalysisService, Depends(get_fa_service)],
    status: str | None = Query("active"),
):
    return await svc.get_guidance(symbol, status=status)


@router.delete("/guidance/{guidance_id}")
async def delete_guidance(
    guidance_id: int,
    user: Annotated[User, Depends(get_current_active_user)],
    svc: Annotated[FinancialAnalysisService, Depends(get_fa_service)],
):
    ok = await svc.delete_guidance(guidance_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return {"deleted": True}


# --- Analysis ---

@router.post("/analyze/{symbol}")
async def analyze(
    symbol: str,
    user: Annotated[User, Depends(get_current_active_user)],
    svc: Annotated[FinancialAnalysisService, Depends(get_fa_service)],
):
    result = await svc.analyze(symbol)
    return result


@router.get("/analyze/{symbol}")
async def get_latest_analysis(
    symbol: str,
    svc: Annotated[FinancialAnalysisService, Depends(get_fa_service)],
):
    result = await svc.get_analysis(symbol)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No analysis found")
    return result
