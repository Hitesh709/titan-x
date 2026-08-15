from typing import Annotated

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel

from titan_x.api.dependencies import require_api_key
from titan_x.api.schemas import MessageResponse
from titan_x.core.rbac import Role, require_role
from titan_x.models.user import User

admin_router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_api_key)],
)


class BackupRestoreRequest(BaseModel):
    key: str | None = None


@admin_router.get("/backup/list", response_model=MessageResponse)
async def list_backups(
    user: Annotated[User, Depends(require_role(Role.ADMIN))],
) -> MessageResponse:
    from titan_x.core.config import get_settings
    from titan_x.infrastructure.backup import list_backups as _list_backups

    backups = await _list_backups(get_settings())
    return MessageResponse(message=f"{len(backups)} backup(s) available", data={"backups": backups})


@admin_router.post("/backup/restore", response_model=MessageResponse)
async def restore_backup(
    user: Annotated[User, Depends(require_role(Role.ADMIN))],
    body: BackupRestoreRequest | None = None,
) -> MessageResponse:
    from titan_x.core.config import get_settings
    from titan_x.infrastructure.backup import restore_from_backup

    result = await restore_from_backup(get_settings(), body.key if body else None)
    return MessageResponse(
        message=f"Restore completed from {result['restored_key']}",
        data=result,
    )


@admin_router.get("/backup/download", response_model=None)
async def download_backup_endpoint(
    user: Annotated[User, Depends(require_role(Role.ADMIN))],
    key: str,
) -> Response:
    from titan_x.core.config import get_settings
    from titan_x.infrastructure.backup import download_backup

    data, key = await download_backup(get_settings(), key)
    filename = key.split("/")[-1]
    return Response(
        content=data,
        media_type="application/gzip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
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
