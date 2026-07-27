from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.api.dependencies import get_current_active_user, get_db
from titan_x.models.user import User
from titan_x.services.correlation_service import CorrelationService

router = APIRouter(prefix="/correlation", tags=["correlation"])


@router.post("/stock")
async def calc_stock_correlation(
    symbol_a: str = Query(..., min_length=1),
    symbol_b: str = Query(..., min_length=1),
    lookback_days: int = Query(252, ge=20, le=756),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    svc = CorrelationService(db)
    result = await svc.stock_correlation(symbol_a, symbol_b, lookback_days)
    return {
        "correlation_type": result.correlation_type,
        "symbol_1": result.symbol_1,
        "symbol_2": result.symbol_2,
        "correlation_value": result.correlation_value,
        "samples": result.samples,
        "lookback_days": result.lookback_days,
    }


@router.post("/sector")
async def calc_sector_correlation(
    sector_a: str = Query(..., min_length=1),
    sector_b: str = Query(..., min_length=1),
    lookback_days: int = Query(252, ge=20, le=756),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    svc = CorrelationService(db)
    result = await svc.sector_correlation(sector_a, sector_b, lookback_days)
    return {
        "correlation_type": result.correlation_type,
        "symbol_1": result.symbol_1,
        "symbol_2": result.symbol_2,
        "correlation_value": result.correlation_value,
        "samples": result.samples,
        "lookback_days": result.lookback_days,
    }


@router.post("/index")
async def calc_index_correlation(
    symbol: str = Query(..., min_length=1),
    index_symbol: str = Query("NIFTY", min_length=1),
    lookback_days: int = Query(252, ge=20, le=756),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    svc = CorrelationService(db)
    result = await svc.index_correlation(symbol, index_symbol, lookback_days)
    return {
        "correlation_type": result.correlation_type,
        "symbol": result.symbol_1,
        "index": result.symbol_2,
        "correlation_value": result.correlation_value,
        "samples": result.samples,
        "lookback_days": result.lookback_days,
    }


@router.post("/portfolio")
async def calc_portfolio_correlation(
    symbols: str = Query(..., min_length=1, description="Comma-separated symbols"),
    portfolio_label: str | None = Query(None),
    lookback_days: int = Query(252, ge=20, le=756),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    svc = CorrelationService(db)
    sym_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    if len(sym_list) < 2:
        raise HTTPException(400, "Provide at least 2 symbols")
    result = await svc.portfolio_correlation(sym_list, portfolio_label, lookback_days)
    return {
        "id": result.id,
        "matrix_type": result.matrix_type,
        "label": result.label,
        "symbols": result.symbols_json,
        "matrix": result.matrix_json,
        "metadata": result.metadata_json,
    }


@router.post("/heatmap")
async def calc_heatmap(
    symbols: str = Query(..., min_length=1, description="Comma-separated symbols"),
    lookback_days: int = Query(252, ge=20, le=756),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    svc = CorrelationService(db)
    sym_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    if len(sym_list) < 2:
        raise HTTPException(400, "Provide at least 2 symbols")
    result = await svc.heatmap(sym_list, lookback_days)
    return {
        "id": result.id,
        "symbols": result.symbols_json,
        "matrix": result.matrix_json,
        "metadata": result.metadata_json,
    }


@router.post("/sector-heatmap")
async def calc_sector_heatmap(
    lookback_days: int = Query(252, ge=20, le=756),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    svc = CorrelationService(db)
    result = await svc.sector_heatmap(lookback_days)
    return {
        "id": result.id,
        "sectors": result.symbols_json,
        "matrix": result.matrix_json,
        "metadata": result.metadata_json,
    }


@router.get("/pair/{type}/{sym1}/{sym2}")
async def get_pair(
    type: str, sym1: str, sym2: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    svc = CorrelationService(db)
    result = await svc.get_pair(type, sym1, sym2)
    if not result:
        raise HTTPException(404, "Correlation pair not found")
    return result


@router.get("/matrix/{type}/{label}")
async def get_matrix(
    type: str, label: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    svc = CorrelationService(db)
    result = await svc.get_matrix(type, label)
    if not result:
        raise HTTPException(404, "Correlation matrix not found")
    return result
