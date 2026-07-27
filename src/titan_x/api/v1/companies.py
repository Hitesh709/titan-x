from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from titan_x.api.dependencies import get_company_service, require_api_key
from titan_x.api.schemas import MessageResponse, PaginatedResponse
from titan_x.services.company_service import CompanyService

companies_router = APIRouter(
    prefix="/companies",
    tags=["companies"],
    dependencies=[Depends(require_api_key)],
)


class CompanyResponse(BaseModel):
    id: int
    symbol: str
    company_name: str
    isin: str
    sector: str | None
    industry: str | None
    exchange: str
    market_cap: int | None
    listing_date: date | None
    status: str
    description: str | None
    website: str | None


class CompanyCreateRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=16, pattern=r"^[A-Za-z0-9\.\-]+$")
    company_name: str = Field(min_length=1, max_length=256)
    isin: str = Field(min_length=12, max_length=12, pattern=r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")
    exchange: str = Field(pattern=r"^(NSE|BSE|NYSE|NASDAQ)$")
    sector: str | None = Field(default=None, max_length=128)
    industry: str | None = Field(default=None, max_length=128)
    market_cap: int | None = Field(default=None, ge=0)
    listing_date: date | None = None
    description: str | None = Field(default=None, max_length=2000)
    website: str | None = Field(default=None, max_length=256)


class CompanyUpdateRequest(BaseModel):
    company_name: str | None = Field(default=None, max_length=256)
    sector: str | None = Field(default=None, max_length=128)
    industry: str | None = Field(default=None, max_length=128)
    market_cap: int | None = Field(default=None, ge=0)
    listing_date: date | None = None
    description: str | None = Field(default=None, max_length=2000)
    website: str | None = Field(default=None, max_length=256)
    status: str | None = Field(default=None, pattern=r"^(active|inactive|suspended)$")


@companies_router.get("", response_model=PaginatedResponse[CompanyResponse])
async def list_companies(
    service: Annotated[CompanyService, Depends(get_company_service)],
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    order_by: str = Query("symbol", pattern=r"^(symbol|company_name|exchange|sector|industry|market_cap|listing_date|status)$"),
    descending: bool = Query(False),
    search: str | None = Query(None, min_length=1, max_length=100),
    exchange: str | None = Query(None, pattern=r"^(NSE|BSE|NYSE|NASDAQ)$"),
    sector: str | None = Query(None, max_length=128),
    industry: str | None = Query(None, max_length=128),
    status: str | None = Query(None, pattern=r"^(active|inactive|suspended)$"),
) -> PaginatedResponse[CompanyResponse]:
    companies, total = await service.list(
        skip=skip,
        limit=limit,
        order_by=order_by,
        descending=descending,
        search=search,
        exchange=exchange,
        sector=sector,
        industry=industry,
        status=status,
    )
    items = [CompanyResponse(**c.__dict__) for c in companies]
    return PaginatedResponse(items=items, total=total, skip=skip, limit=limit)


@companies_router.get("/{company_id}", response_model=CompanyResponse)
async def get_company(
    company_id: int,
    service: Annotated[CompanyService, Depends(get_company_service)],
) -> CompanyResponse:
    company = await service.get_by_id(company_id)
    if company is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    return CompanyResponse(**company.__dict__)


@companies_router.post("", response_model=CompanyResponse, status_code=status.HTTP_201_CREATED)
async def create_company(
    body: CompanyCreateRequest,
    service: Annotated[CompanyService, Depends(get_company_service)],
) -> CompanyResponse:
    try:
        company = await service.create(
            symbol=body.symbol,
            company_name=body.company_name,
            isin=body.isin,
            exchange=body.exchange,
            sector=body.sector,
            industry=body.industry,
            market_cap=body.market_cap,
            listing_date=body.listing_date,
            description=body.description,
            website=body.website,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return CompanyResponse(**company.__dict__)


@companies_router.patch("/{company_id}", response_model=CompanyResponse)
async def update_company(
    company_id: int,
    body: CompanyUpdateRequest,
    service: Annotated[CompanyService, Depends(get_company_service)],
) -> CompanyResponse:
    kwargs = body.model_dump(exclude_unset=True)
    try:
        company = await service.update(company_id, **kwargs)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if company is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    return CompanyResponse(**company.__dict__)


@companies_router.delete("/{company_id}", response_model=MessageResponse)
async def delete_company(
    company_id: int,
    service: Annotated[CompanyService, Depends(get_company_service)],
) -> MessageResponse:
    deleted = await service.delete(company_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    return MessageResponse(message="Company deleted")


@companies_router.get("/by-symbol/{symbol}", response_model=CompanyResponse)
async def get_company_by_symbol(
    symbol: str,
    service: Annotated[CompanyService, Depends(get_company_service)],
) -> CompanyResponse:
    company = await service.get_by_symbol(symbol)
    if company is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    return CompanyResponse(**company.__dict__)


@companies_router.get("/by-isin/{isin}", response_model=CompanyResponse)
async def get_company_by_isin(
    isin: str,
    service: Annotated[CompanyService, Depends(get_company_service)],
) -> CompanyResponse:
    company = await service.get_by_isin(isin)
    if company is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    return CompanyResponse(**company.__dict__)


@companies_router.get("/meta/sectors", response_model=list[str])
async def list_sectors(
    service: Annotated[CompanyService, Depends(get_company_service)],
) -> list[str]:
    return await service.list_sectors()


@companies_router.get("/meta/industries", response_model=list[str])
async def list_industries(
    service: Annotated[CompanyService, Depends(get_company_service)],
) -> list[str]:
    return await service.list_industries()


@companies_router.get("/meta/exchanges", response_model=list[str])
async def list_exchanges(
    service: Annotated[CompanyService, Depends(get_company_service)],
) -> list[str]:
    return await service.list_exchanges()
