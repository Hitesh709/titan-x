from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from sqlalchemy import select as sa_select
from sqlalchemy.orm import selectinload

from titan_x.api.dependencies import get_financial_statement_engine, require_api_key
from titan_x.api.schemas import MessageResponse, PaginatedResponse
from titan_x.models.financial import FinancialStatement
from titan_x.services.financial_statement_engine import FinancialStatementEngine, STANDARD_CONCEPTS

fin_stmt_router = APIRouter(
    prefix="/financial-statements",
    tags=["financial-statements"],
    dependencies=[Depends(require_api_key)],
)


class LineItemResponse(BaseModel):
    concept: str
    label: str | None
    value: float | None
    unit: str | None
    order: int | None


class FinancialStatementResponse(BaseModel):
    id: int
    symbol: str
    fiscal_year: int
    fiscal_period: int
    period_type: str
    statement_type: str
    filing_date: date
    currency: str
    source: str | None
    line_items: list[LineItemResponse]


class RecordStatementRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=16)
    fiscal_year: int = Field(ge=1900, le=2100)
    fiscal_period: int = Field(ge=1, le=4)
    period_type: str = Field(pattern=r"^(quarterly|annual)$")
    statement_type: str = Field(pattern=r"^(balance_sheet|income_statement|cash_flow)$")
    filing_date: date
    line_items: dict[str, float | None]
    currency: str = "USD"
    source: str | None = None


class FinancialRatioResponse(BaseModel):
    return_on_equity: float | None
    return_on_assets: float | None
    debt_to_equity: float | None
    profit_margin: float | None
    asset_turnover: float | None
    interest_coverage: float | None
    operating_cash_flow_ratio: float | None


class MetricSnapshot(BaseModel):
    fiscal_year: int
    fiscal_period: int
    period_type: str
    statement_type: str
    concept_values: dict[str, float | None]


class ConceptsResponse(BaseModel):
    statement_type: str
    concepts: list[dict[str, str]]


@fin_stmt_router.post("", response_model=FinancialStatementResponse, status_code=status.HTTP_201_CREATED)
async def record_statement(
    body: RecordStatementRequest,
    engine: Annotated[FinancialStatementEngine, Depends(get_financial_statement_engine)],
) -> FinancialStatementResponse:
    try:
        stmt = await engine.record_statement(
            symbol=body.symbol, fiscal_year=body.fiscal_year,
            fiscal_period=body.fiscal_period, period_type=body.period_type,
            statement_type=body.statement_type,
            filing_date=body.filing_date, line_items=body.line_items,
            currency=body.currency, source=body.source,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))

    return await _build_response(engine, stmt.id)


@fin_stmt_router.get("/{symbol}", response_model=PaginatedResponse[FinancialStatementResponse])
async def list_statements(
    symbol: str,
    engine: Annotated[FinancialStatementEngine, Depends(get_financial_statement_engine)],
    statement_type: str | None = Query(None, pattern=r"^(balance_sheet|income_statement|cash_flow)$"),
    period_type: str | None = Query(None, pattern=r"^(quarterly|annual)$"),
    fiscal_year: int | None = Query(None, ge=1900, le=2100),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
) -> PaginatedResponse[FinancialStatementResponse]:
    statements, total = await engine.list_statements(
        symbol, statement_type=statement_type, period_type=period_type,
        fiscal_year=fiscal_year, skip=skip, limit=limit,
    )
    items = [FinancialStatementResponse(**s.__dict__, line_items=[
        LineItemResponse(**li.__dict__) for li in s.line_items
    ]) for s in statements]
    return PaginatedResponse(items=items, total=total, skip=skip, limit=limit)


@fin_stmt_router.get("/{symbol}/{statement_type}/{period_type}/{fiscal_year}/{fiscal_period}",
                      response_model=FinancialStatementResponse)
async def get_statement(
    symbol: str, statement_type: str, period_type: str,
    fiscal_year: int, fiscal_period: int,
    engine: Annotated[FinancialStatementEngine, Depends(get_financial_statement_engine)],
) -> FinancialStatementResponse:
    stmt = await engine.get_statement(
        symbol, fiscal_year, fiscal_period, period_type, statement_type,
    )
    if stmt is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Statement not found")
    return FinancialStatementResponse(**stmt.__dict__, line_items=[
        LineItemResponse(**li.__dict__) for li in stmt.line_items
    ])


