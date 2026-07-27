from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.models.financial_analysis import AnnualResult, FinancialAnalysis, Guidance, QuarterlyResult


class FinancialAnalysisService:
    def __init__(self, session: AsyncSession):
        self.session = session

    # --- QUARTERLY RESULTS ---

    async def record_quarterly(
        self, symbol: str, fiscal_year: int, quarter: int,
        revenue: float | None = None, cost_of_revenue: float | None = None,
        gross_profit: float | None = None, operating_expenses: float | None = None,
        operating_income: float | None = None, net_income: float | None = None,
        eps_basic: float | None = None, eps_diluted: float | None = None,
        filing_date: date | None = None, source: str | None = None,
    ) -> QuarterlyResult:
        gp = gross_profit if gross_profit is not None else (revenue - cost_of_revenue if revenue and cost_of_revenue else None)
        gross_margin = round(gp / revenue, 4) if gp and revenue else None
        operating_margin = round(operating_income / revenue, 4) if operating_income and revenue else None
        net_margin = round(net_income / revenue, 4) if net_income and revenue else None

        prev_q = await self._get_prev_quarter(symbol, fiscal_year, quarter)
        prev_4q = await self._get_same_quarter_last_year(symbol, fiscal_year, quarter)
        prev_eps = prev_q.eps_diluted if prev_q else None
        prev_rev = prev_q.revenue if prev_q else None
        yoy_eps = prev_4q.eps_diluted if prev_4q else None
        yoy_rev = prev_4q.revenue if prev_4q else None

        revenue_qoq = round((revenue - prev_rev) / prev_rev, 4) if revenue and prev_rev else None
        revenue_yoy = round((revenue - yoy_rev) / yoy_rev, 4) if revenue and yoy_rev else None
        eps_qoq = round((eps_diluted - prev_eps) / prev_eps, 4) if eps_diluted and prev_eps else None
        eps_yoy = round((eps_diluted - yoy_eps) / yoy_eps, 4) if eps_diluted and yoy_eps else None

        qr = QuarterlyResult(
            symbol=symbol.upper(), fiscal_year=fiscal_year, quarter=quarter,
            revenue=revenue, cost_of_revenue=cost_of_revenue,
            gross_profit=gp, operating_expenses=operating_expenses,
            operating_income=operating_income, net_income=net_income,
            eps_basic=eps_basic, eps_diluted=eps_diluted,
            gross_margin=gross_margin, operating_margin=operating_margin, net_margin=net_margin,
            revenue_qoq_growth=revenue_qoq, revenue_yoy_growth=revenue_yoy,
            eps_qoq_growth=eps_qoq, eps_yoy_growth=eps_yoy,
            filing_date=filing_date, source=source,
        )
        self.session.add(qr)
        await self.session.flush()
        await self.session.refresh(qr)
        return qr

    async def _get_prev_quarter(self, symbol: str, fiscal_year: int, quarter: int) -> QuarterlyResult | None:
        if quarter > 1:
            result = await self.session.execute(
                select(QuarterlyResult).where(
                    QuarterlyResult.symbol == symbol.upper(),
                    QuarterlyResult.fiscal_year == fiscal_year,
                    QuarterlyResult.quarter == quarter - 1,
                )
            )
        else:
            result = await self.session.execute(
                select(QuarterlyResult).where(
                    QuarterlyResult.symbol == symbol.upper(),
                    QuarterlyResult.fiscal_year == fiscal_year - 1,
                    QuarterlyResult.quarter == 4,
                )
            )
        return result.scalar_one_or_none()

    async def _get_same_quarter_last_year(self, symbol: str, fiscal_year: int, quarter: int) -> QuarterlyResult | None:
        result = await self.session.execute(
            select(QuarterlyResult).where(
                QuarterlyResult.symbol == symbol.upper(),
                QuarterlyResult.fiscal_year == fiscal_year - 1,
                QuarterlyResult.quarter == quarter,
            )
        )
        return result.scalar_one_or_none()

    async def get_quarterly(self, symbol: str, limit: int = 8) -> list[QuarterlyResult]:
        result = await self.session.execute(
            select(QuarterlyResult).where(QuarterlyResult.symbol == symbol.upper())
            .order_by(QuarterlyResult.fiscal_year.desc(), QuarterlyResult.quarter.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def delete_quarterly(self, result_id: int) -> bool:
        obj = await self.session.get(QuarterlyResult, result_id)
        if obj is None:
            return False
        await self.session.delete(obj)
        await self.session.flush()
        return True

    # --- ANNUAL RESULTS ---

    async def record_annual(
        self, symbol: str, fiscal_year: int,
        revenue: float | None = None, cost_of_revenue: float | None = None,
        gross_profit: float | None = None, operating_expenses: float | None = None,
        operating_income: float | None = None, net_income: float | None = None,
        eps_basic: float | None = None, eps_diluted: float | None = None,
        filing_date: date | None = None, source: str | None = None,
    ) -> AnnualResult:
        gp = gross_profit if gross_profit is not None else (revenue - cost_of_revenue if revenue and cost_of_revenue else None)
        gross_margin = round(gp / revenue, 4) if gp and revenue else None
        operating_margin = round(operating_income / revenue, 4) if operating_income and revenue else None
        net_margin = round(net_income / revenue, 4) if net_income and revenue else None

        prev = await self._get_annual(symbol, fiscal_year - 1)
        rev_yoy = round((revenue - prev.revenue) / prev.revenue, 4) if revenue and prev and prev.revenue else None
        eps_yoy = round((eps_diluted - prev.eps_diluted) / prev.eps_diluted, 4) if eps_diluted and prev and prev.eps_diluted else None

        ar = AnnualResult(
            symbol=symbol.upper(), fiscal_year=fiscal_year,
            revenue=revenue, cost_of_revenue=cost_of_revenue,
            gross_profit=gp, operating_expenses=operating_expenses,
            operating_income=operating_income, net_income=net_income,
            eps_basic=eps_basic, eps_diluted=eps_diluted,
            gross_margin=gross_margin, operating_margin=operating_margin, net_margin=net_margin,
            revenue_yoy_growth=rev_yoy, eps_yoy_growth=eps_yoy,
            filing_date=filing_date, source=source,
        )
        self.session.add(ar)
        await self.session.flush()
        await self.session.refresh(ar)
        return ar

    async def _get_annual(self, symbol: str, fiscal_year: int) -> AnnualResult | None:
        result = await self.session.execute(
            select(AnnualResult).where(
                AnnualResult.symbol == symbol.upper(),
                AnnualResult.fiscal_year == fiscal_year,
            )
        )
        return result.scalar_one_or_none()

    async def get_annual(self, symbol: str, limit: int = 5) -> list[AnnualResult]:
        result = await self.session.execute(
            select(AnnualResult).where(AnnualResult.symbol == symbol.upper())
            .order_by(AnnualResult.fiscal_year.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def delete_annual(self, result_id: int) -> bool:
        obj = await self.session.get(AnnualResult, result_id)
        if obj is None:
            return False
        await self.session.delete(obj)
        await self.session.flush()
        return True

    # --- GUIDANCE ---

    async def record_guidance(
        self, symbol: str, fiscal_year: int, period_type: str,
        revenue_low: float | None = None, revenue_high: float | None = None,
        eps_low: float | None = None, eps_high: float | None = None,
        operating_margin_low: float | None = None, operating_margin_high: float | None = None,
        guidance_notes: str | None = None, issued_date: date | None = None,
    ) -> Guidance:
        g = Guidance(
            symbol=symbol.upper(), fiscal_year=fiscal_year, period_type=period_type,
            revenue_low=revenue_low, revenue_high=revenue_high,
            eps_low=eps_low, eps_high=eps_high,
            operating_margin_low=operating_margin_low, operating_margin_high=operating_margin_high,
            guidance_notes=guidance_notes, issued_date=issued_date,
        )
        self.session.add(g)
        await self.session.flush()
        await self.session.refresh(g)
        return g

    async def get_guidance(self, symbol: str, status: str | None = "active") -> list[Guidance]:
        q = select(Guidance).where(Guidance.symbol == symbol.upper())
        if status:
            q = q.where(Guidance.status == status)
        q = q.order_by(Guidance.fiscal_year.desc())
        result = await self.session.execute(q)
        return list(result.scalars().all())

    async def delete_guidance(self, guidance_id: int) -> bool:
        obj = await self.session.get(Guidance, guidance_id)
        if obj is None:
            return False
        await self.session.delete(obj)
        await self.session.flush()
        return True

    # --- ANALYSIS ---

    async def analyze(self, symbol: str) -> FinancialAnalysis:
        symbol = symbol.upper()
        quarters = await self.get_quarterly(symbol, limit=4)
        annuals = await self.get_annual(symbol, limit=5)
        guidances = await self.get_guidance(symbol)

        rev_growth_score = self._score_revenue_growth(quarters, annuals)
        margin_score = self._score_margin_trends(quarters, annuals)
        eps_growth_score = self._score_eps_growth(quarters, annuals)
        guidance_score = self._score_guidance(guidances, quarters, annuals)

        weights = {"revenue": 0.30, "margin": 0.25, "eps": 0.30, "guidance": 0.15}
        overall = (
            rev_growth_score * weights["revenue"]
            + margin_score * weights["margin"]
            + eps_growth_score * weights["eps"]
            + guidance_score * weights["guidance"]
        )

        if overall >= 75:
            signal = "strong_buy"
        elif overall >= 55:
            signal = "buy"
        elif overall >= 40:
            signal = "hold"
        elif overall >= 25:
            signal = "sell"
        else:
            signal = "strong_sell"

        recent_q = quarters[0] if quarters else None
        recent_a = annuals[0] if annuals else None
        rev_str = f"${recent_q.revenue / 1e9:.2f}B" if recent_q and recent_q.revenue else "N/A"
        eps_str = f"${recent_q.eps_diluted:.2f}" if recent_q and recent_q.eps_diluted else "N/A"
        rev_gr = f"{recent_q.revenue_yoy_growth * 100:.1f}%" if recent_q and recent_q.revenue_yoy_growth else "N/A"
        eps_gr = f"{recent_q.eps_yoy_growth * 100:.1f}%" if recent_q and recent_q.eps_yoy_growth else "N/A"

        summary = (
            f"{symbol}: Overall Score {overall:.1f}/100 ({signal.upper()}). "
            f"Latest Quarter Rev {rev_str} (YoY: {rev_gr}), EPS {eps_str} (YoY: {eps_gr}). "
            f"Revenue Strength: {rev_growth_score:.0f}/100. "
            f"Margin Health: {margin_score:.0f}/100. "
            f"EPS Momentum: {eps_growth_score:.0f}/100. "
            f"Guidance Confidence: {guidance_score:.0f}/100."
        )

        confidence = min(95.0, 50.0 + rev_growth_score * 0.15 + margin_score * 0.1 + eps_growth_score * 0.15 + guidance_score * 0.1)

        fa = FinancialAnalysis(
            symbol=symbol,
            analysis_date=datetime.now(timezone.utc),
            revenue_growth_score=round(rev_growth_score, 2),
            margin_score=round(margin_score, 2),
            eps_growth_score=round(eps_growth_score, 2),
            guidance_score=round(guidance_score, 2),
            overall_score=round(overall, 2),
            signal=signal,
            confidence=round(confidence, 2),
            summary_text=summary,
        )
        self.session.add(fa)
        await self.session.flush()
        await self.session.refresh(fa)
        return fa

    def _score_revenue_growth(self, quarters: list[QuarterlyResult], annuals: list[AnnualResult]) -> float:
        score = 50.0
        if annuals:
            yoy_values = [a.revenue_yoy_growth for a in annuals if a.revenue_yoy_growth is not None]
            if yoy_values:
                avg_yoy = sum(yoy_values) / len(yoy_values)
                score += avg_yoy * 200
        if quarters:
            qoq_values = [q.revenue_qoq_growth for q in quarters if q.revenue_qoq_growth is not None]
            if qoq_values:
                avg_qoq = sum(qoq_values) / len(qoq_values)
                score += avg_qoq * 100
        return max(0, min(100, score))

    def _score_margin_trends(self, quarters: list[QuarterlyResult], annuals: list[AnnualResult]) -> float:
        score = 50.0
        margins = []
        if annuals:
            margins.extend(a.operating_margin for a in annuals if a.operating_margin is not None)
        if quarters:
            margins.extend(q.operating_margin for q in quarters if q.operating_margin is not None)
        if margins:
            avg_margin = sum(margins) / len(margins)
            score += avg_margin * 200
            if len(margins) >= 2:
                trend = margins[0] - margins[-1]
                score += trend * 150
        return max(0, min(100, score))

    def _score_eps_growth(self, quarters: list[QuarterlyResult], annuals: list[AnnualResult]) -> float:
        score = 50.0
        if annuals:
            yoy = [a.eps_yoy_growth for a in annuals if a.eps_yoy_growth is not None]
            if yoy:
                avg_yoy = sum(yoy) / len(yoy)
                score += avg_yoy * 150
        if quarters:
            qoq = [q.eps_qoq_growth for q in quarters if q.eps_qoq_growth is not None]
            if qoq:
                avg_qoq = sum(qoq) / len(qoq)
                score += avg_qoq * 100
        return max(0, min(100, score))

    def _score_guidance(self, guidances: list[Guidance], quarters: list[QuarterlyResult], annuals: list[AnnualResult]) -> float:
        if not guidances:
            return 50.0
        score = 50.0
        for g in guidances:
            if g.revenue_low and g.revenue_high:
                guidance_mid = (g.revenue_low + g.revenue_high) / 2
                actual = quarters[0].revenue if quarters else None
                if actual and guidance_mid:
                    beat = (actual - guidance_mid) / guidance_mid
                    score += beat * 100
        return max(0, min(100, score))

    async def get_analysis(self, symbol: str) -> FinancialAnalysis | None:
        result = await self.session.execute(
            select(FinancialAnalysis).where(FinancialAnalysis.symbol == symbol.upper())
            .order_by(FinancialAnalysis.analysis_date.desc()).limit(1)
        )
        return result.scalar_one_or_none()
