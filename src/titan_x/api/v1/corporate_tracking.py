from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from titan_x.api.dependencies import (
    get_corporate_tracking_service,
    get_current_active_user,
    require_api_key,
)
from titan_x.api.schemas import MessageResponse, PaginatedResponse
from titan_x.models.user import User
from titan_x.services.corporate_tracking_service import CorporateTrackingService

corp_track_router = APIRouter(
    prefix="/corporate-tracking",
    tags=["corporate-tracking"],
    dependencies=[Depends(require_api_key)],
)


# --- Schemas ---

class PromoterTransactionResponse(BaseModel):
    id: int
    company_id: int
    promoter_id: int | None = None
    promoter_name: str
    transaction_type: str
    quantity: int
    price: float
    transaction_date: date
    value: float
    percentage_change: float | None = None
    mode: str
    notes: str | None = None
    created_at: str | None = None

class PromoterTransactionCreateRequest(BaseModel):
    company_id: int
    promoter_id: int | None = None
    promoter_name: str = Field(..., min_length=1, max_length=128)
    transaction_type: str = Field(..., pattern="^(buy|sell)$")
    quantity: int = Field(..., gt=0)
    price: float = Field(..., gt=0)
    transaction_date: date
    value: float | None = None
    percentage_change: float | None = None
    mode: str = "market"
    notes: str | None = None

class PromoterTransactionUpdateRequest(BaseModel):
    promoter_name: str | None = None
    transaction_type: str | None = None
    quantity: int | None = None
    price: float | None = None
    transaction_date: date | None = None
    value: float | None = None
    percentage_change: float | None = None
    mode: str | None = None
    notes: str | None = None

class InsiderTradeResponse(BaseModel):
    id: int
    company_id: int
    insider_name: str
    designation: str | None = None
    transaction_type: str
    quantity: int
    price: float
    transaction_date: date
    value: float
    mode: str
    is_derivative: bool = False
    derivative_type: str | None = None
    exercise_price: float | None = None
    notes: str | None = None
    filing_date: date | None = None
    created_at: str | None = None

class InsiderTradeCreateRequest(BaseModel):
    company_id: int
    insider_name: str = Field(..., min_length=1, max_length=128)
    designation: str | None = None
    transaction_type: str = Field(..., pattern="^(buy|sell)$")
    quantity: int = Field(..., gt=0)
    price: float = Field(..., gt=0)
    transaction_date: date
    value: float | None = None
    mode: str = "market"
    is_derivative: bool = False
    derivative_type: str | None = None
    exercise_price: float | None = None
    notes: str | None = None
    filing_date: date | None = None

class InsiderTradeUpdateRequest(BaseModel):
    insider_name: str | None = None
    designation: str | None = None
    transaction_type: str | None = None
    quantity: int | None = None
    price: float | None = None
    transaction_date: date | None = None
    value: float | None = None
    mode: str | None = None
    is_derivative: bool | None = None
    derivative_type: str | None = None
    exercise_price: float | None = None
    notes: str | None = None
    filing_date: date | None = None

class ShareholdingPatternResponse(BaseModel):
    id: int
    company_id: int
    filing_date: date
    quarter: int
    year: int
    category: str
    shares_held: int | None = None
    percentage: float
    change_percentage: float | None = None
    created_at: str | None = None

class ShareholdingPatternCreateRequest(BaseModel):
    company_id: int
    filing_date: date
    quarter: int = Field(..., ge=1, le=4)
    year: int = Field(..., ge=2000, le=2100)
    category: str = Field(..., min_length=1, max_length=32)
    shares_held: int | None = None
    percentage: float = Field(..., ge=0, le=100)
    change_percentage: float | None = None

class ShareholdingPatternUpdateRequest(BaseModel):
    filing_date: date | None = None
    quarter: int | None = None
    year: int | None = None
    category: str | None = None
    shares_held: int | None = None
    percentage: float | None = None
    change_percentage: float | None = None

