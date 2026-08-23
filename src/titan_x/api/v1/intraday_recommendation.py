from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from titan_x.api import deps
from titan_x.models.user import User
from titan_x.services.intraday_recommendation_service import get_intraday_recommendations

router = APIRouter(tags=["intraday-recommendations"])


@router.get("/recommendations/intraday")
async def intraday_recommendations(
    segment: str = Query(default="equity", pattern=r"^(equity|fno)$"),
    limit: int = Query(default=10, ge=1, le=20),
    _: User = Depends(deps.get_current_active_user),
):
    """Return live 5-minute intraday opportunities.

    Delivery/short-term recommendations remain on the existing engine. This
    endpoint is intentionally separate so intraday signals cannot overwrite or
    mix with delivery recommendations.
    """
    try:
        return await get_intraday_recommendations(segment=segment, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Intraday market data unavailable: {exc}") from exc
