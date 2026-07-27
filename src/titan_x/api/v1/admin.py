from typing import Annotated

from fastapi import APIRouter, Depends

from titan_x.api.dependencies import require_api_key
from titan_x.api.schemas import MessageResponse
from titan_x.core.rbac import Role, require_role
from titan_x.models.user import User

admin_router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_api_key)],
)


@admin_router.get("/dashboard", response_model=MessageResponse)
async def admin_dashboard(
    user: Annotated[User, Depends(require_role(Role.ADMIN))],
) -> MessageResponse:
    return MessageResponse(message=f"Welcome admin #{user.id}")


@admin_router.get("/analytics", response_model=MessageResponse)
async def view_analytics(
    user: Annotated[User, Depends(require_role(Role.ANALYST))],
) -> MessageResponse:
    return MessageResponse(message=f"Analytics for user #{user.id}")


@admin_router.get("/premium/content", response_model=MessageResponse)
async def premium_content(
    user: Annotated[User, Depends(require_role(Role.PREMIUM))],
) -> MessageResponse:
    return MessageResponse(message=f"Premium content for user #{user.id}")