class PromoterAnalysisResponse(BaseModel):
    buying_score: float
    selling_score: float
    net_flow: int
    buy_volume: int
    sell_volume: int
    buy_value: float | None = None
    sell_value: float | None = None
    total_transactions: int
    buy_count: int
    sell_count: int
    unique_buy_promoters: int | None = None
    unique_sell_promoters: int | None = None
    cluster_buying: bool | None = None
    concentrated_selling: bool | None = None
    avg_buy_price: float | None = None
    avg_sell_price: float | None = None
    insights: list[str]

class InsiderSentimentResponse(BaseModel):
    sentiment_score: float
    buy_sell_ratio: float | None = None
    total_trades: int
    buy_count: int | None = None
    sell_count: int | None = None
    buy_volume: int | None = None
    sell_volume: int | None = None
    weighted_buy_value: float | None = None
    weighted_sell_value: float | None = None
    derivative_trades: int | None = None
    unusual_clusters: int | None = None
    insights: list[str]

class ShareholdingTrendResponse(BaseModel):
    trend_score: float
    total_records: int
    categories_analyzed: list[str] = []
    category_trends: dict = {}
    score_factors: list = []
    insights: list[str]

class CorporateAnalysisResponse(BaseModel):
    id: int
    company_id: int
    analysis_date: date
    promoter_buying_score: float | None = None
    promoter_selling_score: float | None = None
    insider_sentiment_score: float | None = None
    shareholding_trend_score: float | None = None
    weighted_score: float | None = None
    signal: str | None = None
    confidence: float | None = None
    insights_json: str
    generated_at: str | None = None

class CorporateAnalysisDetailResponse(BaseModel):
    id: int
    company_id: int
    analysis_date: date
    promoter_buying_score: float | None = None
    promoter_selling_score: float | None = None
    insider_sentiment_score: float | None = None
    shareholding_trend_score: float | None = None
    weighted_score: float | None = None
    signal: str | None = None
    confidence: float | None = None
    insights_json: dict
    generated_at: str | None = None


# --- Promoter Transaction Endpoints ---

@corp_track_router.post("/promoter-transactions", status_code=status.HTTP_201_CREATED)
async def create_promoter_transaction(
    body: PromoterTransactionCreateRequest,
    service: Annotated[CorporateTrackingService, Depends(get_corporate_tracking_service)],
) -> PromoterTransactionResponse:
    result = await service.create_promoter_transaction(**body.model_dump())
    return PromoterTransactionResponse(
        id=result.id, company_id=result.company_id,
        promoter_id=result.promoter_id, promoter_name=result.promoter_name,
        transaction_type=result.transaction_type, quantity=result.quantity,
        price=result.price, transaction_date=result.transaction_date,
        value=result.value, percentage_change=result.percentage_change,
        mode=result.mode, notes=result.notes,
        created_at=result.created_at.isoformat() if result.created_at else None,
    )

