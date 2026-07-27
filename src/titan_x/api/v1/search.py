from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.api.dependencies import get_current_active_user, request_session
from titan_x.models.user import User
from titan_x.services.global_search_service import GlobalSearchService

router = APIRouter(
    prefix="/search",
    tags=["search"],
)


@router.get("")
async def global_search(
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[AsyncSession, Depends(request_session)],
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(10, ge=1, le=50, description="Results per category"),
) -> dict:
    svc = GlobalSearchService(session)
    return await svc.search(q, current_user.id, limit=limit)
