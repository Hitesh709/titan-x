from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from titan_x.api.dependencies import get_health_service
from titan_x.api.schemas import LivenessResponse, ReadinessResponse
from titan_x.services.health_service import HealthService

# Health endpoints are intentionally PUBLIC: Render's healthCheckPath
# (/api/v1/health/live) probes them without credentials. Gating them behind
# require_api_key returned 401, causing Render to treat the instance as
# unhealthy and restart it (recurring downtime / 5xx).
health_router = APIRouter(tags=["health"])


@health_router.get("/health/live", response_model=LivenessResponse)
async def liveness() -> LivenessResponse:
    return LivenessResponse(status="alive")


@health_router.get("/health/ready", response_model=ReadinessResponse)
async def readiness(
    response: Response,
    service: Annotated[HealthService, Depends(get_health_service)],
) -> ReadinessResponse:
    result = await service.readiness()
    if not result.ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(
        status="ready" if result.ready else "unavailable",
        database="available" if result.database else "unavailable",
        redis="available" if result.redis else "unavailable",
    )
