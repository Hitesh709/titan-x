from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.api import deps
from titan_x.models.user import User
from titan_x.services.market_heatmap_service import MarketHeatmapService

router = APIRouter(prefix="/market-heatmap", tags=["market-heatmap"])


@router.get("")
async def get_market_heatmap(
    as_of_date: date | None = Query(None),
    period: str = Query("1M", regex=r"^(1W|1M|3M|6M|YTD|1Y|3Y|5Y)$"),
    session: AsyncSession = Depends(deps.get_session),
    current_user: User = Depends(deps.get_current_active_user),
):
    service = MarketHeatmapService(session)
    return await service.get_heatmap(as_of_date, period)
