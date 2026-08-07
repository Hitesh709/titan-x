from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.api import deps
from titan_x.models.pattern_library import PATTERN_CATEGORIES
from titan_x.models.user import User
from titan_x.services.pattern_library_service import PatternLibraryService

router = APIRouter(prefix="/pattern-library", tags=["pattern_library"])


async def _get_service(
    session: AsyncSession = Depends(deps.get_session),
) -> PatternLibraryService:
    return PatternLibraryService(session)


def _def_dict(d: Any) -> dict[str, Any]:
    return {
        "id": d.id,
        "name": d.name,
        "category": d.category,
        "description": d.description,
        "ai_pattern_id": d.ai_pattern_id,
        "is_active": d.is_active,
        "version": d.version,
    }


def _inst_dict(i: Any) -> dict[str, Any]:
    return {
        "id": i.id,
        "definition_id": i.definition_id,
        "symbol": i.symbol,
        "category": i.category,
        "direction": i.direction,
        "start_date": i.start_date.isoformat() if i.start_date else None,
        "end_date": i.end_date.isoformat() if i.end_date else None,
        "entry_price": i.entry_price,
        "target_price": i.target_price,
        "stop_loss": i.stop_loss,
        "confidence_score": i.confidence_score,
        "is_active": i.is_active,
    }


@router.post("/definitions", summary="Create a pattern definition")
async def create_definition(
    name: str, category: str, description: str | None = None,
    service: PatternLibraryService = Depends(_get_service),
    current_user: User = Depends(deps.get_current_active_superuser),
) -> dict[str, Any]:
    if category not in PATTERN_CATEGORIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid category: {category}. Must be one of {PATTERN_CATEGORIES}",
        )
    d = await service.create_definition(name, category, description)
    return _def_dict(d)


@router.get("/definitions", summary="List pattern definitions")
async def list_definitions(
    category: str | None = Query(None),
    active_only: bool = Query(True),
    skip: int = Query(0), limit: int = Query(100),
    service: PatternLibraryService = Depends(_get_service),
) -> dict[str, Any]:
    defs, total = await service.list_definitions(category, active_only, skip, limit)
    return {"total": total, "definitions": [_def_dict(d) for d in defs]}


@router.post("/detect/{symbol}", summary="Detect all patterns for a symbol")
async def detect_all(
    symbol: str,
    end_date: date | None = None,
    service: PatternLibraryService = Depends(_get_service),
) -> dict[str, Any]:
    results = await service.detect_all(symbol.upper(), end_date)
    return {
        "symbol": symbol.upper(),
        "candlestick": [_inst_dict(i) for i in results.get("candlestick", [])],
        "volume": [_inst_dict(i) for i in results.get("volume", [])],
        "breakout": [_inst_dict(i) for i in results.get("breakout", [])],
        "gap": [_inst_dict(i) for i in results.get("gap", [])],
        "trend": [_inst_dict(i) for i in results.get("trend", [])],
        "total": sum(len(v) for v in results.values()),
    }


@router.post("/detect/{symbol}/{category}", summary="Detect patterns by category")
async def detect_category(
    symbol: str, category: str,
    end_date: date | None = None,
    service: PatternLibraryService = Depends(_get_service),
) -> dict[str, Any]:
    detect_map = {
        "candlestick": service.detect_candlestick,
        "volume": service.detect_volume,
        "breakout": service.detect_breakout,
        "gap": service.detect_gap,
        "trend": service.detect_trend,
    }
    detector = detect_map.get(category)
    if not detector:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid category: {category}")
    instances = await detector(symbol.upper(), end_date)
    return {"symbol": symbol.upper(), "category": category, "detected": len(instances), "instances": [_inst_dict(i) for i in instances]}


@router.get("/instances", summary="List pattern instances")
async def list_instances(
    symbol: str | None = Query(None),
    category: str | None = Query(None),
    definition_id: int | None = Query(None),
    active_only: bool = Query(True),
    limit: int = Query(100), offset: int = Query(0),
    service: PatternLibraryService = Depends(_get_service),
) -> dict[str, Any]:
    instances = await service.get_instances(symbol, category, definition_id, active_only, limit, offset)
    return {"total": len(instances), "instances": [_inst_dict(i) for i in instances]}


@router.get("/stats/{definition_id}", summary="Instance stats for a definition")
async def instance_stats(
    definition_id: int,
    since: date | None = None,
    service: PatternLibraryService = Depends(_get_service),
) -> dict[str, Any]:
    return await service.get_instance_stats(definition_id, since)
