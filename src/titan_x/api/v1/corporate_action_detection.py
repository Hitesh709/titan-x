from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from titan_x.api.dependencies import (
    get_corporate_action_detector,
    require_api_key,
)
from titan_x.api.schemas import MessageResponse, PaginatedResponse
from titan_x.services.corporate_action_detector import CorporateActionDetector

cad_router = APIRouter(
    prefix="/corp-action-detection",
    tags=["corp-action-detection"],
    dependencies=[Depends(require_api_key)],
)


@cad_router.post("/detect/{symbol}")
async def detect_all(
    symbol: str,
    detector: Annotated[CorporateActionDetector, Depends(get_corporate_action_detector)],
) -> dict:
    return await detector.detect_all(symbol)


@cad_router.post("/detect/{symbol}/splits")
async def detect_splits(
    symbol: str,
    detector: Annotated[CorporateActionDetector, Depends(get_corporate_action_detector)],
) -> list[dict]:
    results = await detector.detect_splits(symbol)
    return [{"id": r.id, "date": str(r.detected_date), "confidence": r.confidence,
             "numerator": r.estimated_numerator, "denominator": r.estimated_denominator} for r in results]


@cad_router.post("/detect/{symbol}/bonuses")
async def detect_bonuses(
    symbol: str,
    detector: Annotated[CorporateActionDetector, Depends(get_corporate_action_detector)],
) -> list[dict]:
    results = await detector.detect_bonuses(symbol)
    return [{"id": r.id, "date": str(r.detected_date), "confidence": r.confidence,
             "numerator": r.estimated_numerator, "denominator": r.estimated_denominator} for r in results]


@cad_router.post("/detect/{symbol}/dividends")
async def detect_dividends(
    symbol: str,
    detector: Annotated[CorporateActionDetector, Depends(get_corporate_action_detector)],
) -> list[dict]:
    results = await detector.detect_dividends(symbol)
    return [{"id": r.id, "date": str(r.detected_date), "confidence": r.confidence,
             "estimated_dividend": r.estimated_dividend_amount} for r in results]


@cad_router.post("/detect/{symbol}/rights")
async def detect_rights(
    symbol: str,
    detector: Annotated[CorporateActionDetector, Depends(get_corporate_action_detector)],
) -> list[dict]:
    results = await detector.detect_rights(symbol)
    return [{"id": r.id, "date": str(r.detected_date), "confidence": r.confidence} for r in results]


@cad_router.post("/detect/{symbol}/mergers")
async def detect_mergers(
    symbol: str,
    detector: Annotated[CorporateActionDetector, Depends(get_corporate_action_detector)],
) -> list[dict]:
    results = await detector.detect_mergers(symbol)
    return [{"id": r.id, "date": str(r.detected_date), "confidence": r.confidence} for r in results]


@cad_router.post("/detect/{symbol}/acquisitions")
async def detect_acquisitions(
    symbol: str,
    detector: Annotated[CorporateActionDetector, Depends(get_corporate_action_detector)],
) -> list[dict]:
    results = await detector.detect_acquisitions(symbol)
    return [{"id": r.id, "date": str(r.detected_date), "confidence": r.confidence} for r in results]


@cad_router.get("/detections")
async def list_detections(
    detector: Annotated[CorporateActionDetector, Depends(get_corporate_action_detector)],
    symbol: str | None = Query(None, max_length=16),
    status: str | None = Query(None, pattern="^(pending|confirmed|rejected)$"),
    detected_type: str | None = Query(None, pattern="^(split|bonus|dividend|rights|merger|acquisition)$"),
    skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500),
) -> PaginatedResponse[dict]:
    rows, total = await detector.list_detections(symbol=symbol, status=status, detected_type=detected_type, skip=skip, limit=limit)
    items = [{
        "id": r.id, "symbol": r.symbol, "detected_type": r.detected_type,
        "detected_date": str(r.detected_date), "confidence": r.confidence,
        "source": r.source, "status": r.status,
        "estimated_numerator": r.estimated_numerator,
        "estimated_denominator": r.estimated_denominator,
        "estimated_dividend_amount": r.estimated_dividend_amount,
        "price_before": r.price_before, "price_after": r.price_after,
        "volume_spike_ratio": r.volume_spike_ratio,
        "confirmed_action_id": r.confirmed_action_id,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r in rows]
    return PaginatedResponse(items=items, total=total, skip=skip, limit=limit)


@cad_router.get("/detections/{detection_id}")
async def get_detection(
    detection_id: int,
    detector: Annotated[CorporateActionDetector, Depends(get_corporate_action_detector)],
) -> dict:
    r = await detector.get_detection(detection_id)
    if r is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Detection not found")
    return {
        "id": r.id, "symbol": r.symbol, "detected_type": r.detected_type,
        "detected_date": str(r.detected_date), "confidence": r.confidence,
        "source": r.source, "status": r.status,
        "estimated_numerator": r.estimated_numerator,
        "estimated_denominator": r.estimated_denominator,
        "estimated_dividend_amount": r.estimated_dividend_amount,
        "estimated_premium": r.estimated_premium,
        "estimated_issue_price": r.estimated_issue_price,
        "target_symbol": r.target_symbol,
        "price_before": r.price_before, "price_after": r.price_after,
        "volume_spike_ratio": r.volume_spike_ratio,
        "signal_details_json": r.signal_details_json,
        "confirmed_action_id": r.confirmed_action_id,
        "confirmed_at": r.confirmed_at.isoformat() if r.confirmed_at else None,
        "notes": r.notes,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


@cad_router.post("/confirm/{detection_id}")
async def confirm_detection(
    detection_id: int,
    detector: Annotated[CorporateActionDetector, Depends(get_corporate_action_detector)],
) -> dict:
    try:
        action = await detector.confirm_detection(detection_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return {"status": "confirmed", "action_id": action.id, "symbol": action.symbol,
            "action_type": action.action_type, "action_date": str(action.action_date)}


@cad_router.post("/confirm-and-adjust/{detection_id}")
async def confirm_and_adjust(
    detection_id: int,
    detector: Annotated[CorporateActionDetector, Depends(get_corporate_action_detector)],
) -> dict:
    try:
        result = await detector.confirm_and_adjust(detection_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return result


@cad_router.post("/auto/{symbol}")
async def auto_detect_and_adjust(
    symbol: str,
    detector: Annotated[CorporateActionDetector, Depends(get_corporate_action_detector)],
    min_confidence: float = Query(50.0, ge=0, le=100),
) -> dict:
    return await detector.auto_detect_and_adjust(symbol, min_confidence=min_confidence)


@cad_router.delete("/detections/{detection_id}")
async def delete_detection(
    detection_id: int,
    detector: Annotated[CorporateActionDetector, Depends(get_corporate_action_detector)],
) -> MessageResponse:
    deleted = await detector.delete_detection(detection_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Detection not found")
    return MessageResponse(message="Detection deleted")
