from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from titan_x.api.dependencies import get_corporate_action_service, get_price_service, require_api_key
from titan_x.api.schemas import MessageResponse, PaginatedResponse
from titan_x.services.price_service import CorporateActionService, PriceService

prices_router = APIRouter(
    prefix="/prices",
    tags=["prices"],
    dependencies=[Depends(require_api_key)],
)

corp_actions_router = APIRouter(
    prefix="/corporate-actions",
    tags=["corporate-actions"],
    dependencies=[Depends(require_api_key)],
)


class PriceResponse(BaseModel):
    id: int
    symbol: str
    trade_date: date
    open: float
    high: float
    low: float
    close: float
    volume: int


class PriceCreateRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=16)
    trade_date: date
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    volume: int = Field(ge=0)


class PriceBulkImportResponse(BaseModel):
    total: int
    created: int
    skipped_duplicates: int
    errors: list[dict[str, Any]]
    warnings: list[str]


class AdjustedPriceResponse(BaseModel):
    id: int
    symbol: str
    trade_date: date
    open: float
    high: float
    low: float
    close: float
    volume: int
    adjustment_factor: float


class CorporateActionResponse(BaseModel):
    id: int
    symbol: str
    action_date: date
    action_type: str
    description: str | None
    ratio_numerator: float | None
    ratio_denominator: float | None
    dividend_amount: float | None
    adjustment_factor: float | None


class CorporateActionCreateRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=16)
    action_date: date
    action_type: str = Field(pattern=r"^(split|bonus|dividend|rights|merger|delisting|other)$")
    description: str | None = Field(default=None, max_length=1000)
    ratio_numerator: float | None = Field(default=None, gt=0)
    ratio_denominator: float | None = Field(default=None, gt=0)
    dividend_amount: float | None = Field(default=None, ge=0)
    adjustment_factor: float | None = Field(default=None, gt=0)


@ prices_router.get("/{symbol}", response_model=PaginatedResponse[PriceResponse])
async def list_prices(
    symbol: str,
    service: Annotated[PriceService, Depends(get_price_service)],
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
) -> PaginatedResponse[PriceResponse]:
    prices, total = await service.get_prices(
        symbol, start_date=start_date, end_date=end_date,
        skip=skip, limit=limit,
    )
    items = [PriceResponse(**p.__dict__) for p in prices]
    return PaginatedResponse(items=items, total=total, skip=skip, limit=limit)


@ prices_router.get("/{symbol}/latest", response_model=PriceResponse | None)
async def get_latest_price(
    symbol: str,
    service: Annotated[PriceService, Depends(get_price_service)],
) -> PriceResponse | None:
    price = await service.get_latest_price(symbol)
    if price is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No prices found for symbol")
    return PriceResponse(**price.__dict__)


@ prices_router.post("", response_model=PriceResponse, status_code=status.HTTP_201_CREATED)
async def create_price(
    body: PriceCreateRequest,
    service: Annotated[PriceService, Depends(get_price_service)],
) -> PriceResponse:
    try:
        price = await service.create_price(
            symbol=body.symbol, trade_date=body.trade_date,
            open=body.open, high=body.high, low=body.low,
            close=body.close, volume=body.volume,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return PriceResponse(**price.__dict__)


@ prices_router.delete("/{price_id}", response_model=MessageResponse)
async def delete_price(
    price_id: int,
    service: Annotated[PriceService, Depends(get_price_service)],
) -> MessageResponse:
    deleted = await service.delete_price(price_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Price not found")
    return MessageResponse(message="Price deleted")


@ prices_router.post("/bulk/{symbol}", response_model=PriceBulkImportResponse)
async def bulk_import(
    symbol: str,
    records: list[dict[str, Any]],
    service: Annotated[PriceService, Depends(get_price_service)],
) -> PriceBulkImportResponse:
    result = await service.bulk_import(symbol, records)
    return PriceBulkImportResponse(
        total=result.total, created=result.created,
        skipped_duplicates=result.skipped_duplicates,
        errors=result.errors, warnings=result.warnings,
    )


@ prices_router.post("/bulk/{symbol}/csv", response_model=PriceBulkImportResponse)
async def bulk_import_csv(
    symbol: str,
    body: dict[str, str],
    service: Annotated[PriceService, Depends(get_price_service)],
) -> PriceBulkImportResponse:
    csv_content: str = body.get("csv", "")
    if not csv_content.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="CSV content is required")
    result = await service.bulk_import_csv(symbol, csv_content)
    return PriceBulkImportResponse(
        total=result.total, created=result.created,
        skipped_duplicates=result.skipped_duplicates,
        errors=result.errors, warnings=result.warnings,
    )


@ prices_router.post("/{symbol}/adjust", response_model=dict[str, int])
async def compute_adjusted_prices(
    symbol: str,
    service: Annotated[PriceService, Depends(get_price_service)],
) -> dict[str, int]:
    count = await service.compute_adjusted_prices(symbol)
    return {"adjusted_count": count}


@ prices_router.get("/{symbol}/adjusted", response_model=PaginatedResponse[AdjustedPriceResponse])
async def list_adjusted_prices(
    symbol: str,
    service: Annotated[PriceService, Depends(get_price_service)],
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
) -> PaginatedResponse[AdjustedPriceResponse]:
    from sqlalchemy import select
    from titan_x.models.price import AdjustedPrice
    stmt = select(AdjustedPrice).where(AdjustedPrice.symbol == symbol.upper()).order_by(AdjustedPrice.trade_date.desc())
    total_result = await service._session.execute(stmt)
    total = len(total_result.scalars().all())
    stmt = stmt.offset(skip).limit(limit)
    result = await service._session.execute(stmt)
    items = [AdjustedPriceResponse(**p.__dict__) for p in result.scalars().all()]
    return PaginatedResponse(items=items, total=total, skip=skip, limit=limit)


@ corp_actions_router.get("/{symbol}", response_model=PaginatedResponse[CorporateActionResponse])
async def list_corporate_actions(
    symbol: str,
    service: Annotated[CorporateActionService, Depends(get_corporate_action_service)],
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
) -> PaginatedResponse[CorporateActionResponse]:
    actions, total = await service.list_for_symbol(symbol, skip=skip, limit=limit)
    items = [CorporateActionResponse(**a.__dict__) for a in actions]
    return PaginatedResponse(items=items, total=total, skip=skip, limit=limit)


@ corp_actions_router.post("", response_model=CorporateActionResponse, status_code=status.HTTP_201_CREATED)
async def create_corporate_action(
    body: CorporateActionCreateRequest,
    service: Annotated[CorporateActionService, Depends(get_corporate_action_service)],
) -> CorporateActionResponse:
    try:
        action = await service.create(
            symbol=body.symbol, action_date=body.action_date,
            action_type=body.action_type, description=body.description,
            ratio_numerator=body.ratio_numerator, ratio_denominator=body.ratio_denominator,
            dividend_amount=body.dividend_amount, adjustment_factor=body.adjustment_factor,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return CorporateActionResponse(**action.__dict__)


@ corp_actions_router.delete("/{action_id}", response_model=MessageResponse)
async def delete_corporate_action(
    action_id: int,
    service: Annotated[CorporateActionService, Depends(get_corporate_action_service)],
) -> MessageResponse:
    deleted = await service.delete(action_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Corporate action not found")
    return MessageResponse(message="Corporate action deleted")
