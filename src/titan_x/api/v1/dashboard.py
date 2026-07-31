from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.api.dependencies import get_current_active_user, request_session
from titan_x.models.user import User
from titan_x.services.dashboard_service import DashboardService

router = APIRouter(
    prefix="/dashboard",
    tags=["dashboard"],
)


@router.get("")
async def get_dashboard(
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[AsyncSession, Depends(request_session)],
) -> dict:
    svc = DashboardService(session)
    return await svc.get_dashboard(current_user.id)


@router.get("/ai-picks")
async def get_ai_picks(
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[AsyncSession, Depends(request_session)],
) -> list[dict]:
    svc = DashboardService(session)
    return await svc.get_ai_picks(current_user.id)
