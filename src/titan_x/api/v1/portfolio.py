from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from titan_x.api.dependencies import get_portfolio_engine, require_api_key
from titan_x.api.schemas import MessageResponse, PaginatedResponse
from titan_x.services.portfolio_engine import PortfolioEngine

portfolio_router = APIRouter(
    prefix="/portfolio",
    tags=["portfolio"],
    dependencies=[Depends(require_api_key)],
)


class PortfolioResponse(BaseModel):
    id: int | None = None
    name: str
    description: str | None = None
    metadata_json: str | None = None
    created_at: str | None = None


class HoldingResponse(BaseModel):
    symbol: str
    sector: str | None = None
    quantity: float
    average_price: float | None = None
    cost_basis: float | None = None
    current_price: float | None = None
    market_value: float
    unrealized_pnl: float
    allocation_pct: float
    as_of_date: str | None = None


class HoldingsResponse(BaseModel):
    holdings: list[HoldingResponse]
    summary: dict


class TransactionResponse(BaseModel):
    id: int
    portfolio_id: int
    symbol: str
    transaction_type: str
    quantity: float
    price: float
    total_amount: float
    transaction_date: str
    realized_pnl: float | None = None
    notes: str | None = None


class PnLResponse(BaseModel):
    realized_pnl: float
    unrealized_pnl: float
    total_pnl: float


class AllocationItem(BaseModel):
    symbol: str
    allocation_pct: float
    market_value: float


class SectorAllocationItem(BaseModel):
    sector: str
    allocation_pct: float
    market_value: float


class AveragePriceResponse(BaseModel):
    symbol: str
    average_price: float | None = None
    quantity: float
    cost_basis: float | None = None


class PortfolioSummaryResponse(BaseModel):
    portfolio: PortfolioResponse
    holdings: list[HoldingResponse]
    pnl: PnLResponse
    allocation: list[AllocationItem]
    sector_allocation: list[SectorAllocationItem]
    summary: dict


@portfolio_router.post("", response_model=PortfolioResponse, status_code=status.HTTP_201_CREATED)
async def create_portfolio(
    engine: Annotated[PortfolioEngine, Depends(get_portfolio_engine)],
    name: str = Query(..., min_length=1, max_length=128),
    description: str | None = Query(None),
) -> PortfolioResponse:
    return PortfolioResponse(**(await engine.create_portfolio(name, description)))


@portfolio_router.get("", response_model=PaginatedResponse[PortfolioResponse])
async def list_portfolios(
    engine: Annotated[PortfolioEngine, Depends(get_portfolio_engine)],
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
) -> PaginatedResponse[PortfolioResponse]:
    rows, total = await engine.list_portfolios(skip, limit)
    items = [PortfolioResponse(**{
        "id": r.id, "name": r.name, "description": r.description,
        "metadata_json": r.metadata_json,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }) for r in rows]
    return PaginatedResponse(items=items, total=total, skip=skip, limit=limit)


@portfolio_router.get("/{portfolio_id}", response_model=PortfolioResponse)
async def get_portfolio(
    portfolio_id: int,
    engine: Annotated[PortfolioEngine, Depends(get_portfolio_engine)],
) -> PortfolioResponse:
    portfolio = await engine.get_portfolio(portfolio_id)
    if portfolio is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Portfolio not found")
    return PortfolioResponse(**{
        "id": portfolio.id, "name": portfolio.name, "description": portfolio.description,
        "metadata_json": portfolio.metadata_json,
        "created_at": portfolio.created_at.isoformat() if portfolio.created_at else None,
    })


