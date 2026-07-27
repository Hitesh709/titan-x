from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.api.dependencies import get_current_active_user, get_db
from titan_x.models.user import User
from titan_x.services.valuation_service import ValuationService

router = APIRouter(prefix="/valuation", tags=["valuation"])


class DCFRequest(BaseModel):
    free_cash_flow: float | None = None
    growth_rate_5y: float | None = None
    terminal_growth_rate: float = 0.025
    wacc: float | None = None
    projection_years: int = 5
    shares_outstanding: float | None = None
    net_debt: float | None = None
    cash_and_equivalents: float | None = None
    current_price: float | None = None


class RelativeRequest(BaseModel):
    eps: float | None = None
    book_value_per_share: float | None = None
    revenue_per_share: float | None = None
    ebitda: float | None = None
    current_price: float | None = None
    industry_avg_pe: float | None = None
    industry_avg_pb: float | None = None
    industry_avg_ps: float | None = None
    industry_avg_ev_ebitda: float | None = None


class SectorRequest(BaseModel):
    peer_data: list[dict] | None = None


@router.post("/dcf/{symbol}")
async def compute_dcf(symbol: str, body: DCFRequest, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    svc = ValuationService(db)
    result = await svc.compute_dcf(symbol.upper(), **body.model_dump(exclude_none=True))
    return {
        "id": result.id,
        "symbol": result.symbol,
        "current_price": result.current_price,
        "intrinsic_value": result.intrinsic_value,
        "upside_pct": result.upside_pct,
        "wacc": result.wacc,
        "growth_rate_5y": result.growth_rate_5y,
        "terminal_growth": result.terminal_growth_rate,
        "free_cash_flow": result.free_cash_flow,
        "present_value_fcf": result.present_value_fcf,
        "terminal_value": result.terminal_value,
        "enterprise_value": result.enterprise_value,
        "equity_value": result.equity_value,
    }


@router.get("/dcf/{symbol}")
async def get_dcf(symbol: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    svc = ValuationService(db)
    result = await svc.get_dcf(symbol.upper())
    if not result:
        raise HTTPException(404, "DCF valuation not found")
    return result


@router.post("/relative/{symbol}")
async def compute_relative(symbol: str, body: RelativeRequest, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    svc = ValuationService(db)
    result = await svc.compute_relative(symbol.upper(), **{k: v for k, v in body.model_dump().items() if v is not None})
    return {
        "id": result.id,
        "symbol": result.symbol,
        "current_price": result.current_price,
        "pe_ratio": result.pe_ratio,
        "pb_ratio": result.pb_ratio,
        "ps_ratio": result.ps_ratio,
        "pe_fair_value": result.pe_fair_value,
        "pb_fair_value": result.pb_fair_value,
        "ps_fair_value": result.ps_fair_value,
        "composite_fair_value": result.composite_fair_value,
        "upside_pct": result.upside_pct,
    }


@router.get("/relative/{symbol}")
async def get_relative(symbol: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    svc = ValuationService(db)
    result = await svc.get_relative(symbol.upper())
    if not result:
        raise HTTPException(404, "Relative valuation not found")
    return result


@router.post("/sector/{symbol}")
async def compute_sector(symbol: str, body: SectorRequest, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    svc = ValuationService(db)
    result = await svc.compute_sector(symbol.upper(), sector_pe_data=body.peer_data)
    return {
        "id": result.id,
        "symbol": result.symbol,
        "sector": result.sector,
        "peer_count": result.peer_count,
        "peer_avg_pe": result.peer_avg_pe,
        "peer_median_pe": result.peer_median_pe,
        "pe_percentile": result.pe_percentile,
        "sector_grade": result.sector_grade,
        "sector_fair_value": result.sector_fair_value,
        "upside_pct": result.upside_pct,
    }


@router.get("/sector/{symbol}")
async def get_sector(symbol: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    svc = ValuationService(db)
    result = await svc.get_sector(symbol.upper())
    if not result:
        raise HTTPException(404, "Sector valuation not found")
    return result


@router.post("/report/{symbol}")
async def generate_report(symbol: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    svc = ValuationService(db)
    result = await svc.generate_report(symbol.upper())
    return {
        "id": result.id,
        "symbol": result.symbol,
        "current_price": result.current_price,
        "dcf_fair_value": result.dcf_fair_value,
        "relative_fair_value": result.relative_fair_value,
        "sector_fair_value": result.sector_fair_value,
        "composite_fair_value": result.composite_fair_value,
        "margin_of_safety_pct": result.margin_of_safety_pct,
        "recommendation": result.recommendation,
        "report_json": result.report_json,
    }


@router.get("/report/{symbol}")
async def get_report(symbol: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    svc = ValuationService(db)
    result = await svc.get_report(symbol.upper())
    if not result:
        raise HTTPException(404, "Valuation report not found")
    return result
