from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.api.dependencies import get_current_active_user, request_session
from titan_x.models.user import User
from titan_x.services.top_pick_service import TopPickService

router = APIRouter(
    prefix="/top-picks",
    tags=["top-picks"],
)


@router.get("")
async def get_top_picks(
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[AsyncSession, Depends(request_session)],
    limit: Annotated[int, Query(ge=1, le=20)] = 10,
) -> dict:
    svc = TopPickService(session)
    return await svc.get_top_picks(limit=limit)