@portfolio_router.delete("/{portfolio_id}", response_model=MessageResponse)
async def delete_portfolio(
    portfolio_id: int,
    engine: Annotated[PortfolioEngine, Depends(get_portfolio_engine)],
) -> MessageResponse:
    deleted = await engine.delete_portfolio(portfolio_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Portfolio not found")
    return MessageResponse(message="Portfolio deleted")


@portfolio_router.post("/{portfolio_id}/transactions", response_model=TransactionResponse, status_code=status.HTTP_201_CREATED)
async def add_transaction(
    portfolio_id: int,
    engine: Annotated[PortfolioEngine, Depends(get_portfolio_engine)],
    symbol: str = Query(..., min_length=1, max_length=16),
    transaction_type: str = Query(..., pattern="^(buy|sell)$"),
    quantity: float = Query(..., gt=0),
    price: float = Query(..., gt=0),
    transaction_date: date | None = Query(None),
    notes: str | None = Query(None),
) -> TransactionResponse:
    try:
        result = await engine.record_transaction(
            portfolio_id, symbol, transaction_type, quantity, price, transaction_date, notes,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return TransactionResponse(**result)


@portfolio_router.get("/{portfolio_id}/transactions", response_model=PaginatedResponse[TransactionResponse])
async def list_transactions(
    portfolio_id: int,
    engine: Annotated[PortfolioEngine, Depends(get_portfolio_engine)],
    symbol: str | None = Query(None),
    transaction_type: str | None = Query(None, pattern="^(buy|sell)?$"),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
) -> PaginatedResponse[TransactionResponse]:
    rows, total = await engine.get_transactions(
        portfolio_id, symbol, transaction_type, start_date, end_date, skip, limit,
    )
    items = [TransactionResponse(**{
        "id": r.id, "portfolio_id": r.portfolio_id, "symbol": r.symbol,
        "transaction_type": r.transaction_type, "quantity": r.quantity,
        "price": r.price, "total_amount": r.total_amount,
        "transaction_date": r.transaction_date.isoformat() if r.transaction_date else None,
        "realized_pnl": r.realized_pnl, "notes": r.notes,
    }) for r in rows]
    return PaginatedResponse(items=items, total=total, skip=skip, limit=limit)


@portfolio_router.get("/{portfolio_id}/holdings", response_model=HoldingsResponse)
async def get_holdings(
    portfolio_id: int,
    engine: Annotated[PortfolioEngine, Depends(get_portfolio_engine)],
) -> HoldingsResponse:
    holdings, summary = await engine.get_holdings(portfolio_id)
    return HoldingsResponse(
        holdings=[HoldingResponse(**h) for h in holdings],
        summary=summary,
    )


@portfolio_router.get("/{portfolio_id}/pnl", response_model=PnLResponse)
async def get_pnl(
    portfolio_id: int,
    engine: Annotated[PortfolioEngine, Depends(get_portfolio_engine)],
) -> PnLResponse:
    return PnLResponse(**(await engine.get_pnl(portfolio_id)))


@portfolio_router.get("/{portfolio_id}/allocation", response_model=list[AllocationItem])
async def get_allocation(
    portfolio_id: int,
    engine: Annotated[PortfolioEngine, Depends(get_portfolio_engine)],
) -> list[AllocationItem]:
    return [AllocationItem(**a) for a in await engine.get_portfolio_allocation(portfolio_id)]


@portfolio_router.get("/{portfolio_id}/sector-allocation", response_model=list[SectorAllocationItem])
async def get_sector_allocation(
    portfolio_id: int,
    engine: Annotated[PortfolioEngine, Depends(get_portfolio_engine)],
) -> list[SectorAllocationItem]:
    return [SectorAllocationItem(**a) for a in await engine.get_sector_allocation(portfolio_id)]


@portfolio_router.get("/{portfolio_id}/average-price/{symbol}", response_model=AveragePriceResponse)
async def get_average_price(
    portfolio_id: int,
    symbol: str,
    engine: Annotated[PortfolioEngine, Depends(get_portfolio_engine)],
) -> AveragePriceResponse:
    return AveragePriceResponse(**(await engine.get_average_price(portfolio_id, symbol)))


@portfolio_router.get("/{portfolio_id}/summary", response_model=PortfolioSummaryResponse)
async def get_portfolio_summary(
    portfolio_id: int,
    engine: Annotated[PortfolioEngine, Depends(get_portfolio_engine)],
) -> PortfolioSummaryResponse:
    result = await engine.get_portfolio_summary(portfolio_id)
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Portfolio not found")
    return PortfolioSummaryResponse(**result)


@portfolio_router.get("/{portfolio_id}/beta")
async def get_portfolio_beta(
    portfolio_id: int,
    engine: Annotated[PortfolioEngine, Depends(get_portfolio_engine)],
    benchmark: str = "SPY",
    days: int = 252,
) -> dict:
    return await engine.get_portfolio_beta(portfolio_id, benchmark, days)


@portfolio_router.get("/{portfolio_id}/correlation")
async def get_correlation_matrix(
    portfolio_id: int,
    engine: Annotated[PortfolioEngine, Depends(get_portfolio_engine)],
    days: int = 252,
) -> dict:
    return await engine.get_correlation_matrix(portfolio_id, days)


@portfolio_router.get("/{portfolio_id}/diversification")
async def get_diversification(
    portfolio_id: int,
    engine: Annotated[PortfolioEngine, Depends(get_portfolio_engine)],
) -> dict:
    return await engine.get_diversification_metrics(portfolio_id)


@portfolio_router.get("/{portfolio_id}/concentration")
async def get_concentration(
    portfolio_id: int,
    engine: Annotated[PortfolioEngine, Depends(get_portfolio_engine)],
) -> dict:
    return await engine.get_concentration_risk(portfolio_id)


@portfolio_router.get("/{portfolio_id}/sector-exposure")
async def get_sector_exposure(
    portfolio_id: int,
    engine: Annotated[PortfolioEngine, Depends(get_portfolio_engine)],
) -> dict:
    return await engine.get_sector_exposure(portfolio_id)


@portfolio_router.get("/{portfolio_id}/drawdown")
async def get_drawdown(
    portfolio_id: int,
    engine: Annotated[PortfolioEngine, Depends(get_portfolio_engine)],
    days: int = 252,
    confidence: float = 0.95,
) -> dict:
    return await engine.get_expected_drawdown(portfolio_id, days, confidence)


@portfolio_router.get("/{portfolio_id}/risk-score")
async def get_risk_score(
    portfolio_id: int,
    engine: Annotated[PortfolioEngine, Depends(get_portfolio_engine)],
) -> dict:
    return await engine.get_portfolio_risk_score(portfolio_id)


@portfolio_router.get("/{portfolio_id}/risk-report")
async def get_risk_report(
    portfolio_id: int,
    engine: Annotated[PortfolioEngine, Depends(get_portfolio_engine)],
) -> dict:
    result = await engine.get_portfolio_risk_report(portfolio_id)
    if "error" in result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result["error"])
    return result
