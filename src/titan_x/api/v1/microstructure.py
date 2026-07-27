from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.api.dependencies import get_current_active_user, get_db
from titan_x.models.user import User
from titan_x.services.microstructure_service import MicrostructureService

router = APIRouter(prefix="/microstructure", tags=["microstructure"])


@router.post("/analyze/{symbol}")
async def analyze_microstructure(
    symbol: str,
    as_of_date: date | None = Query(None),
    delivery_quantity: int | None = Query(None),
    total_traded_quantity: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    svc = MicrostructureService(db)
    result = await svc.analyze(symbol.upper(), as_of_date, delivery_quantity, total_traded_quantity)
    return {
        "id": result.id,
        "symbol": result.symbol,
        "as_of_date": result.as_of_date.isoformat(),
        "volume": result.volume,
        "avg_volume_5d": result.avg_volume_5d,
        "avg_volume_20d": result.avg_volume_20d,
        "volume_ratio": result.volume_ratio,
        "volume_percentile_20d": result.volume_percentile_20d,
        "volume_trend": result.volume_trend,
        "delivery_percentage": result.delivery_percentage,
        "delivery_trend": result.delivery_trend,
        "delivery_score": result.delivery_score,
        "avg_spread_pct": result.avg_spread_pct,
        "spread_regime": result.spread_regime,
        "dollar_volume": result.dollar_volume,
        "depth_score": result.depth_score,
        "turnover": result.turnover,
        "turnover_ratio": result.turnover_ratio,
        "free_float_turnover": result.free_float_turnover,
        "amihud_illiquidity": result.amihud_illiquidity,
        "liquidity_score": result.liquidity_score,
        "liquidity_rating": result.liquidity_rating,
    }


@router.get("/analyze/{symbol}")
async def get_analysis(
    symbol: str,
    as_of_date: date | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    svc = MicrostructureService(db)
    result = await svc.get_analysis(symbol.upper(), as_of_date)
    if not result:
        raise HTTPException(404, "Analysis not found")
    return result


@router.get("/analyze/{symbol}/history")
async def list_analysis(
    symbol: str,
    limit: int = Query(30, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    svc = MicrostructureService(db)
    return await svc.list_analysis(symbol.upper(), limit=limit, offset=offset)
