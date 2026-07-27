from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from titan_x.api.dependencies import (
    get_current_active_user,
    get_user_service,
    require_api_key,
    request_session,
)
from titan_x.api.schemas import (
    MessageResponse,
    PaginatedResponse,
    RegisterResponse,
    UserCreateRequest,
    UserResponse,
    UserUpdateRequest,
)
from titan_x.core.rbac import Role, require_role
from titan_x.models.user import User
from titan_x.services.user_service import UserService

users_router = APIRouter(
    prefix="/admin/users",
    tags=["users"],
    dependencies=[Depends(require_api_key), Depends(require_role(Role.ADMIN))],
)


@users_router.get("", response_model=PaginatedResponse[UserResponse])
async def list_users(
    service: Annotated[UserService, Depends(get_user_service)],
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    order_by: str = Query("id", pattern=r"^(id|email|role|created_at|updated_at)$"),
    descending: bool = Query(False),
    search: str | None = Query(None, min_length=2, max_length=100),
    role: str | None = Query(None, pattern=r"^(normal|premium|analyst|admin)$"),
    is_active: bool | None = Query(None),
    is_verified: bool | None = Query(None),
    is_superuser: bool | None = Query(None),
) -> PaginatedResponse[UserResponse]:
    users, total = await service.list_users(
        skip=skip,
        limit=limit,
        order_by=order_by,
        descending=descending,
        search=search,
        role=role,
        is_active=is_active,
        is_verified=is_verified,
        is_superuser=is_superuser,
    )
    items = [
        UserResponse(
            id=u.id,
            email=u.email,
            role=u.role,
            is_active=u.is_active,
            is_verified=u.is_verified,
            is_superuser=u.is_superuser,
            created_at=u.created_at,
            updated_at=u.updated_at,
        )
        for u in users
    ]
    return PaginatedResponse(items=items, total=total, skip=skip, limit=limit)


@users_router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    service: Annotated[UserService, Depends(get_user_service)],
) -> UserResponse:
    user = await service.get_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return UserResponse(
        id=user.id,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
        is_verified=user.is_verified,
        is_superuser=user.is_superuser,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


@users_router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreateRequest,
    service: Annotated[UserService, Depends(get_user_service)],
) -> UserResponse:
    try:
        user = await service.create_user(
            email=body.email,
            password=body.password,
            role=body.role,
            is_active=body.is_active,
            is_superuser=body.is_superuser,
            is_verified=body.is_verified,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return UserResponse(
        id=user.id,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
        is_verified=user.is_verified,
        is_superuser=user.is_superuser,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


@users_router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    body: UserUpdateRequest,
    service: Annotated[UserService, Depends(get_user_service)],
) -> UserResponse:
    kwargs = body.model_dump(exclude_unset=True)
    try:
        user = await service.update_user(user_id, **kwargs)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return UserResponse(
        id=user.id,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
        is_verified=user.is_verified,
        is_superuser=user.is_superuser,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


@users_router.delete("/{user_id}", response_model=MessageResponse)
async def delete_user(
    user_id: int,
    service: Annotated[UserService, Depends(get_user_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> MessageResponse:
    if current_user.id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete yourself",
        )
    deleted = await service.delete_user(user_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return MessageResponse(message="User deleted")
