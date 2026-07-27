from collections.abc import Sequence
from datetime import date
from typing import Any

import structlog
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from titan_x.db.repository import BaseRepository
from titan_x.models.financial import FinancialLineItem, FinancialStatement

logger = structlog.get_logger(__name__)


STANDARD_CONCEPTS: dict[str, list[dict[str, str]]] = {
    "balance_sheet": [
        {"concept": "total_assets", "label": "Total Assets", "order": "100"},
        {"concept": "current_assets", "label": "Current Assets", "order": "110"},
        {"concept": "cash_and_equivalents", "label": "Cash and Cash Equivalents", "order": "111"},
        {"concept": "accounts_receivable", "label": "Accounts Receivable", "order": "112"},
        {"concept": "inventory", "label": "Inventory", "order": "113"},
        {"concept": "non_current_assets", "label": "Non-Current Assets", "order": "120"},
        {"concept": "property_plant_equipment", "label": "Property, Plant & Equipment", "order": "121"},
        {"concept": "goodwill", "label": "Goodwill", "order": "122"},
        {"concept": "total_liabilities", "label": "Total Liabilities", "order": "200"},
        {"concept": "current_liabilities", "label": "Current Liabilities", "order": "210"},
        {"concept": "accounts_payable", "label": "Accounts Payable", "order": "211"},
        {"concept": "short_term_debt", "label": "Short-Term Debt", "order": "212"},
        {"concept": "long_term_debt", "label": "Long-Term Debt", "order": "220"},
        {"concept": "total_equity", "label": "Total Equity", "order": "300"},
        {"concept": "retained_earnings", "label": "Retained Earnings", "order": "310"},
        {"concept": "common_stock", "label": "Common Stock", "order": "311"},
        {"concept": "treasury_stock", "label": "Treasury Stock", "order": "312"},
    ],
    "income_statement": [
        {"concept": "revenue", "label": "Revenue", "order": "100"},
        {"concept": "cost_of_revenue", "label": "Cost of Revenue", "order": "110"},
        {"concept": "gross_profit", "label": "Gross Profit", "order": "120"},
        {"concept": "operating_expenses", "label": "Operating Expenses", "order": "200"},
        {"concept": "selling_general_administrative", "label": "SG&A", "order": "210"},
        {"concept": "research_development", "label": "Research & Development", "order": "220"},
        {"concept": "operating_income", "label": "Operating Income", "order": "300"},
        {"concept": "interest_expense", "label": "Interest Expense", "order": "310"},
        {"concept": "income_before_tax", "label": "Income Before Tax", "order": "400"},
        {"concept": "income_tax_expense", "label": "Income Tax Expense", "order": "410"},
        {"concept": "net_income", "label": "Net Income", "order": "500"},
        {"concept": "ebitda", "label": "EBITDA", "order": "510"},
        {"concept": "eps_basic", "label": "EPS (Basic)", "unit": "ratio", "order": "600"},
        {"concept": "eps_diluted", "label": "EPS (Diluted)", "unit": "ratio", "order": "610"},
        {"concept": "shares_outstanding", "label": "Shares Outstanding", "unit": "shares", "order": "700"},
    ],
    "cash_flow": [
        {"concept": "operating_cash_flow", "label": "Operating Cash Flow", "order": "100"},
        {"concept": "depreciation_amortization", "label": "Depreciation & Amortization", "order": "110"},
        {"concept": "stock_based_compensation", "label": "Stock-Based Compensation", "order": "120"},
        {"concept": "changes_in_working_capital", "label": "Changes in Working Capital", "order": "130"},
        {"concept": "investing_cash_flow", "label": "Investing Cash Flow", "order": "200"},
        {"concept": "capital_expenditures", "label": "Capital Expenditures", "order": "210"},
        {"concept": "acquisitions", "label": "Acquisitions", "order": "220"},
        {"concept": "financing_cash_flow", "label": "Financing Cash Flow", "order": "300"},
        {"concept": "dividends_paid", "label": "Dividends Paid", "order": "310"},
        {"concept": "share_repurchases", "label": "Share Repurchases", "order": "320"},
        {"concept": "debt_issuance", "label": "Debt Issuance", "order": "330"},
        {"concept": "free_cash_flow", "label": "Free Cash Flow", "order": "400"},
        {"concept": "net_change_in_cash", "label": "Net Change in Cash", "order": "500"},
    ],
}

CONCEPT_UNITS: dict[str, str] = {}
for _stype, concepts in STANDARD_CONCEPTS.items():
    for c in concepts:
        CONCEPT_UNITS[c["concept"]] = c.get("unit", "USD")