@fin_stmt_router.get("/{symbol}/quarterly/{statement_type}/{fiscal_year}",
                      response_model=list[FinancialStatementResponse])
async def get_quarterly_statements(
    symbol: str, statement_type: str, fiscal_year: int,
    engine: Annotated[FinancialStatementEngine, Depends(get_financial_statement_engine)],
) -> list[FinancialStatementResponse]:
    statements = await engine.get_quarterly(symbol, statement_type, fiscal_year)
    return [FinancialStatementResponse(**s.__dict__, line_items=[
        LineItemResponse(**li.__dict__) for li in s.line_items
    ]) for s in statements]


@fin_stmt_router.get("/{symbol}/annual/{statement_type}/{fiscal_year}",
                      response_model=FinancialStatementResponse)
async def get_annual_statement(
    symbol: str, statement_type: str, fiscal_year: int,
    engine: Annotated[FinancialStatementEngine, Depends(get_financial_statement_engine)],
) -> FinancialStatementResponse:
    stmt = await engine.get_annual(symbol, statement_type, fiscal_year)
    if stmt is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Annual statement not found")
    return FinancialStatementResponse(**stmt.__dict__, line_items=[
        LineItemResponse(**li.__dict__) for li in stmt.line_items
    ])


@fin_stmt_router.post("/{symbol}/aggregate-annual/{statement_type}/{fiscal_year}",
                       response_model=FinancialStatementResponse)
async def aggregate_annual(
    symbol: str, statement_type: str, fiscal_year: int,
    engine: Annotated[FinancialStatementEngine, Depends(get_financial_statement_engine)],
) -> FinancialStatementResponse:
    try:
        stmt = await engine.aggregate_annual_from_quarters(symbol, statement_type, fiscal_year)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return await _build_response(engine, stmt.id)


@fin_stmt_router.get("/{symbol}/ratios/{fiscal_year}",
                      response_model=FinancialRatioResponse)
async def get_financial_ratios(
    symbol: str, fiscal_year: int,
    engine: Annotated[FinancialStatementEngine, Depends(get_financial_statement_engine)],
    period_type: str = Query("annual", pattern=r"^(quarterly|annual)$"),
) -> FinancialRatioResponse:
    ratios = await engine.get_financial_ratios(symbol, fiscal_year, period_type)
    return FinancialRatioResponse(**ratios)


@fin_stmt_router.get("/{symbol}/metrics",
                      response_model=list[MetricSnapshot])
async def get_metrics(
    symbol: str,
    engine: Annotated[FinancialStatementEngine, Depends(get_financial_statement_engine)],
    concepts: str = Query(description="Comma-separated concept names"),
    period_type: str = Query("annual", pattern=r"^(quarterly|annual)$"),
    limit: int = Query(10, ge=1, le=100),
) -> list[MetricSnapshot]:
    concept_list = [c.strip() for c in concepts.split(",") if c.strip()]
    if not concept_list:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one concept required")
    results = await engine.get_metrics(symbol, concept_list, period_type, limit)
    return [MetricSnapshot(
        fiscal_year=r["fiscal_year"], fiscal_period=r["fiscal_period"],
        period_type=r["period_type"], statement_type=r["statement_type"],
        concept_values={c: r.get(c) for c in concept_list},
    ) for r in results]


@fin_stmt_router.get("/concepts/{statement_type}", response_model=ConceptsResponse)
async def get_concepts(statement_type: str) -> ConceptsResponse:
    concepts = STANDARD_CONCEPTS.get(statement_type, [])
    return ConceptsResponse(statement_type=statement_type, concepts=concepts)


@fin_stmt_router.delete("/{statement_id}", response_model=MessageResponse)
async def delete_statement(
    statement_id: int,
    engine: Annotated[FinancialStatementEngine, Depends(get_financial_statement_engine)],
) -> MessageResponse:
    deleted = await engine.delete_statement(statement_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Statement not found")
    return MessageResponse(message="Financial statement deleted")


async def _build_response(engine: FinancialStatementEngine, stmt_id: int) -> FinancialStatementResponse:
    result = await engine._session.execute(
        sa_select(FinancialStatement)
        .where(FinancialStatement.id == stmt_id)
        .options(selectinload(FinancialStatement.line_items))
    )
    stmt = result.scalar_one()
    return FinancialStatementResponse(**stmt.__dict__, line_items=[
        LineItemResponse(**li.__dict__) for li in stmt.line_items
    ])
