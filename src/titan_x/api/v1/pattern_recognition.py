from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from titan_x.api.dependencies import get_pattern_recognition_engine, require_api_key
from titan_x.api.schemas import MessageResponse, PaginatedResponse
from titan_x.services.pattern_recognition_engine import PatternRecognitionEngine

pattern_router = APIRouter(
    prefix="/patterns",
    tags=["patterns"],
    dependencies=[Depends(require_api_key)],
)


class PatternData(BaseModel):
    pattern_type: str
    direction: str
    start_date: str
    end_date: str
    entry_price: float | None
    target_price: float | None
    stop_loss: float | None
    confidence_score: float | None
    pattern_data: dict | None
    ai_classification: dict | None = None
    id: int | None = None


class SRLevel(BaseModel):
    price_level: float
    level_type: str
    strength_score: float | None
    touch_count: int
    first_detected: date
    last_tested: date


class ScanResult(BaseModel):
    symbol: str
    end_date: str
    patterns: list[PatternData]
    support_resistance: dict[str, list[SRLevel | dict]]
    total_patterns: int


class StoredPatternResponse(BaseModel):
    id: int
    symbol: str
    pattern_type: str
    direction: str
    start_date: date
    end_date: date
    entry_price: float | None
    target_price: float | None
    stop_loss: float | None
    confidence_score: float | None
    is_active: bool


class StoredSRResponse(BaseModel):
    id: int
    symbol: str
    level_type: str
    price_level: float
    strength_score: float | None
    touch_count: int
    first_detected: date
    last_tested: date
    is_active: bool


class PatternSummary(BaseModel):
    symbol: str
    total_patterns: int
    pattern_type_counts: dict[str, int]
    direction_counts: dict[str, int]
    top_patterns: list[dict]
    support_levels: list[dict]
    resistance_levels: list[dict]


@pattern_router.get("/types", response_model=list[str])
async def list_pattern_types(
    engine: Annotated[PatternRecognitionEngine, Depends(get_pattern_recognition_engine)],
) -> list[str]:
    return engine.list_pattern_types()


@pattern_router.post("/scan/{symbol}", response_model=ScanResult)
async def scan_symbol(
    symbol: str,
    engine: Annotated[PatternRecognitionEngine, Depends(get_pattern_recognition_engine)],
    end_date: date | None = Query(None),
    store: bool = Query(False),
) -> ScanResult:
    result = await engine.scan_symbol(symbol, end_date, store)
    return ScanResult(**result)


@pattern_router.post("/scan-all", response_model=list[ScanResult])
async def scan_all_symbols(
    engine: Annotated[PatternRecognitionEngine, Depends(get_pattern_recognition_engine)],
    end_date: date | None = Query(None),
    store: bool = Query(False),
) -> list[ScanResult]:
    results = await engine.scan_all_symbols(end_date, store)
    return [ScanResult(**r) for r in results]


@pattern_router.get("/detect/double-top/{symbol}", response_model=list[PatternData])
async def detect_double_top(
    symbol: str,
    engine: Annotated[PatternRecognitionEngine, Depends(get_pattern_recognition_engine)],
    end_date: date | None = Query(None),
) -> list[PatternData]:
    return await engine.detect_double_top(symbol, end_date)


@pattern_router.get("/detect/double-bottom/{symbol}", response_model=list[PatternData])
async def detect_double_bottom(
    symbol: str,
    engine: Annotated[PatternRecognitionEngine, Depends(get_pattern_recognition_engine)],
    end_date: date | None = Query(None),
) -> list[PatternData]:
    return await engine.detect_double_bottom(symbol, end_date)


@pattern_router.get("/detect/cup-handle/{symbol}", response_model=list[PatternData])
async def detect_cup_handle(
    symbol: str,
    engine: Annotated[PatternRecognitionEngine, Depends(get_pattern_recognition_engine)],
    end_date: date | None = Query(None),
) -> list[PatternData]:
    return await engine.detect_cup_handle(symbol, end_date)