class FinancialStatementEngine:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = BaseRepository(session, FinancialStatement)

    async def record_statement(
        self, symbol: str, fiscal_year: int, fiscal_period: int,
        period_type: str, statement_type: str,
        filing_date: date, line_items: dict[str, float | None],
        currency: str = "USD", source: str | None = None,
    ) -> FinancialStatement:
        symbol = symbol.upper()

        existing = await self._session.execute(
            select(FinancialStatement).where(
                FinancialStatement.symbol == symbol,
                FinancialStatement.fiscal_year == fiscal_year,
                FinancialStatement.fiscal_period == fiscal_period,
                FinancialStatement.period_type == period_type,
                FinancialStatement.statement_type == statement_type,
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise ValueError(
                f"{statement_type} already exists for {symbol} "
                f"FY{fiscal_year} P{fiscal_period} ({period_type})"
            )

        stmt = await self._repo.create(
            symbol=symbol, fiscal_year=fiscal_year, fiscal_period=fiscal_period,
            period_type=period_type, statement_type=statement_type,
            filing_date=filing_date, currency=currency, source=source,
        )

        items_to_create: list[FinancialLineItem] = []
        concepts_meta = STANDARD_CONCEPTS.get(statement_type, [])
        concept_order_map = {c["concept"]: c["order"] for c in concepts_meta}

        for concept, value in line_items.items():
            if value is None:
                continue
            meta = {c["concept"]: c for c in concepts_meta}.get(concept, {})
            items_to_create.append(FinancialLineItem(
                statement_id=stmt.id,
                concept=concept,
                label=meta.get("label"),
                value=value,
                unit=meta.get("unit", "USD"),
                order=concept_order_map.get(concept),
            ))

        for item in items_to_create:
            self._session.add(item)

        await self._session.flush()
        logger.info("statement_recorded", symbol=symbol, type=statement_type,
                     year=fiscal_year, period=fiscal_period, period_type=period_type)
        return stmt

    async def get_statement(
        self, symbol: str, fiscal_year: int, fiscal_period: int,
        period_type: str, statement_type: str,
    ) -> FinancialStatement | None:
        result = await self._session.execute(
            select(FinancialStatement)
            .where(
                FinancialStatement.symbol == symbol.upper(),
                FinancialStatement.fiscal_year == fiscal_year,
                FinancialStatement.fiscal_period == fiscal_period,
                FinancialStatement.period_type == period_type,
                FinancialStatement.statement_type == statement_type,
            )
            .options(selectinload(FinancialStatement.line_items))
        )
        return result.scalar_one_or_none()

    async def list_statements(
        self, symbol: str, *, statement_type: str | None = None,
        period_type: str | None = None, fiscal_year: int | None = None,
        skip: int = 0, limit: int = 100,
    ) -> tuple[Sequence[FinancialStatement], int]:
        stmt = select(FinancialStatement).where(FinancialStatement.symbol == symbol.upper())
        if statement_type:
            stmt = stmt.where(FinancialStatement.statement_type == statement_type)
        if period_type:
            stmt = stmt.where(FinancialStatement.period_type == period_type)
        if fiscal_year is not None:
            stmt = stmt.where(FinancialStatement.fiscal_year == fiscal_year)

        count_result = await self._session.execute(stmt)
        total = len(count_result.scalars().all())

        stmt = stmt.order_by(
            FinancialStatement.fiscal_year.desc(),
            FinancialStatement.fiscal_period.desc(),
        ).offset(skip).limit(limit)
        result = await self._session.execute(
            stmt.options(selectinload(FinancialStatement.line_items))
        )
        return list(result.scalars().all()), total

    async def get_quarterly(
        self, symbol: str, statement_type: str, fiscal_year: int,
    ) -> list[FinancialStatement]:
        result = await self._session.execute(
            select(FinancialStatement)
            .where(
                FinancialStatement.symbol == symbol.upper(),
                FinancialStatement.statement_type == statement_type,
                FinancialStatement.period_type == "quarterly",
                FinancialStatement.fiscal_year == fiscal_year,
            )
            .order_by(FinancialStatement.fiscal_period.asc())
            .options(selectinload(FinancialStatement.line_items))
        )
        return list(result.scalars().all())

    async def get_annual(
        self, symbol: str, statement_type: str, fiscal_year: int,
    ) -> FinancialStatement | None:
        result = await self._session.execute(
            select(FinancialStatement)
            .where(
                FinancialStatement.symbol == symbol.upper(),
                FinancialStatement.statement_type == statement_type,
                FinancialStatement.period_type == "annual",
                FinancialStatement.fiscal_year == fiscal_year,
            )
            .options(selectinload(FinancialStatement.line_items))
        )
        return result.scalar_one_or_none()

    async def aggregate_annual_from_quarters(
        self, symbol: str, statement_type: str, fiscal_year: int,
        filing_date: date | None = None,
    ) -> FinancialStatement:
        symbol = symbol.upper()
        quarters = await self.get_quarterly(symbol, statement_type, fiscal_year)
        if len(quarters) < 4:
            raise ValueError(f"Need all 4 quarters to aggregate annual for {symbol} FY{fiscal_year}")

        concept_values: dict[str, float] = {}
        for q in quarters:
            for item in q.line_items:
                if item.value is not None:
                    concept_values[item.concept] = concept_values.get(item.concept, 0.0) + item.value

        bs_concepts = {c["concept"] for c in STANDARD_CONCEPTS.get("balance_sheet", [])}
        if statement_type == "balance_sheet":
            q4 = quarters[3]
            concept_values = {}
            for item in q4.line_items:
                if item.value is not None:
                    concept_values[item.concept] = item.value

        if filing_date is None:
            filing_date = max(q.filing_date for q in quarters)

        final_filing_date = date.today() if filing_date is None else filing_date

        return await self.record_statement(
            symbol=symbol, fiscal_year=fiscal_year, fiscal_period=4,
            period_type="annual", statement_type=statement_type,
            filing_date=final_filing_date, line_items=concept_values,
        )

    async def get_metrics(
        self, symbol: str, concepts: list[str],
        period_type: str = "annual", limit: int = 10,
    ) -> list[dict[str, Any]]:
        symbol = symbol.upper()
        stmt_type_order = ["income_statement", "balance_sheet", "cash_flow"]
        results: list[dict[str, Any]] = []

        stmt = (
            select(FinancialStatement)
            .where(
                FinancialStatement.symbol == symbol,
                FinancialStatement.period_type == period_type,
            )
            .order_by(FinancialStatement.fiscal_year.desc())
            .limit(limit)
            .options(selectinload(FinancialStatement.line_items))
        )
        db_results = await self._session.execute(stmt)
        statements: list[FinancialStatement] = list(db_results.scalars().all())

        for stmt in statements:
            entry: dict[str, Any] = {
                "fiscal_year": stmt.fiscal_year,
                "fiscal_period": stmt.fiscal_period,
                "period_type": stmt.period_type,
                "statement_type": stmt.statement_type,
            }
            item_map = {li.concept: li.value for li in stmt.line_items}
            for concept in concepts:
                entry[concept] = item_map.get(concept)
            results.append(entry)

        return results

    async def get_financial_ratios(
        self, symbol: str, fiscal_year: int, period_type: str = "annual",
    ) -> dict[str, float | None]:
        symbol = symbol.upper()

        income = await self.get_statement(symbol, fiscal_year, 4, period_type, "income_statement")
        bs = await self.get_statement(symbol, fiscal_year, 4, period_type, "balance_sheet")
        cf = await self.get_statement(symbol, fiscal_year, 4, period_type, "cash_flow")

        def gv(stmt: FinancialStatement | None, concept: str) -> float | None:
            if stmt is None or not stmt.line_items:
                return None
            item_map = {li.concept: li.value for li in stmt.line_items}
            return item_map.get(concept)

        revenue = gv(income, "revenue")
        net_income = gv(income, "net_income")
        total_assets = gv(bs, "total_assets")
        total_equity = gv(bs, "total_equity")
        total_liabilities = gv(bs, "total_liabilities")
        operating_cf = gv(cf, "operating_cash_flow")
        ebitda_val = gv(income, "ebitda")
        interest = gv(income, "interest_expense")

        ratios: dict[str, float | None] = {}
        ratios["return_on_equity"] = round(net_income / total_equity, 4) if net_income and total_equity else None
        ratios["return_on_assets"] = round(net_income / total_assets, 4) if net_income and total_assets else None
        ratios["debt_to_equity"] = round(total_liabilities / total_equity, 4) if total_liabilities and total_equity else None
        ratios["profit_margin"] = round(net_income / revenue, 4) if net_income and revenue else None
        ratios["asset_turnover"] = round(revenue / total_assets, 4) if revenue and total_assets else None
        ratios["interest_coverage"] = round(ebitda_val / interest, 4) if ebitda_val and interest else None
        ratios["operating_cash_flow_ratio"] = round(operating_cf / total_liabilities, 4) if operating_cf and total_liabilities else None
        return ratios

    async def delete_statement(self, statement_id: int) -> bool:
        return await self._repo.delete(statement_id)
