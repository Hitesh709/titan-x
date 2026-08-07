"""Fundamental Scanner API.

Scan all symbols for ROE, ROCE, Debt, Revenue Growth, EPS Growth,
Cash Flow, and Valuation signals. View rankings and scan results.
"""
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.api import deps
from titan_x.models.user import User
from titan_x.services.fundamental_scanner_service import FundamentalScannerService

router = APIRouter(prefix="/fundamental-scanner", tags=["fundamental_scanner"])


async def _get_service(
    session: AsyncSession = Depends(deps.get_session),
) -> FundamentalScannerService:
    return FundamentalScannerService(session)


def _scan_dict(r) -> dict[str, Any]:
    return {
        "id": r.id,
        "symbol": r.symbol,
        "scan_date": r.scan_date.isoformat(),
        "composite_score": r.composite_score,
        "roe_score": r.roe_score,
        "roce_score": r.roce_score,
        "debt_score": r.debt_score,
        "revenue_growth_score": r.revenue_growth_score,
        "eps_growth_score": r.eps_growth_score,
        "cash_flow_score": r.cash_flow_score,
        "valuation_score": r.valuation_score,
        "roe_signal": r.roe_signal,
        "roce_signal": r.roce_signal,
        "debt_signal": r.debt_signal,
        "revenue_growth_signal": r.revenue_growth_signal,
        "eps_growth_signal": r.eps_growth_signal,
        "cash_flow_signal": r.cash_flow_signal,
        "valuation_signal": r.valuation_signal,
    }


@router.post("/scan/all", summary="Scan all active symbols")
async def scan_all(
    current_user: User = Depends(deps.get_current_active_superuser),
    service: FundamentalScannerService = Depends(_get_service),
) -> dict[str, Any]:
    results = await service.scan_all()
    return {
        "scanned": len(results),
        "scan_date": date.today().isoformat(),
    }


@router.post("/scan/{symbol}", summary="Scan a single symbol")
async def scan_symbol(
    symbol: str,
    current_user: User = Depends(deps.get_current_active_user),
    service: FundamentalScannerService = Depends(_get_service),
) -> dict[str, Any]:
    result = await service.scan_symbol(symbol)
    return _scan_dict(result)


@router.get("/rankings", summary="Get ranked scan results")
async def get_rankings(
    scan_date: date | None = None,
    min_score: float = Query(0.0, ge=0, le=100),
    limit: int = Query(100, ge=1, le=500),
    service: FundamentalScannerService = Depends(_get_service),
) -> list[dict[str, Any]]:
    d = scan_date
    results = await service.get_rankings(d, min_score, limit)
    return [_scan_dict(r) for r in results]


@router.get("/results/{symbol}", summary="Get latest scan for a symbol")
async def get_latest_scan(
    symbol: str,
    service: FundamentalScannerService = Depends(_get_service),
) -> dict[str, Any]:
    result = await service.get_latest_scan(symbol.upper())
    if not result:
        raise HTTPException(404, "No scan result found")
    return _scan_dict(result)


@router.get("/results/{symbol}/history", summary="Get scan history for a symbol")
async def get_scan_history(
    symbol: str,
    limit: int = Query(30, ge=1, le=365),
    service: FundamentalScannerService = Depends(_get_service),
) -> list[dict[str, Any]]:
    results = await service.get_scan_history(symbol.upper(), limit)
    return [_scan_dict(r) for r in results]


@router.get("/top-by-dimension/{dimension}", summary="Get top by dimension")
async def get_top_by_dimension(
    dimension: str,
    scan_date: date | None = None,
    limit: int = Query(20, ge=1, le=100),
    service: FundamentalScannerService = Depends(_get_service),
) -> list[dict[str, Any]]:
    d = scan_date
    results = await service.get_top_by_dimension(dimension, d, limit)
    return [_scan_dict(r) for r in results]


@router.get("/summary", summary="Get scan summary")
async def get_scan_summary(
    scan_date: date | None = None,
    service: FundamentalScannerService = Depends(_get_service),
) -> dict[str, Any]:
    d = scan_date
    return await service.get_scan_summary(d)


@router.get("/dates", summary="Get all scan dates")
async def get_all_scan_dates(
    service: FundamentalScannerService = Depends(_get_service),
) -> list[str]:
    dates = await service.get_all_scan_dates()
    return [d.isoformat() for d in dates]
