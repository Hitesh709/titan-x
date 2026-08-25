from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.api.dependencies import get_db, require_api_key
from titan_x.models.price import DailyPrice
from titan_x.services.intraday_service import IntradayService
from titan_x.services.technical_strength_engine import score_technical_strength

router = APIRouter(prefix="/technical-strength", tags=["technical-strength"], dependencies=[Depends(require_api_key)])


class TechnicalStrengthResponse(BaseModel):
    symbol: str
    intraday: dict
    delivery: dict


@router.get("/{symbol}", response_model=TechnicalStrengthResponse)
async def technical_strength(
    symbol: str = Path(..., min_length=1, max_length=16),
    resolution: str = Query("5min", pattern=r"^(1min|5min|15min|hourly)$"),
    session: AsyncSession = Depends(get_db),
) -> TechnicalStrengthResponse:
    symbol = symbol.upper()
    intraday_service = IntradayService(session)
    intraday_bars, _ = await intraday_service.get_bars(symbol, resolution, limit=500)
    daily_result = await session.execute(select(DailyPrice).where(DailyPrice.symbol == symbol).order_by(DailyPrice.trade_date.asc()).limit(500))
    daily_bars = list(daily_result.scalars().all())
    if not intraday_bars and not daily_bars:
        raise HTTPException(status_code=404, detail=f"No price data available for {symbol}")

    intra = score_technical_strength(intraday_bars, mode="intraday")
    delivery = score_technical_strength(daily_bars, mode="delivery")
    return TechnicalStrengthResponse(
        symbol=symbol,
        intraday={"score": intra.score, "direction": intra.direction, "label": intra.label, "factors": intra.factors, "evidence": intra.evidence},
        delivery={"score": delivery.score, "direction": delivery.direction, "label": delivery.label, "factors": delivery.factors, "evidence": delivery.evidence},
    )
