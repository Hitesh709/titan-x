from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from titan_x.api.dependencies import get_corporate_action_engine, require_api_key
from titan_x.api.schemas import MessageResponse, PaginatedResponse
from titan_x.services.corporate_action_engine import CorporateActionEngine

ca_engine_router = APIRouter(
    prefix="/corp-actions-engine",
    tags=["corporate-actions-engine"],
    dependencies=[Depends(require_api_key)],
)


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
    new_symbol: str | None
    old_symbol: str | None
    rights_premium: float | None
    rights_issue_price: float | None


class SplitRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=16)
    action_date: date
    numerator: float = Field(gt=0)
    denominator: float = Field(gt=0)
    description: str | None = None


class BonusRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=16)
    action_date: date
    numerator: float = Field(gt=0)
    denominator: float = Field(gt=0)
    description: str | None = None


class DividendRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=16)
    action_date: date
    dividend_amount: float = Field(ge=0)
    description: str | None = None


class RightsRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=16)
    action_date: date
    numerator: float = Field(gt=0)
    denominator: float = Field(gt=0)
    premium: float = Field(gt=0)
    issue_price: float = Field(gt=0)
    description: str | None = None


class MergerRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=16)
    action_date: date
    numerator: float = Field(gt=0)
    denominator: float = Field(gt=0)
    new_symbol: str = Field(min_length=1, max_length=16)
    description: str | None = None


class AcquisitionRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=16)
    action_date: date
    numerator: float = Field(gt=0)
    denominator: float = Field(gt=0)
    old_symbol: str = Field(min_length=1, max_length=16)
    description: str | None = None


class AdjustPricesResponse(BaseModel):
    symbol: str
    actions_used: int
    prices_adjusted: int


@ca_engine_router.post("/split", response_model=CorporateActionResponse, status_code=status.HTTP_201_CREATED)
async def record_split(
    body: SplitRequest,
    engine: Annotated[CorporateActionEngine, Depends(get_corporate_action_engine)],
) -> CorporateActionResponse:
    try:
        action = await engine.record_split(
            symbol=body.symbol, action_date=body.action_date,
            numerator=body.numerator, denominator=body.denominator,
            description=body.description,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return CorporateActionResponse(**action.__dict__)


@ca_engine_router.post("/bonus", response_model=CorporateActionResponse, status_code=status.HTTP_201_CREATED)
async def record_bonus(
    body: BonusRequest,
    engine: Annotated[CorporateActionEngine, Depends(get_corporate_action_engine)],
) -> CorporateActionResponse:
    try:
        action = await engine.record_bonus(
            symbol=body.symbol, action_date=body.action_date,
            numerator=body.numerator, denominator=body.denominator,
            description=body.description,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return CorporateActionResponse(**action.__dict__)


@ca_engine_router.post("/dividend", response_model=CorporateActionResponse, status_code=status.HTTP_201_CREATED)
async def record_dividend(
    body: DividendRequest,
    engine: Annotated[CorporateActionEngine, Depends(get_corporate_action_engine)],
) -> CorporateActionResponse:
    try:
        action = await engine.record_dividend(
            symbol=body.symbol, action_date=body.action_date,
            dividend_amount=body.dividend_amount, description=body.description,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return CorporateActionResponse(**action.__dict__)


@ca_engine_router.post("/rights", response_model=CorporateActionResponse, status_code=status.HTTP_201_CREATED)
async def record_rights(
    body: RightsRequest,
    engine: Annotated[CorporateActionEngine, Depends(get_corporate_action_engine)],
) -> CorporateActionResponse:
    try:
        action = await engine.record_rights(
            symbol=body.symbol, action_date=body.action_date,
            numerator=body.numerator, denominator=body.denominator,
            premium=body.premium, issue_price=body.issue_price,
            description=body.description,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return CorporateActionResponse(**action.__dict__)


@ca_engine_router.post("/merger", response_model=CorporateActionResponse, status_code=status.HTTP_201_CREATED)
async def record_merger(
    body: MergerRequest,
    engine: Annotated[CorporateActionEngine, Depends(get_corporate_action_engine)],
) -> CorporateActionResponse:
    try:
        action = await engine.record_merger(
            symbol=body.symbol, action_date=body.action_date,
            numerator=body.numerator, denominator=body.denominator,
            new_symbol=body.new_symbol, description=body.description,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return CorporateActionResponse(**action.__dict__)


@ca_engine_router.post("/acquisition", response_model=CorporateActionResponse, status_code=status.HTTP_201_CREATED)
async def record_acquisition(
    body: AcquisitionRequest,
    engine: Annotated[CorporateActionEngine, Depends(get_corporate_action_engine)],
) -> CorporateActionResponse:
    try:
        action = await engine.record_acquisition(
            symbol=body.symbol, action_date=body.action_date,
            numerator=body.numerator, denominator=body.denominator,
            old_symbol=body.old_symbol, description=body.description,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return CorporateActionResponse(**action.__dict__)


@ca_engine_router.get("/{symbol}", response_model=PaginatedResponse[CorporateActionResponse])
async def list_actions(
    symbol: str,
    engine: Annotated[CorporateActionEngine, Depends(get_corporate_action_engine)],
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
) -> PaginatedResponse[CorporateActionResponse]:
    actions, total = await engine.list_actions(symbol, skip=skip, limit=limit)
    items = [CorporateActionResponse(**a.__dict__) for a in actions]
    return PaginatedResponse(items=items, total=total, skip=skip, limit=limit)


@ca_engine_router.get("", response_model=PaginatedResponse[CorporateActionResponse])
async def list_actions_by_type(
    engine: Annotated[CorporateActionEngine, Depends(get_corporate_action_engine)],
    action_type: str = Query(pattern=r"^(split|bonus|dividend|rights|merger|acquisition)$"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
) -> PaginatedResponse[CorporateActionResponse]:
    actions, total = await engine.list_all_by_type(action_type, skip=skip, limit=limit)
    items = [CorporateActionResponse(**a.__dict__) for a in actions]
    return PaginatedResponse(items=items, total=total, skip=skip, limit=limit)


@ca_engine_router.get("/detail/{action_id}", response_model=CorporateActionResponse)
async def get_action(
    action_id: int,
    engine: Annotated[CorporateActionEngine, Depends(get_corporate_action_engine)],
) -> CorporateActionResponse:
    action = await engine.get_action(action_id)
    if action is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action not found")
    return CorporateActionResponse(**action.__dict__)


@ca_engine_router.delete("/{action_id}", response_model=MessageResponse)
async def delete_action(
    action_id: int,
    engine: Annotated[CorporateActionEngine, Depends(get_corporate_action_engine)],
) -> MessageResponse:
    deleted = await engine.delete_action(action_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action not found")
    return MessageResponse(message="Corporate action deleted")


@ca_engine_router.post("/adjust/{symbol}", response_model=AdjustPricesResponse)
async def adjust_prices(
    symbol: str,
    engine: Annotated[CorporateActionEngine, Depends(get_corporate_action_engine)],
) -> AdjustPricesResponse:
    result = await engine.adjust_prices(symbol)
    return AdjustPricesResponse(**result)
