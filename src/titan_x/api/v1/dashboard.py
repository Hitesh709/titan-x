import asyncio
import structlog
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.api.dependencies import get_cache, get_current_active_user, request_session
from titan_x.infrastructure.cache import RedisCache
from titan_x.models.user import User
from titan_x.services.dashboard_service import DashboardService

logger = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/dashboard",
    tags=["dashboard"],
)


@router.get("")
async def get_dashboard(
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[AsyncSession, Depends(request_session)],
    cache: Annotated[RedisCache, Depends(get_cache)],
) -> dict:
    cache_key = f"dashboard:{current_user.id}"
    cached: object | None = None
    try:
        cached = await cache.get(cache_key)
    except Exception:  # noqa: BLE001
        logger.warning("dashboard_cache_get_failed", user_id=current_user.id, exc_info=True)
    if cached is not None:
        return cached  # type: ignore[return-value]
    svc = DashboardService(session)
    result = await svc.get_dashboard(current_user.id)
    try:
        asyncio.ensure_future(cache.set(cache_key, result, ttl=30))
    except Exception:  # noqa: BLE001
        logger.warning("dashboard_cache_set_failed", user_id=current_user.id)
    return result


@router.get("/ai-picks")
async def get_ai_picks(
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[AsyncSession, Depends(request_session)],
) -> list[dict]:
    svc = DashboardService(session)
    return await svc.get_ai_picks(current_user.id)
