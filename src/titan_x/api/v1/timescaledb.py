"""TimescaleDB management API.

Endpoints for inspecting hypertables, chunks, compression, retention,
continuous aggregates, and overall TimescaleDB health metrics.
"""
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.api import deps
from titan_x.api.dependencies import require_api_key
from titan_x.models.user import User
from titan_x.services.timescaledb_service import (
    HYPERTABLE_CONFIG,
    TimescaleDBService,
)

router = APIRouter(
    prefix="/timescaledb",
    tags=["timescaledb"],
    dependencies=[Depends(require_api_key)],
)


async def _get_service(
    session: AsyncSession = Depends(deps.get_session),
) -> TimescaleDBService:
    return TimescaleDBService(session)


@router.get("/status")
async def get_status(
    service: TimescaleDBService = Depends(_get_service),
) -> dict[str, Any]:
    """Check if TimescaleDB is installed and available."""
    available = await service.is_timescaledb_available()
    return {"timescaledb_available": available}


@router.get("/hypertables")
async def list_hypertables(
    service: TimescaleDBService = Depends(_get_service),
) -> list[dict[str, Any]]:
    """List all hypertables and their metadata."""
    return await service.list_hypertables()


@router.get("/hypertables/{table_name}")
async def get_hypertable(
    table_name: str,
    service: TimescaleDBService = Depends(_get_service),
) -> dict[str, Any]:
    """Get details for a specific hypertable."""
    if table_name not in HYPERTABLE_CONFIG:
        raise HTTPException(
            status_code=404,
            detail=f"Table '{table_name}' is not a configured hypertable.",
        )
    details = await service.get_hypertable_details(table_name)
    if details is None:
        raise HTTPException(
            status_code=404,
            detail=f"Hypertable '{table_name}' not found.",
        )
    return details


@router.get("/chunks")
async def list_chunks(
    table_name: str | None = None,
    service: TimescaleDBService = Depends(_get_service),
) -> list[dict[str, Any]]:
    """List chunks for all hypertables or filter by table_name."""
    if table_name and table_name not in HYPERTABLE_CONFIG:
        raise HTTPException(
            status_code=404,
            detail=f"Table '{table_name}' is not a configured hypertable.",
        )
    return await service.list_chunks(table_name)


@router.get("/chunks/{table_name}/detailed")
async def get_chunk_detailed_stats(
    table_name: str,
    service: TimescaleDBService = Depends(_get_service),
) -> list[dict[str, Any]]:
    """Get detailed chunk statistics (size, compression ratio)."""
    if table_name not in HYPERTABLE_CONFIG:
        raise HTTPException(
            status_code=404,
            detail=f"Table '{table_name}' is not a configured hypertable.",
        )
    return await service.get_chunk_detailed_stats(table_name)


@router.get("/compression")
async def list_compression_policies(
    service: TimescaleDBService = Depends(_get_service),
) -> list[dict[str, Any]]:
    """List all compression policies."""
    return await service.list_compression_policies()


@router.get("/compression/{table_name}")
async def get_compression_stats(
    table_name: str,
    service: TimescaleDBService = Depends(_get_service),
) -> dict[str, Any]:
    """Get compression statistics for a specific hypertable."""
    if table_name not in HYPERTABLE_CONFIG:
        raise HTTPException(
            status_code=404,
            detail=f"Table '{table_name}' is not a configured hypertable.",
        )
    return await service.get_compression_stats(table_name)


@router.get("/retention")
async def list_retention_policies(
    service: TimescaleDBService = Depends(_get_service),
) -> list[dict[str, Any]]:
    """List all retention policies."""
    return await service.list_retention_policies()


@router.get("/continuous-aggregates")
async def list_continuous_aggregates(
    service: TimescaleDBService = Depends(_get_service),
) -> list[dict[str, Any]]:
    """List all continuous aggregate views."""
    return await service.list_continuous_aggregates()


@router.post("/continuous-aggregates/{view_name}/refresh")
async def refresh_continuous_aggregate(
    view_name: str,
    service: TimescaleDBService = Depends(_get_service),
) -> dict[str, Any]:
    """Manually refresh a continuous aggregate view."""
    try:
        return await service.refresh_continuous_aggregate(view_name)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to refresh continuous aggregate '{view_name}': {exc}",
        )


@router.post("/hypertables/{table_name}/reorder")
async def reorder_chunks(
    table_name: str,
    index_name: str,
    service: TimescaleDBService = Depends(_get_service),
) -> dict[str, Any]:
    """Reorder chunks on disk for a hypertable to improve query performance."""
    if table_name not in HYPERTABLE_CONFIG:
        raise HTTPException(
            status_code=404,
            detail=f"Table '{table_name}' is not a configured hypertable.",
        )
    try:
        return await service.reorder_chunks(table_name, index_name)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to reorder chunks: {exc}",
        )


@router.get("/stats")
async def get_stats_summary(
    current_user: User = Depends(deps.get_current_active_superuser),
    service: TimescaleDBService = Depends(_get_service),
) -> dict[str, Any]:
    """Get a full TimescaleDB statistics dashboard (superuser only)."""
    return await service.get_stats_summary()