@pattern_router.get("/detect/flags/{symbol}", response_model=list[PatternData])
async def detect_flags(
    symbol: str,
    engine: Annotated[PatternRecognitionEngine, Depends(get_pattern_recognition_engine)],
    end_date: date | None = Query(None),
) -> list[PatternData]:
    return await engine.detect_flags(symbol, end_date)


@pattern_router.get("/detect/triangles/{symbol}", response_model=list[PatternData])
async def detect_triangles(
    symbol: str,
    engine: Annotated[PatternRecognitionEngine, Depends(get_pattern_recognition_engine)],
    end_date: date | None = Query(None),
) -> list[PatternData]:
    return await engine.detect_triangles(symbol, end_date)


@pattern_router.get("/support-resistance/{symbol}", response_model=dict)
async def detect_support_resistance(
    symbol: str,
    engine: Annotated[PatternRecognitionEngine, Depends(get_pattern_recognition_engine)],
    end_date: date | None = Query(None),
) -> dict:
    return await engine.detect_support_resistance(symbol, end_date)


@pattern_router.post("/classify/{symbol}", response_model=dict)
async def classify_pattern(
    symbol: str,
    pattern_data: dict,
    engine: Annotated[PatternRecognitionEngine, Depends(get_pattern_recognition_engine)],
) -> dict:
    return await engine.classify_pattern(symbol, pattern_data)


@pattern_router.get("/stored", response_model=PaginatedResponse[StoredPatternResponse])
async def get_stored_patterns(
    engine: Annotated[PatternRecognitionEngine, Depends(get_pattern_recognition_engine)],
    symbol: str | None = Query(None),
    pattern_type: str | None = Query(None),
    direction: str | None = Query(None),
    min_confidence: float | None = Query(None, ge=0, le=100),
    is_active: bool | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
) -> PaginatedResponse[StoredPatternResponse]:
    rows, total = await engine.get_detected_patterns(
        symbol, pattern_type, direction, min_confidence, is_active, skip, limit,
    )
    items = [StoredPatternResponse(**r.__dict__) for r in rows]
    return PaginatedResponse(items=items, total=total, skip=skip, limit=limit)


@pattern_router.get("/support-resistance/stored/{symbol}", response_model=list[StoredSRResponse])
async def get_stored_support_resistance(
    symbol: str,
    engine: Annotated[PatternRecognitionEngine, Depends(get_pattern_recognition_engine)],
    level_type: str | None = Query(None),
) -> list[StoredSRResponse]:
    results = await engine.get_support_resistance(symbol, level_type)
    return [StoredSRResponse(**r.__dict__) for r in results]


@pattern_router.get("/summary/{symbol}", response_model=PatternSummary)
async def get_pattern_summary(
    symbol: str,
    engine: Annotated[PatternRecognitionEngine, Depends(get_pattern_recognition_engine)],
) -> PatternSummary:
    return await engine.get_pattern_summary(symbol)


@pattern_router.patch("/stored/{pattern_id}/active", response_model=StoredPatternResponse)
async def toggle_pattern_active(
    pattern_id: int,
    is_active: bool = Query(...),
    engine: PatternRecognitionEngine = Depends(get_pattern_recognition_engine),
) -> StoredPatternResponse:
    result = await engine.update_pattern_active(pattern_id, is_active)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pattern not found")
    return StoredPatternResponse(**result.__dict__)


@pattern_router.delete("/stored/{pattern_id}", response_model=MessageResponse)
async def delete_pattern(
    pattern_id: int,
    engine: Annotated[PatternRecognitionEngine, Depends(get_pattern_recognition_engine)],
) -> MessageResponse:
    deleted = await engine.delete_pattern(pattern_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pattern not found")
    return MessageResponse(message="Pattern deleted")


@pattern_router.delete("/sr/{sr_id}", response_model=MessageResponse)
async def delete_sr_level(
    sr_id: int,
    engine: Annotated[PatternRecognitionEngine, Depends(get_pattern_recognition_engine)],
) -> MessageResponse:
    deleted = await engine.delete_sr_level(sr_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="S/R level not found")
    return MessageResponse(message="Support/Resistance level deleted")
