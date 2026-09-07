from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from titan_x.api import deps
from titan_x.models.user import User

router = APIRouter(prefix="/profile", tags=["profile"])


class ProfileUpdate(BaseModel):
    username: str | None = Field(default=None, min_length=3, max_length=80, pattern=r"^[A-Za-z0-9_.-]+$")
    phone: str | None = Field(default=None, min_length=7, max_length=32)


def payload(user: User) -> dict:
    created = getattr(user, "created_at", None)
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "phone": user.phone,
        "role": user.role,
        "is_active": user.is_active,
        "is_verified": user.is_verified,
        "created_at": created.isoformat() if created else None,
    }


@router.get("/me")
async def get_profile(
    session=Depends(deps.get_session),
    current_user: User = Depends(deps.get_current_active_user),
) -> dict:
    result = await session.execute(select(User).where(User.id == current_user.id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    return payload(user)


@router.patch("/me")
async def update_profile(
    body: ProfileUpdate,
    session=Depends(deps.get_session),
    current_user: User = Depends(deps.get_current_active_user),
) -> dict:
    result = await session.execute(select(User).where(User.id == current_user.id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="Profile not found")

    if body.username is not None:
        username = body.username.strip()
        duplicate = await session.execute(select(User).where(User.username == username, User.id != user.id))
        if duplicate.scalar_one_or_none() is not None:
            raise HTTPException(status_code=409, detail="Username is already registered")
        user.username = username

    if body.phone is not None:
        phone = body.phone.strip()
        duplicate = await session.execute(select(User).where(User.phone == phone, User.id != user.id))
        if duplicate.scalar_one_or_none() is not None:
            raise HTTPException(status_code=409, detail="Mobile number is already registered")
        user.phone = phone

    await session.commit()
    return payload(user)
