from typing import Annotated

from fastapi import APIRouter, Depends

from titan_x.api.dependencies import require_api_key
from titan_x.api.schemas import VersionResponse
from titan_x.core.config import Settings, get_settings

version_router = APIRouter(tags=["version"], dependencies=[Depends(require_api_key)])


@version_router.get("/version", response_model=VersionResponse)
async def version(settings: Annotated[Settings, Depends(get_settings)]) -> VersionResponse:
    return VersionResponse(
        version=settings.app_version,
        build_date=settings.app_build_date,
        environment=settings.environment,
    )
