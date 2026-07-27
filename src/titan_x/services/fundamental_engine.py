import json
import math
from collections.abc import Sequence
from datetime import date
from typing import Any

import structlog
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from titan_x.db.repository import BaseRepository
from titan_x.models.company import Company
from titan_x.models.financial import FinancialStatement
from titan_x.models.fundamental import FundamentalMetric
from titan_x.models.price import DailyPrice

logger = structlog.get_logger(__name__)

METRIC_DEFINITIONS: dict[str, dict[str, Any]] = {
    "PE": {"name": "PE", "category": "valuation", "description": "Price-to-Earnings Ratio (TTM)", "default_params": {}},
    "PB": {"name": "PB", "category": "valuation", "description": "Price-to-Book Ratio", "default_params": {}},
    "EV_EBITDA": {"name": "EV_EBITDA", "category": "valuation", "description": "Enterprise Value / EBITDA", "default_params": {}},
    "EV_REVENUE": {"name": "EV_REVENUE", "category": "valuation", "description": "Enterprise Value / Revenue", "default_params": {}},
    "DIVIDEND_YIELD": {"name": "DIVIDEND_YIELD", "category": "valuation", "description": "Dividend Yield", "default_params": {}},
    "ROE": {"name": "ROE", "category": "profitability", "description": "Return on Equity", "default_params": {}},
    "ROA": {"name": "ROA", "category": "profitability", "description": "Return on Assets", "default_params": {}},
    "ROCE": {"name": "ROCE", "category": "profitability", "description": "Return on Capital Employed", "default_params": {}},
    "GROSS_MARGIN": {"name": "GROSS_MARGIN", "category": "profitability", "description": "Gross Profit Margin", "default_params": {}},
    "OPERATING_MARGIN": {"name": "OPERATING_MARGIN", "category": "profitability", "description": "Operating Profit Margin", "default_params": {}},
    "NET_MARGIN": {"name": "NET_MARGIN", "category": "profitability", "description": "Net Profit Margin", "default_params": {}},
    "DEBT_EQUITY": {"name": "DEBT_EQUITY", "category": "leverage", "description": "Debt-to-Equity Ratio", "default_params": {}},
    "INTEREST_COVERAGE": {"name": "INTEREST_COVERAGE", "category": "leverage", "description": "Interest Coverage Ratio", "default_params": {}},
    "NET_DEBT": {"name": "NET_DEBT", "category": "leverage", "description": "Net Debt", "default_params": {}},
    "CURRENT_RATIO": {"name": "CURRENT_RATIO", "category": "liquidity", "description": "Current Ratio", "default_params": {}},
    "QUICK_RATIO": {"name": "QUICK_RATIO", "category": "liquidity", "description": "Quick Ratio (Acid Test)", "default_params": {}},
    "REVENUE_GROWTH": {"name": "REVENUE_GROWTH", "category": "growth", "description": "Revenue Growth (YoY %)", "default_params": {}},
    "EPS_GROWTH": {"name": "EPS_GROWTH", "category": "growth", "description": "EPS Growth (YoY %)", "default_params": {}},
    "BOOK_VALUE_GROWTH": {"name": "BOOK_VALUE_GROWTH", "category": "growth", "description": "Book Value Growth (YoY %)", "default_params": {}},
    "ASSET_TURNOVER": {"name": "ASSET_TURNOVER", "category": "efficiency", "description": "Asset Turnover Ratio", "default_params": {}},
    "INVENTORY_TURNOVER": {"name": "INVENTORY_TURNOVER", "category": "efficiency", "description": "Inventory Turnover", "default_params": {}},
    "QUALITY_SCORE": {"name": "QUALITY_SCORE", "category": "composite", "description": "Composite Quality Score (0-10)", "default_params": {}},
}


def _gv(stmt: FinancialStatement | None, concept: str) -> float | None:
    if stmt is None or not stmt.line_items:
        return None
    item_map = {li.concept: li.value for li in stmt.line_items}
    return item_map.get(concept)


def _safe_div(num: float | None, den: float | None) -> float | None:
    if num is not None and den is not None and den != 0:
        return num / den
    return None


def _safe_pct(num: float | None, den: float | None) -> float | None:
    r = _safe_div(num, den)
    return round(r * 100, 4) if r is not None else None


def _compute_enterprise_value(
    market_cap: float | None,
    short_term_debt: float | None,
    long_term_debt: float | None,
    cash: float | None,
) -> float | None:
    if market_cap is None:
        return None
    total_debt = (short_term_debt or 0.0) + (long_term_debt or 0.0)
    cash_val = cash or 0.0
    return market_cap + total_debt - cash_val


