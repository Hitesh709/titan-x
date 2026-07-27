from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from titan_x.api.dependencies import get_current_active_user, request_session
from titan_x.models.user import User
from titan_x.services.preference_service import PreferenceService
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/preferences", tags=["preferences"])


async def get_preference_service(
    session: Annotated[AsyncSession, Depends(request_session)],
) -> PreferenceService:
    return PreferenceService(session)


@router.get("")
async def get_all_preferences(
    user: Annotated[User, Depends(get_current_active_user)],
    svc: Annotated[PreferenceService, Depends(get_preference_service)],
):
    return await svc.get_all_preferences(user.id)


@router.get("/{pref_key}")
async def get_preference(
    pref_key: str,
    user: Annotated[User, Depends(get_current_active_user)],
    svc: Annotated[PreferenceService, Depends(get_preference_service)],
):
    value = await svc.get_preference(user.id, pref_key)
    if value is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Preference not found")
    return {"key": pref_key, "value": value}


@router.put("/{pref_key}")
async def set_preference(
    pref_key: str,
    user: Annotated[User, Depends(get_current_active_user)],
    svc: Annotated[PreferenceService, Depends(get_preference_service)],
    value: str = Query(...),
):
    pref = await svc.set_preference(user.id, pref_key, value)
    return {"key": pref.pref_key, "value": pref.pref_value}


@router.delete("/{pref_key}")
async def delete_preference(
    pref_key: str,
    user: Annotated[User, Depends(get_current_active_user)],
    svc: Annotated[PreferenceService, Depends(get_preference_service)],
):
    ok = await svc.delete_preference(user.id, pref_key)
    return {"deleted": ok}


@router.delete("")
async def clear_all_preferences(
    user: Annotated[User, Depends(get_current_active_user)],
    svc: Annotated[PreferenceService, Depends(get_preference_service)],
):
    count = await svc.delete_all_preferences(user.id)
    return {"deleted_count": count}
