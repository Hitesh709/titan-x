from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.api.dependencies import get_current_active_user, request_session
from titan_x.models.user import User
from titan_x.services.export_service import ExportService

router = APIRouter(
    prefix="/export",
    tags=["export"],
)

FORMAT_MAP = {
    "csv": ("text/csv; charset=utf-8", "export.csv"),
    "xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "export.xlsx"),
    "pdf": ("application/pdf", "export.pdf"),
}


@router.get("")
async def export_data(
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[AsyncSession, Depends(request_session)],
    format: str = Query("pdf", pattern="^(csv|xlsx|pdf)$"),
) -> Response:
    svc = ExportService(session)
    try:
        content = await svc.export(current_user.id, format)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=str(e))
    media_type, filename = FORMAT_MAP[format]
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
