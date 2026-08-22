from datetime import date
import json

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.api import deps
from titan_x.api.schemas import PaginatedResponse
from titan_x.models.user import User
from titan_x.services.advanced_screener_service import AdvancedScreenerService

router = APIRouter(prefix="/screener", tags=["screener"])


class SavedScreenCreate(BaseModel):
    name: str
    description: str | None = None
    filters_json: str


class SavedScreenUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    filters_json: str | None = None


@router.post("/run")
async def run_adhoc_screen(
    filters: dict,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    as_of_date: date | None = Query(None, description="Evaluate historical data as of this date"),
    session: AsyncSession = Depends(deps.get_session),
    current_user: User = Depends(deps.get_current_active_user),
):
    service = AdvancedScreenerService(session)
    return await service.run_screen(
        filters, current_user.id, skip=skip, limit=limit, as_of_date=as_of_date
    )


@router.post("/screens", status_code=status.HTTP_201_CREATED)
async def create_saved_screen(
    body: SavedScreenCreate,
    session: AsyncSession = Depends(deps.get_session),
    current_user: User = Depends(deps.get_current_active_user),
):
    service = AdvancedScreenerService(session)
    return await service.save_screen(current_user.id, body.name, body.filters_json, body.description)


@router.get("/screens")
async def list_saved_screens(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(deps.get_session),
    current_user: User = Depends(deps.get_current_active_user),
):
    service = AdvancedScreenerService(session)
    screens, total = await service.list_screens(current_user.id, skip, limit)
    return PaginatedResponse(items=screens, total=total, skip=skip, limit=limit)


@router.get("/screens/{screen_id}")
async def get_saved_screen(
    screen_id: int,
    session: AsyncSession = Depends(deps.get_session),
    current_user: User = Depends(deps.get_current_active_user),
):
    service = AdvancedScreenerService(session)
    screen = await service.get_screen(screen_id, current_user.id)
    if screen is None:
        raise HTTPException(status_code=404, detail="Saved screen not found")
    return screen


@router.put("/screens/{screen_id}")
async def update_saved_screen(
    screen_id: int,
    body: SavedScreenUpdate,
    session: AsyncSession = Depends(deps.get_session),
    current_user: User = Depends(deps.get_current_active_user),
):
    service = AdvancedScreenerService(session)
    screen = await service.update_screen(
        screen_id, current_user.id,
        name=body.name, description=body.description, filters_json=body.filters_json,
    )
    if screen is None:
        raise HTTPException(status_code=404, detail="Saved screen not found")
    return screen


@router.delete("/screens/{screen_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_saved_screen(
    screen_id: int,
    session: AsyncSession = Depends(deps.get_session),
    current_user: User = Depends(deps.get_current_active_user),
):
    service = AdvancedScreenerService(session)
    deleted = await service.delete_screen(screen_id, current_user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Saved screen not found")


@router.post("/screens/{screen_id}/run")
async def run_saved_screen(
    screen_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    as_of_date: date | None = Query(None, description="Evaluate historical data as of this date"),
    session: AsyncSession = Depends(deps.get_session),
    current_user: User = Depends(deps.get_current_active_user),
):
    service = AdvancedScreenerService(session)
    if as_of_date is None:
        result = await service.run_saved_screen(screen_id, current_user.id, skip, limit)
    else:
        screen = await service.get_screen(screen_id, current_user.id)
        if screen is None:
            raise HTTPException(status_code=404, detail="Saved screen not found")
        filters = json.loads(screen.filters_json)
        result = await service.run_screen(
            filters, current_user.id, screen_id, skip, limit, as_of_date=as_of_date
        )
    if result is None:
        raise HTTPException(status_code=404, detail="Saved screen not found")
    return result