@corp_track_router.get("/promoter-transactions")
async def list_promoter_transactions(
    service: Annotated[CorporateTrackingService, Depends(get_corporate_tracking_service)],
    company_id: int | None = Query(None),
    transaction_type: str | None = Query(None, pattern="^(buy|sell)$"),
    from_date: date | None = Query(None),
    to_date: date | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
) -> PaginatedResponse[dict]:
    rows, total = await service.list_promoter_transactions(
        company_id=company_id, transaction_type=transaction_type,
        from_date=from_date, to_date=to_date, skip=skip, limit=limit,
    )
    items = [{
        "id": r.id, "company_id": r.company_id,
        "promoter_id": r.promoter_id, "promoter_name": r.promoter_name,
        "transaction_type": r.transaction_type, "quantity": r.quantity,
        "price": r.price, "transaction_date": r.transaction_date.isoformat(),
        "value": r.value, "percentage_change": r.percentage_change,
        "mode": r.mode, "notes": r.notes,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r in rows]
    return PaginatedResponse(items=items, total=total, skip=skip, limit=limit)

@corp_track_router.get("/promoter-transactions/{transaction_id}")
async def get_promoter_transaction(
    transaction_id: int,
    service: Annotated[CorporateTrackingService, Depends(get_corporate_tracking_service)],
) -> dict:
    result = await service.get_promoter_transaction(transaction_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Promoter transaction not found")
    return {
        "id": result.id, "company_id": result.company_id,
        "promoter_id": result.promoter_id, "promoter_name": result.promoter_name,
        "transaction_type": result.transaction_type, "quantity": result.quantity,
        "price": result.price, "transaction_date": result.transaction_date.isoformat(),
        "value": result.value, "percentage_change": result.percentage_change,
        "mode": result.mode, "notes": result.notes,
        "created_at": result.created_at.isoformat() if result.created_at else None,
    }

@corp_track_router.patch("/promoter-transactions/{transaction_id}")
async def update_promoter_transaction(
    transaction_id: int,
    body: PromoterTransactionUpdateRequest,
    service: Annotated[CorporateTrackingService, Depends(get_corporate_tracking_service)],
) -> dict:
    kwargs = body.model_dump(exclude_unset=True)
    result = await service.update_promoter_transaction(transaction_id, **kwargs)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Promoter transaction not found")
    return {
        "id": result.id, "company_id": result.company_id,
        "promoter_id": result.promoter_id, "promoter_name": result.promoter_name,
        "transaction_type": result.transaction_type, "quantity": result.quantity,
        "price": result.price, "transaction_date": result.transaction_date.isoformat(),
        "value": result.value, "percentage_change": result.percentage_change,
        "mode": result.mode, "notes": result.notes,
        "created_at": result.created_at.isoformat() if result.created_at else None,
    }

@corp_track_router.delete("/promoter-transactions/{transaction_id}")
async def delete_promoter_transaction(
    transaction_id: int,
    service: Annotated[CorporateTrackingService, Depends(get_corporate_tracking_service)],
) -> MessageResponse:
    deleted = await service.delete_promoter_transaction(transaction_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Promoter transaction not found")
    return MessageResponse(message="Promoter transaction deleted")


# --- Insider Trade Endpoints ---

@corp_track_router.post("/insider-trades", status_code=status.HTTP_201_CREATED)
async def create_insider_trade(
    body: InsiderTradeCreateRequest,
    service: Annotated[CorporateTrackingService, Depends(get_corporate_tracking_service)],
) -> dict:
    result = await service.create_insider_trade(**body.model_dump())
    return {
        "id": result.id, "company_id": result.company_id,
        "insider_name": result.insider_name, "designation": result.designation,
        "transaction_type": result.transaction_type, "quantity": result.quantity,
        "price": result.price, "transaction_date": result.transaction_date.isoformat(),
        "value": result.value, "mode": result.mode,
        "is_derivative": result.is_derivative, "derivative_type": result.derivative_type,
        "exercise_price": result.exercise_price, "notes": result.notes,
        "filing_date": result.filing_date.isoformat() if result.filing_date else None,
        "created_at": result.created_at.isoformat() if result.created_at else None,
    }

@corp_track_router.get("/insider-trades")
async def list_insider_trades(
    service: Annotated[CorporateTrackingService, Depends(get_corporate_tracking_service)],
    company_id: int | None = Query(None),
    transaction_type: str | None = Query(None, pattern="^(buy|sell)$"),
    from_date: date | None = Query(None),
    to_date: date | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
) -> PaginatedResponse[dict]:
    rows, total = await service.list_insider_trades(
        company_id=company_id, transaction_type=transaction_type,
        from_date=from_date, to_date=to_date, skip=skip, limit=limit,
    )
    items = [{
        "id": r.id, "company_id": r.company_id,
        "insider_name": r.insider_name, "designation": r.designation,
        "transaction_type": r.transaction_type, "quantity": r.quantity,
        "price": r.price, "transaction_date": r.transaction_date.isoformat(),
        "value": r.value, "mode": r.mode,
        "is_derivative": r.is_derivative, "derivative_type": r.derivative_type,
        "exercise_price": r.exercise_price, "notes": r.notes,
        "filing_date": r.filing_date.isoformat() if r.filing_date else None,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r in rows]
    return PaginatedResponse(items=items, total=total, skip=skip, limit=limit)

@corp_track_router.get("/insider-trades/{trade_id}")
async def get_insider_trade(
    trade_id: int,
    service: Annotated[CorporateTrackingService, Depends(get_corporate_tracking_service)],
) -> dict:
    result = await service.get_insider_trade(trade_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Insider trade not found")
    return {
        "id": result.id, "company_id": result.company_id,
        "insider_name": result.insider_name, "designation": result.designation,
        "transaction_type": result.transaction_type, "quantity": result.quantity,
        "price": result.price, "transaction_date": result.transaction_date.isoformat(),
        "value": result.value, "mode": result.mode,
        "is_derivative": result.is_derivative, "derivative_type": result.derivative_type,
        "exercise_price": result.exercise_price, "notes": result.notes,
        "filing_date": result.filing_date.isoformat() if result.filing_date else None,
        "created_at": result.created_at.isoformat() if result.created_at else None,
    }

@corp_track_router.patch("/insider-trades/{trade_id}")
async def update_insider_trade(
    trade_id: int,
    body: InsiderTradeUpdateRequest,
    service: Annotated[CorporateTrackingService, Depends(get_corporate_tracking_service)],
) -> dict:
    kwargs = body.model_dump(exclude_unset=True)
    result = await service.update_insider_trade(trade_id, **kwargs)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Insider trade not found")
    return {
        "id": result.id, "company_id": result.company_id,
        "insider_name": result.insider_name, "designation": result.designation,
        "transaction_type": result.transaction_type, "quantity": result.quantity,
        "price": result.price, "transaction_date": result.transaction_date.isoformat(),
        "value": result.value, "mode": result.mode,
        "is_derivative": result.is_derivative, "derivative_type": result.derivative_type,
        "exercise_price": result.exercise_price, "notes": result.notes,
        "filing_date": result.filing_date.isoformat() if result.filing_date else None,
        "created_at": result.created_at.isoformat() if result.created_at else None,
    }

@corp_track_router.delete("/insider-trades/{trade_id}")
async def delete_insider_trade(
    trade_id: int,
    service: Annotated[CorporateTrackingService, Depends(get_corporate_tracking_service)],
) -> MessageResponse:
    deleted = await service.delete_insider_trade(trade_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Insider trade not found")
    return MessageResponse(message="Insider trade deleted")


# --- Shareholding Pattern Endpoints ---

@corp_track_router.post("/shareholding-patterns", status_code=status.HTTP_201_CREATED)
async def create_shareholding_pattern(
    body: ShareholdingPatternCreateRequest,
    service: Annotated[CorporateTrackingService, Depends(get_corporate_tracking_service)],
) -> dict:
    result = await service.create_shareholding_pattern(**body.model_dump())
    return {
        "id": result.id, "company_id": result.company_id,
        "filing_date": result.filing_date.isoformat(),
        "quarter": result.quarter, "year": result.year,
        "category": result.category, "shares_held": result.shares_held,
        "percentage": result.percentage, "change_percentage": result.change_percentage,
        "created_at": result.created_at.isoformat() if result.created_at else None,
    }

@corp_track_router.get("/shareholding-patterns")
async def list_shareholding_patterns(
    service: Annotated[CorporateTrackingService, Depends(get_corporate_tracking_service)],
    company_id: int | None = Query(None),
    category: str | None = Query(None, max_length=32),
    year: int | None = Query(None, ge=2000, le=2100),
    quarter: int | None = Query(None, ge=1, le=4),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
) -> PaginatedResponse[dict]:
    rows, total = await service.list_shareholding_patterns(
        company_id=company_id, category=category, year=year, quarter=quarter,
        skip=skip, limit=limit,
    )
    items = [{
        "id": r.id, "company_id": r.company_id,
        "filing_date": r.filing_date.isoformat(),
        "quarter": r.quarter, "year": r.year,
        "category": r.category, "shares_held": r.shares_held,
        "percentage": r.percentage, "change_percentage": r.change_percentage,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r in rows]
    return PaginatedResponse(items=items, total=total, skip=skip, limit=limit)

@corp_track_router.get("/shareholding-patterns/{pattern_id}")
async def get_shareholding_pattern(
    pattern_id: int,
    service: Annotated[CorporateTrackingService, Depends(get_corporate_tracking_service)],
) -> dict:
    result = await service.get_shareholding_pattern(pattern_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shareholding pattern not found")
    return {
        "id": result.id, "company_id": result.company_id,
        "filing_date": result.filing_date.isoformat(),
        "quarter": result.quarter, "year": result.year,
        "category": result.category, "shares_held": result.shares_held,
        "percentage": result.percentage, "change_percentage": result.change_percentage,
        "created_at": result.created_at.isoformat() if result.created_at else None,
    }

@corp_track_router.patch("/shareholding-patterns/{pattern_id}")
async def update_shareholding_pattern(
    pattern_id: int,
    body: ShareholdingPatternUpdateRequest,
    service: Annotated[CorporateTrackingService, Depends(get_corporate_tracking_service)],
) -> dict:
    kwargs = body.model_dump(exclude_unset=True)
    result = await service.update_shareholding_pattern(pattern_id, **kwargs)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shareholding pattern not found")
    return {
        "id": result.id, "company_id": result.company_id,
        "filing_date": result.filing_date.isoformat(),
        "quarter": result.quarter, "year": result.year,
        "category": result.category, "shares_held": result.shares_held,
        "percentage": result.percentage, "change_percentage": result.change_percentage,
        "created_at": result.created_at.isoformat() if result.created_at else None,
    }

@corp_track_router.delete("/shareholding-patterns/{pattern_id}")
async def delete_shareholding_pattern(
    pattern_id: int,
    service: Annotated[CorporateTrackingService, Depends(get_corporate_tracking_service)],
) -> MessageResponse:
    deleted = await service.delete_shareholding_pattern(pattern_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shareholding pattern not found")
    return MessageResponse(message="Shareholding pattern deleted")


# --- AI Analysis Endpoints ---

@corp_track_router.get("/analyze/promoter/{company_id}")
async def analyze_promoter_activity(
    company_id: int,
    service: Annotated[CorporateTrackingService, Depends(get_corporate_tracking_service)],
) -> PromoterAnalysisResponse:
    return await service.analyze_promoter_activity(company_id)

@corp_track_router.get("/analyze/insider/{company_id}")
async def analyze_insider_sentiment(
    company_id: int,
    service: Annotated[CorporateTrackingService, Depends(get_corporate_tracking_service)],
) -> InsiderSentimentResponse:
    return await service.analyze_insider_sentiment(company_id)

@corp_track_router.get("/analyze/shareholding/{company_id}")
async def analyze_shareholding_trends(
    company_id: int,
    service: Annotated[CorporateTrackingService, Depends(get_corporate_tracking_service)],
) -> ShareholdingTrendResponse:
    return await service.analyze_shareholding_trends(company_id)

@corp_track_router.post("/analyze/{company_id}", status_code=status.HTTP_201_CREATED)
async def generate_analysis(
    company_id: int,
    service: Annotated[CorporateTrackingService, Depends(get_corporate_tracking_service)],
) -> CorporateAnalysisDetailResponse:
    result = await service.generate_analysis(company_id)
    import json
    return CorporateAnalysisDetailResponse(
        id=result.id, company_id=result.company_id,
        analysis_date=result.analysis_date,
        promoter_buying_score=result.promoter_buying_score,
        promoter_selling_score=result.promoter_selling_score,
        insider_sentiment_score=result.insider_sentiment_score,
        shareholding_trend_score=result.shareholding_trend_score,
        weighted_score=result.weighted_score,
        signal=result.signal, confidence=result.confidence,
        insights_json=json.loads(result.insights_json),
        generated_at=result.generated_at.isoformat() if result.generated_at else None,
    )

@corp_track_router.get("/analyze")
async def list_analyses(
    service: Annotated[CorporateTrackingService, Depends(get_corporate_tracking_service)],
    company_id: int | None = Query(None),
    signal: str | None = Query(None, pattern="^(strong_buy|buy|hold|sell|strong_sell)$"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
) -> PaginatedResponse[dict]:
    rows, total = await service.list_analyses(
        company_id=company_id, signal=signal, skip=skip, limit=limit,
    )
    items = [{
        "id": r.id, "company_id": r.company_id,
        "analysis_date": r.analysis_date.isoformat(),
        "promoter_buying_score": r.promoter_buying_score,
        "promoter_selling_score": r.promoter_selling_score,
        "insider_sentiment_score": r.insider_sentiment_score,
        "shareholding_trend_score": r.shareholding_trend_score,
        "weighted_score": r.weighted_score,
        "signal": r.signal, "confidence": r.confidence,
        "generated_at": r.generated_at.isoformat() if r.generated_at else None,
    } for r in rows]
    return PaginatedResponse(items=items, total=total, skip=skip, limit=limit)

@corp_track_router.get("/analyze/latest/{company_id}")
async def get_latest_analysis(
    company_id: int,
    service: Annotated[CorporateTrackingService, Depends(get_corporate_tracking_service)],
) -> CorporateAnalysisDetailResponse:
    result = await service.get_latest_analysis(company_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No analysis found for this company")
    import json
    return CorporateAnalysisDetailResponse(
        id=result.id, company_id=result.company_id,
        analysis_date=result.analysis_date,
        promoter_buying_score=result.promoter_buying_score,
        promoter_selling_score=result.promoter_selling_score,
        insider_sentiment_score=result.insider_sentiment_score,
        shareholding_trend_score=result.shareholding_trend_score,
        weighted_score=result.weighted_score,
        signal=result.signal, confidence=result.confidence,
        insights_json=json.loads(result.insights_json),
        generated_at=result.generated_at.isoformat() if result.generated_at else None,
    )

@corp_track_router.get("/analyze/{analysis_id}")
async def get_analysis(
    analysis_id: int,
    service: Annotated[CorporateTrackingService, Depends(get_corporate_tracking_service)],
) -> CorporateAnalysisDetailResponse:
    result = await service.get_analysis(analysis_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis not found")
    import json
    return CorporateAnalysisDetailResponse(
        id=result.id, company_id=result.company_id,
        analysis_date=result.analysis_date,
        promoter_buying_score=result.promoter_buying_score,
        promoter_selling_score=result.promoter_selling_score,
        insider_sentiment_score=result.insider_sentiment_score,
        shareholding_trend_score=result.shareholding_trend_score,
        weighted_score=result.weighted_score,
        signal=result.signal, confidence=result.confidence,
        insights_json=json.loads(result.insights_json),
        generated_at=result.generated_at.isoformat() if result.generated_at else None,
    )

@corp_track_router.delete("/analyze/{analysis_id}")
async def delete_analysis(
    analysis_id: int,
    service: Annotated[CorporateTrackingService, Depends(get_corporate_tracking_service)],
) -> MessageResponse:
    deleted = await service.delete_analysis(analysis_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis not found")
    return MessageResponse(message="Analysis deleted")