class FundamentalEngine:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._metric_repo = BaseRepository(session, FundamentalMetric)

    def list_metrics(self) -> list[dict[str, Any]]:
        return list(METRIC_DEFINITIONS.values())

    async def _get_statement(
        self, symbol: str, fiscal_year: int, fiscal_period: int, period_type: str, statement_type: str,
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

    async def _get_latest_price(self, symbol: str) -> DailyPrice | None:
        result = await self._session.execute(
            select(DailyPrice)
            .where(DailyPrice.symbol == symbol.upper())
            .order_by(DailyPrice.trade_date.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _get_company(self, symbol: str) -> Company | None:
        result = await self._session.execute(
            select(Company).where(Company.symbol == symbol.upper())
        )
        return result.scalar_one_or_none()

    async def _store(
        self, symbol: str, fiscal_year: int, fiscal_period: int,
        period_type: str, metric_name: str, value: float | None,
        meta: dict[str, Any] | None = None,
    ) -> None:
        if value is None:
            return
        result = await self._session.execute(
            select(FundamentalMetric).where(
                FundamentalMetric.symbol == symbol.upper(),
                FundamentalMetric.fiscal_year == fiscal_year,
                FundamentalMetric.fiscal_period == fiscal_period,
                FundamentalMetric.period_type == period_type,
                FundamentalMetric.metric_name == metric_name,
            )
        )
        if result.scalar_one_or_none() is not None:
            return
        await self._metric_repo.create(
            symbol=symbol.upper(), fiscal_year=fiscal_year,
            fiscal_period=fiscal_period, period_type=period_type,
            metric_name=metric_name, value=value,
            metadata_json=json.dumps(meta) if meta else None,
        )

    async def compute_all(self, symbol: str, fiscal_year: int, period_type: str = "annual") -> dict[str, Any]:
        symbol = symbol.upper()
        fp = 4 if period_type == "annual" else 1

        inc = await self._get_statement(symbol, fiscal_year, fp, period_type, "income_statement")
        bs = await self._get_statement(symbol, fiscal_year, fp, period_type, "balance_sheet")
        cf = await self._get_statement(symbol, fiscal_year, fp, period_type, "cash_flow")
        inc_prev = await self._get_statement(symbol, fiscal_year - 1, fp, period_type, "income_statement")
        bs_prev = await self._get_statement(symbol, fiscal_year - 1, fp, period_type, "balance_sheet")

        price = await self._get_latest_price(symbol)
        company = await self._get_company(symbol)

        close = price.close if price else None
        shares = _gv(inc, "shares_outstanding")
        market_cap = (close * shares) if close and shares else company.market_cap if company else None

        revenue = _gv(inc, "revenue")
        cost_revenue = _gv(inc, "cost_of_revenue")
        gross_profit = _gv(inc, "gross_profit")
        op_income = _gv(inc, "operating_income")
        net_income = _gv(inc, "net_income")
        ebitda_val = _gv(inc, "ebitda")
        eps = _gv(inc, "eps_basic")
        interest = _gv(inc, "interest_expense")
        dividends = _gv(cf, "dividends_paid") or 0.0

        total_assets = _gv(bs, "total_assets")
        total_liabilities = _gv(bs, "total_liabilities")
        total_equity = _gv(bs, "total_equity")
        current_assets = _gv(bs, "current_assets")
        current_liab = _gv(bs, "current_liabilities")
        cash = _gv(bs, "cash_and_equivalents")
        short_debt = _gv(bs, "short_term_debt")
        long_debt = _gv(bs, "long_term_debt")
        inventory = _gv(bs, "inventory")
        accounts_receivable = _gv(bs, "accounts_receivable")

        revenue_prev = _gv(inc_prev, "revenue")
        eps_prev = _gv(inc_prev, "eps_basic")
        equity_prev = _gv(bs_prev, "total_equity")

        results: dict[str, Any] = {}
        meta: dict[str, Any] = {}

        pe = _safe_div(close, eps) if close and eps else _safe_div(market_cap, net_income) if market_cap and net_income else None
        if pe is not None:
            results["PE"] = round(pe, 4)
            meta["PE"] = {"close": close, "eps": eps}

        book_value = _safe_div(total_equity, shares) if shares else None
        pb = _safe_div(close, book_value) if close and book_value else None
        if pb is not None:
            results["PB"] = round(pb, 4)
            meta["PB"] = {"close": close, "book_value_per_share": book_value}

        ev = _compute_enterprise_value(market_cap, short_debt, long_debt, cash)
        ev_ebitda = _safe_div(ev, ebitda_val)
        if ev_ebitda is not None:
            results["EV_EBITDA"] = round(ev_ebitda, 4)
            meta["EV_EBITDA"] = {"ev": ev, "ebitda": ebitda_val}

        ev_revenue = _safe_div(ev, revenue)
        if ev_revenue is not None:
            results["EV_REVENUE"] = round(ev_revenue, 4)

        div_yield = _safe_div(dividends * -1, market_cap) if market_cap else None
        if div_yield is not None:
            results["DIVIDEND_YIELD"] = round(div_yield * 100, 4)

        roe = _safe_pct(net_income, total_equity)
        if roe is not None:
            results["ROE"] = roe
            meta["ROE"] = {"net_income": net_income, "equity": total_equity}

        roa = _safe_pct(net_income, total_assets)
        if roa is not None:
            results["ROA"] = roa

        capital_employed = (total_assets - current_liab) if total_assets is not None and current_liab is not None else None
        roce = _safe_pct(op_income or ebitda_val, capital_employed)
        if roce is not None:
            results["ROCE"] = roce
            meta["ROCE"] = {"ebit": op_income or ebitda_val, "capital_employed": capital_employed}

        gross_margin = _safe_pct(gross_profit or _safe_sub(revenue, cost_revenue), revenue)
        if gross_margin is not None:
            results["GROSS_MARGIN"] = gross_margin

        op_margin = _safe_pct(op_income, revenue)
        if op_margin is not None:
            results["OPERATING_MARGIN"] = op_margin

        net_margin = _safe_pct(net_income, revenue)
        if net_margin is not None:
            results["NET_MARGIN"] = net_margin

        de = _safe_div(total_liabilities, total_equity)
        if de is not None:
            results["DEBT_EQUITY"] = round(de, 4)
            meta["DEBT_EQUITY"] = {"total_liabilities": total_liabilities, "equity": total_equity}

        ic = _safe_div(ebitda_val or op_income, interest)
        if ic is not None:
            results["INTEREST_COVERAGE"] = round(ic, 4)
            meta["INTEREST_COVERAGE"] = {"ebitda": ebitda_val or op_income, "interest": interest}

        net_debt = ((short_debt or 0.0) + (long_debt or 0.0) - (cash or 0.0)) if any(x is not None for x in [short_debt, long_debt, cash]) else None
        if net_debt is not None:
            results["NET_DEBT"] = round(net_debt, 2)

        cr = _safe_div(current_assets, current_liab)
        if cr is not None:
            results["CURRENT_RATIO"] = round(cr, 4)

        quick = _safe_div((current_assets or 0.0) - (inventory or 0.0), current_liab) if current_assets is not None and current_liab is not None else None
        if quick is not None:
            results["QUICK_RATIO"] = round(quick, 4)

        rev_growth = _safe_pct(_safe_sub(revenue, revenue_prev), revenue_prev)
        if rev_growth is not None:
            results["REVENUE_GROWTH"] = rev_growth
            meta["REVENUE_GROWTH"] = {"current": revenue, "previous": revenue_prev}

        eps_growth = _safe_pct(_safe_sub(eps, eps_prev), eps_prev)
        if eps_growth is not None:
            results["EPS_GROWTH"] = eps_growth
            meta["EPS_GROWTH"] = {"current": eps, "previous": eps_prev}

        bv_growth = _safe_pct(_safe_sub(total_equity, equity_prev), equity_prev)
        if bv_growth is not None:
            results["BOOK_VALUE_GROWTH"] = bv_growth

        asset_turnover = _safe_div(revenue, total_assets)
        if asset_turnover is not None:
            results["ASSET_TURNOVER"] = round(asset_turnover, 4)

        inv_turnover = _safe_div(cost_revenue, inventory)
        if inv_turnover is not None:
            results["INVENTORY_TURNOVER"] = round(inv_turnover, 4)

        quality_result = self._compute_quality_score(net_income, total_equity, total_assets,
                                                      total_liabilities, total_equity, operating_cf=_gv(cf, "operating_cash_flow"),
                                                      interest=interest, ebitda=ebitda_val or op_income,
                                                      rev_growth_pct=results.get("REVENUE_GROWTH"),
                                                      roe_val=results.get("ROE"))
        if quality_result is not None:
            results["QUALITY_SCORE"] = quality_result["score"]
            meta["QUALITY_SCORE"] = quality_result

        for metric_name in results:
            value = results[metric_name]
            await self._store(symbol, fiscal_year, fp, period_type, metric_name, value, meta.get(metric_name))

        await self._session.flush()
        logger.info("fundamentals_computed", symbol=symbol, year=fiscal_year, metrics=len(results))
        return results

    async def get_stored(
        self, symbol: str, *, metric_name: str | None = None,
        fiscal_year: int | None = None, period_type: str | None = None,
        skip: int = 0, limit: int = 100,
    ) -> tuple[Sequence[FundamentalMetric], int]:
        stmt = select(FundamentalMetric).where(FundamentalMetric.symbol == symbol.upper())
        if metric_name:
            stmt = stmt.where(FundamentalMetric.metric_name == metric_name.upper())
        if fiscal_year is not None:
            stmt = stmt.where(FundamentalMetric.fiscal_year == fiscal_year)
        if period_type:
            stmt = stmt.where(FundamentalMetric.period_type == period_type)

        count_result = await self._session.execute(stmt)
        total = len(count_result.scalars().all())
        stmt = stmt.order_by(FundamentalMetric.fiscal_year.desc(), FundamentalMetric.metric_name.asc()).offset(skip).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all()), total

    async def screen(self, metric_name: str, min_val: float | None = None, max_val: float | None = None,
                     fiscal_year: int | None = None, period_type: str = "annual",
                     limit: int = 50) -> list[dict[str, Any]]:
        stmt = select(FundamentalMetric).where(
            FundamentalMetric.metric_name == metric_name.upper(),
            FundamentalMetric.period_type == period_type,
        )
        if min_val is not None:
            stmt = stmt.where(FundamentalMetric.value >= min_val)
        if max_val is not None:
            stmt = stmt.where(FundamentalMetric.value <= max_val)
        if fiscal_year is not None:
            stmt = stmt.where(FundamentalMetric.fiscal_year == fiscal_year)
        stmt = stmt.order_by(FundamentalMetric.value.desc().nullslast()).limit(limit)
        result = await self._session.execute(stmt)
        rows = result.scalars().all()
        return [{"symbol": r.symbol, "value": r.value, "fiscal_year": r.fiscal_year, "metric": r.metric_name} for r in rows]

    async def delete_stored(self, metric_id: int) -> bool:
        return await self._metric_repo.delete(metric_id)

    def _compute_quality_score(
        self, net_income: float | None, equity: float | None,
        total_assets: float | None, total_liabilities: float | None,
        total_equity: float | None, operating_cf: float | None,
        interest: float | None, ebitda: float | None,
        rev_growth_pct: float | None, roe_val: float | None,
    ) -> dict[str, Any] | None:
        score = 0
        breakdown: dict[str, int] = {}
        max_score = 10

        roe = roe_val or _safe_pct(net_income, equity)
        if roe is not None and roe > 10:
            score += 2
            breakdown["roe_positive"] = 2
        elif roe is not None and roe > 0:
            score += 1
            breakdown["roe_positive"] = 1
        else:
            breakdown["roe_positive"] = 0

        roa = _safe_pct(net_income, total_assets)
        if roa is not None and roa > 5:
            score += 1
            breakdown["roa_positive"] = 1
        elif roa is not None and roa > 0:
            score += 0
            breakdown["roa_positive"] = 0
        else:
            breakdown["roa_positive"] = 0

        ocf_pos = operating_cf is not None and operating_cf > 0
        if ocf_pos:
            score += 1
            breakdown["ocf_positive"] = 1
        else:
            breakdown["ocf_positive"] = 0

        de = _safe_div(total_liabilities, total_equity)
        if de is not None and de < 1.0:
            score += 2
            breakdown["low_leverage"] = 2
        elif de is not None and de < 2.0:
            score += 1
            breakdown["low_leverage"] = 1
        else:
            breakdown["low_leverage"] = 0

        ic = _safe_div(ebitda, interest)
        if ic is not None and ic > 5:
            score += 1
            breakdown["interest_coverage"] = 1
        else:
            breakdown["interest_coverage"] = 0

        if rev_growth_pct is not None and rev_growth_pct > 10:
            score += 2
            breakdown["revenue_growth"] = 2
        elif rev_growth_pct is not None and rev_growth_pct > 0:
            score += 1
            breakdown["revenue_growth"] = 1
        else:
            breakdown["revenue_growth"] = 0

        if roe is not None and roe > 15:
            score += 1
            breakdown["efficiency"] = 1
        else:
            breakdown["efficiency"] = 0

        return {"score": score, "max_score": max_score, "breakdown": breakdown}


def _safe_sub(a: float | None, b: float | None) -> float | None:
    if a is not None and b is not None:
        return a - b
    return None
