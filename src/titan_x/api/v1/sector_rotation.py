from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.api import deps
from titan_x.models.user import User
from titan_x.services.sector_rotation_service import SectorRotationService

router = APIRouter(prefix="/sector-rotation", tags=["sector-rotation"])


@router.get("")
async def detect_sector_rotation(
    as_of_date: date | None = Query(None),
    session: AsyncSession = Depends(deps.get_session),
    current_user: User = Depends(deps.get_current_active_user),
):
    service = SectorRotationService(session)
    return await service.detect_rotation(as_of_date)
