import json
from collections.abc import Sequence
from datetime import date, timedelta
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.db.repository import BaseRepository
from titan_x.models.institutional_holdings import (
    DIIHolding,
    ETFHolding,
    FIIHolding,
    InstitutionalAnalysis,
    MutualFundHolding,
)

logger = structlog.get_logger(__name__)

ANALYSIS_LOOKBACK_QUARTERS = 4


class InstitutionalAnalysisService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._fii_repo = BaseRepository(session, FIIHolding)
        self._dii_repo = BaseRepository(session, DIIHolding)
        self._mf_repo = BaseRepository(session, MutualFundHolding)
        self._etf_repo = BaseRepository(session, ETFHolding)
        self._analysis_repo = BaseRepository(session, InstitutionalAnalysis)

    # ------------------------------------------------------------------
    # CRUD: FII Holdings
    # ------------------------------------------------------------------

    async def create_fii_holding(self, **kwargs: Any) -> FIIHolding:
        return await self._fii_repo.create(**kwargs)

    async def get_fii_holding(self, holding_id: int) -> FIIHolding | None:
        return await self._fii_repo.get(holding_id)

    async def list_fii_holdings(
        self, company_id: int | None = None, fii_name: str | None = None,
        year: int | None = None, quarter: int | None = None,
        skip: int = 0, limit: int = 100,
    ) -> tuple[Sequence[FIIHolding], int]:
        query = select(FIIHolding)
        cq = select(func.count()).select_from(FIIHolding)
        if company_id is not None:
            query = query.where(FIIHolding.company_id == company_id)
            cq = cq.where(FIIHolding.company_id == company_id)
        if fii_name is not None:
            query = query.where(FIIHolding.fii_name.ilike(f"%{fii_name}%"))
            cq = cq.where(FIIHolding.fii_name.ilike(f"%{fii_name}%"))
        if year is not None:
            query = query.where(FIIHolding.year == year)
            cq = cq.where(FIIHolding.year == year)
        if quarter is not None:
            query = query.where(FIIHolding.quarter == quarter)
            cq = cq.where(FIIHolding.quarter == quarter)
        total = (await self._session.execute(cq)).scalar() or 0
        query = query.order_by(FIIHolding.year.desc(), FIIHolding.quarter.desc()).offset(skip).limit(limit)
        rows = (await self._session.execute(query)).scalars().all()
        return rows, total

    async def update_fii_holding(self, holding_id: int, **kwargs: Any) -> FIIHolding | None:
        return await self._fii_repo.update(holding_id, **kwargs)

    async def delete_fii_holding(self, holding_id: int) -> bool:
        return await self._fii_repo.delete(holding_id)

    # ------------------------------------------------------------------
    # CRUD: DII Holdings
    # ------------------------------------------------------------------

    async def create_dii_holding(self, **kwargs: Any) -> DIIHolding:
        return await self._dii_repo.create(**kwargs)

    async def get_dii_holding(self, holding_id: int) -> DIIHolding | None:
        return await self._dii_repo.get(holding_id)

    async def list_dii_holdings(
        self, company_id: int | None = None, dii_name: str | None = None,
        year: int | None = None, quarter: int | None = None,
        skip: int = 0, limit: int = 100,
    ) -> tuple[Sequence[DIIHolding], int]:
        query = select(DIIHolding)
        cq = select(func.count()).select_from(DIIHolding)
        if company_id is not None:
            query = query.where(DIIHolding.company_id == company_id)
            cq = cq.where(DIIHolding.company_id == company_id)
        if dii_name is not None:
            query = query.where(DIIHolding.dii_name.ilike(f"%{dii_name}%"))
            cq = cq.where(DIIHolding.dii_name.ilike(f"%{dii_name}%"))
        if year is not None:
            query = query.where(DIIHolding.year == year)
            cq = cq.where(DIIHolding.year == year)
        if quarter is not None:
            query = query.where(DIIHolding.quarter == quarter)
            cq = cq.where(DIIHolding.quarter == quarter)
        total = (await self._session.execute(cq)).scalar() or 0
        query = query.order_by(DIIHolding.year.desc(), DIIHolding.quarter.desc()).offset(skip).limit(limit)
        rows = (await self._session.execute(query)).scalars().all()
        return rows, total

    async def update_dii_holding(self, holding_id: int, **kwargs: Any) -> DIIHolding | None:
        return await self._dii_repo.update(holding_id, **kwargs)

    async def delete_dii_holding(self, holding_id: int) -> bool:
        return await self._dii_repo.delete(holding_id)

    # ------------------------------------------------------------------
    # CRUD: Mutual Fund Holdings
    # ------------------------------------------------------------------

    async def create_mf_holding(self, **kwargs: Any) -> MutualFundHolding:
        return await self._mf_repo.create(**kwargs)

    async def get_mf_holding(self, holding_id: int) -> MutualFundHolding | None:
        return await self._mf_repo.get(holding_id)

    async def list_mf_holdings(
        self, company_id: int | None = None, scheme_name: str | None = None,
        amc: str | None = None, year: int | None = None, quarter: int | None = None,
        skip: int = 0, limit: int = 100,
    ) -> tuple[Sequence[MutualFundHolding], int]:
        query = select(MutualFundHolding)
        cq = select(func.count()).select_from(MutualFundHolding)
        if company_id is not None:
            query = query.where(MutualFundHolding.company_id == company_id)
            cq = cq.where(MutualFundHolding.company_id == company_id)
        if scheme_name is not None:
            query = query.where(MutualFundHolding.scheme_name.ilike(f"%{scheme_name}%"))
            cq = cq.where(MutualFundHolding.scheme_name.ilike(f"%{scheme_name}%"))
        if amc is not None:
            query = query.where(MutualFundHolding.amc == amc)
            cq = cq.where(MutualFundHolding.amc == amc)
        if year is not None:
            query = query.where(MutualFundHolding.year == year)
            cq = cq.where(MutualFundHolding.year == year)
        if quarter is not None:
            query = query.where(MutualFundHolding.quarter == quarter)
            cq = cq.where(MutualFundHolding.quarter == quarter)
        total = (await self._session.execute(cq)).scalar() or 0
        query = query.order_by(MutualFundHolding.year.desc(), MutualFundHolding.quarter.desc()).offset(skip).limit(limit)
        rows = (await self._session.execute(query)).scalars().all()
        return rows, total

    async def update_mf_holding(self, holding_id: int, **kwargs: Any) -> MutualFundHolding | None:
        return await self._mf_repo.update(holding_id, **kwargs)

    async def delete_mf_holding(self, holding_id: int) -> bool:
        return await self._mf_repo.delete(holding_id)

    # ------------------------------------------------------------------
    # CRUD: ETF Holdings
    # ------------------------------------------------------------------

    async def create_etf_holding(self, **kwargs: Any) -> ETFHolding:
        return await self._etf_repo.create(**kwargs)

    async def get_etf_holding(self, holding_id: int) -> ETFHolding | None:
        return await self._etf_repo.get(holding_id)

    async def list_etf_holdings(
        self, company_id: int | None = None, etf_name: str | None = None,
        year: int | None = None, quarter: int | None = None,
        skip: int = 0, limit: int = 100,
    ) -> tuple[Sequence[ETFHolding], int]:
        query = select(ETFHolding)
        cq = select(func.count()).select_from(ETFHolding)
        if company_id is not None:
            query = query.where(ETFHolding.company_id == company_id)
            cq = cq.where(ETFHolding.company_id == company_id)
        if etf_name is not None:
            query = query.where(ETFHolding.etf_name.ilike(f"%{etf_name}%"))
            cq = cq.where(ETFHolding.etf_name.ilike(f"%{etf_name}%"))
        if year is not None:
            query = query.where(ETFHolding.year == year)
            cq = cq.where(ETFHolding.year == year)
        if quarter is not None:
            query = query.where(ETFHolding.quarter == quarter)
            cq = cq.where(ETFHolding.quarter == quarter)
        total = (await self._session.execute(cq)).scalar() or 0
        query = query.order_by(ETFHolding.year.desc(), ETFHolding.quarter.desc()).offset(skip).limit(limit)
        rows = (await self._session.execute(query)).scalars().all()
        return rows, total

    async def update_etf_holding(self, holding_id: int, **kwargs: Any) -> ETFHolding | None:
        return await self._etf_repo.update(holding_id, **kwargs)

    async def delete_etf_holding(self, holding_id: int) -> bool:
        return await self._etf_repo.delete(holding_id)

    # ------------------------------------------------------------------
    # AI: FII Scoring
    # ------------------------------------------------------------------

    async def analyze_fii(self, company_id: int) -> dict[str, Any]:
        result = await self._session.execute(
            select(FIIHolding)
            .where(FIIHolding.company_id == company_id)
            .order_by(FIIHolding.year.desc(), FIIHolding.quarter.desc())
        )
        rows = result.scalars().all()
        if not rows:
            return {"fii_score": 50.0, "total_fiis": 0, "insights": ["No FII holdings data available"]}

        quarter_groups: dict[tuple[int, int], list[FIIHolding]] = {}
        for r in rows:
            quarter_groups.setdefault((r.year, r.quarter), []).append(r)

        sorted_quarters = sorted(quarter_groups.keys(), reverse=True)
        latest_q = sorted_quarters[0] if sorted_quarters else None
        prev_q = sorted_quarters[1] if len(sorted_quarters) > 1 else None

        latest = quarter_groups.get(latest_q, [])
        total_pct = sum(r.percentage for r in latest)
        fii_count = len(latest)

        if prev_q:
            prev = quarter_groups.get(prev_q, [])
            prev_pct = sum(r.percentage for r in prev)
            pct_change = total_pct - prev_pct
        else:
            pct_change = 0.0

        top_fiis = sorted(latest, key=lambda r: r.percentage, reverse=True)[:5]
        gaining = sum(1 for r in latest if r.change_percentage is not None and r.change_percentage > 0)
        losing = sum(1 for r in latest if r.change_percentage is not None and r.change_percentage < 0)

        score = 50.0
        insights = []
        if pct_change > 0:
            score += min(20, pct_change * 4)
            insights.append(f"FII holdings increased by {pct_change:+.2f}% over last quarter")
        elif pct_change < 0:
            score -= min(25, abs(pct_change) * 5)
            insights.append(f"FII holdings decreased by {pct_change:+.2f}% over last quarter")

        if fii_count >= 10:
            score += 5
            insights.append(f"Broad FII participation — {fii_count} FIIs hold the stock")
        elif fii_count <= 2 and fii_count > 0:
            score -= 5
            insights.append(f"Narrow FII participation — only {fii_count} FII(s) hold the stock")

        if gaining > losing and total_pct > 0:
            score += 5
            insights.append(f"{gaining} FIIs increased stake vs {losing} decreased")

        score = min(100, max(0, score))

        return {
            "fii_score": round(score, 2),
            "total_fiis": fii_count,
            "total_holding_pct": round(total_pct, 2),
            "pct_change": round(pct_change, 2),
            "gaining_fiis": gaining,
            "losing_fiis": losing,
            "top_fiis": [
                {"name": r.fii_name, "percentage": r.percentage, "change": r.change_percentage}
                for r in top_fiis
            ],
            "insights": insights,
        }

    # ------------------------------------------------------------------
    # AI: DII Scoring
    # ------------------------------------------------------------------

    async def analyze_dii(self, company_id: int) -> dict[str, Any]:
        result = await self._session.execute(
            select(DIIHolding)
            .where(DIIHolding.company_id == company_id)
            .order_by(DIIHolding.year.desc(), DIIHolding.quarter.desc())
        )
        rows = result.scalars().all()
        if not rows:
            return {"dii_score": 50.0, "total_diis": 0, "insights": ["No DII holdings data available"]}

        quarter_groups: dict[tuple[int, int], list[DIIHolding]] = {}
        for r in rows:
            quarter_groups.setdefault((r.year, r.quarter), []).append(r)

        sorted_quarters = sorted(quarter_groups.keys(), reverse=True)
        latest_q = sorted_quarters[0]
        prev_q = sorted_quarters[1] if len(sorted_quarters) > 1 else None

        latest = quarter_groups[latest_q]
        total_pct = sum(r.percentage for r in latest)
        dii_count = len(latest)

        if prev_q:
            prev_pct = sum(r.percentage for r in quarter_groups[prev_q])
            pct_change = total_pct - prev_pct
        else:
            pct_change = 0.0

        score = 50.0
        insights = []
        if pct_change > 0:
            score += min(15, pct_change * 3)
            insights.append(f"DII holdings increased by {pct_change:+.2f}% — domestic support")
        elif pct_change < 0:
            score -= min(20, abs(pct_change) * 4)
            insights.append(f"DII holdings decreased by {pct_change:+.2f}%")

        categories = set(r.category for r in latest)
        if len(categories) >= 3:
            score += 5
            insights.append(f"Broad DII participation across {len(categories)} categories")

        score = min(100, max(0, score))

        return {
            "dii_score": round(score, 2),
            "total_diis": dii_count,
            "total_holding_pct": round(total_pct, 2),
            "pct_change": round(pct_change, 2),
            "categories": list(categories),
            "insights": insights,
        }

    # ------------------------------------------------------------------
    # AI: Mutual Fund Scoring
    # ------------------------------------------------------------------

    async def analyze_mf(self, company_id: int) -> dict[str, Any]:
        result = await self._session.execute(
            select(MutualFundHolding)
            .where(MutualFundHolding.company_id == company_id)
            .order_by(MutualFundHolding.year.desc(), MutualFundHolding.quarter.desc())
        )
        rows = result.scalars().all()
        if not rows:
            return {"mf_score": 50.0, "total_schemes": 0, "insights": ["No MF holdings data available"]}

        quarter_groups: dict[tuple[int, int], list[MutualFundHolding]] = {}
        for r in rows:
            quarter_groups.setdefault((r.year, r.quarter), []).append(r)

        sorted_quarters = sorted(quarter_groups.keys(), reverse=True)
        latest_q = sorted_quarters[0]
        prev_q = sorted_quarters[1] if len(sorted_quarters) > 1 else None

        latest = quarter_groups[latest_q]
        total_schemes = len(latest)
        total_pct = sum(r.percentage for r in latest)
        unique_amcs = len(set(r.amc for r in latest))

        if prev_q:
            prev = quarter_groups[prev_q]
            prev_pct = sum(r.percentage for r in prev)
            pct_change = total_pct - prev_pct
            prev_schemes = len(prev)
            scheme_change = total_schemes - prev_schemes
        else:
            pct_change = 0.0
            scheme_change = 0

        top_schemes = sorted(latest, key=lambda r: r.percentage, reverse=True)[:5]

        amc_groups: dict[str, float] = {}
        for r in latest:
            amc_groups[r.amc] = amc_groups.get(r.amc, 0) + r.percentage
        top_amcs = sorted(amc_groups.items(), key=lambda x: x[1], reverse=True)[:3]

        score = 50.0
        insights = []
        if pct_change > 0:
            score += min(15, pct_change * 3)
            insights.append(f"Mutual fund holdings increased by {pct_change:+.2f}%")
        elif pct_change < 0:
            score -= min(20, abs(pct_change) * 4)
            insights.append(f"Mutual fund holdings decreased by {pct_change:+.2f}%")

        if scheme_change > 0:
            score += 5
            insights.append(f"{scheme_change} new schemes added the stock in the last quarter")
        elif scheme_change < 0:
            score -= 5
            insights.append(f"{abs(scheme_change)} schemes exited the stock in the last quarter")

        if unique_amcs >= 5:
            score += 5
            insights.append(f"Wide AMC participation — {unique_amcs} fund houses hold the stock")

        if top_schemes:
            insights.append(f"Top holder: {top_schemes[0].scheme_name} ({top_schemes[0].percentage:.2f}%)")

        score = min(100, max(0, score))

        return {
            "mf_score": round(score, 2),
            "total_schemes": total_schemes,
            "unique_amcs": unique_amcs,
            "total_holding_pct": round(total_pct, 2),
            "pct_change": round(pct_change, 2),
            "scheme_change": scheme_change,
            "top_schemes": [
                {"scheme_name": r.scheme_name, "amc": r.amc, "percentage": r.percentage, "change": r.change_percentage}
                for r in top_schemes
            ],
            "top_amcs": [{"amc": a, "total_pct": round(p, 2)} for a, p in top_amcs],
            "insights": insights,
        }

    # ------------------------------------------------------------------
    # AI: ETF Scoring
    # ------------------------------------------------------------------

    async def analyze_etf(self, company_id: int) -> dict[str, Any]:
        result = await self._session.execute(
            select(ETFHolding)
            .where(ETFHolding.company_id == company_id)
            .order_by(ETFHolding.year.desc(), ETFHolding.quarter.desc())
        )
        rows = result.scalars().all()
        if not rows:
            return {"etf_score": 50.0, "total_etfs": 0, "insights": ["No ETF holdings data available"]}

        quarter_groups: dict[tuple[int, int], list[ETFHolding]] = {}
        for r in rows:
            quarter_groups.setdefault((r.year, r.quarter), []).append(r)

        sorted_quarters = sorted(quarter_groups.keys(), reverse=True)
        latest_q = sorted_quarters[0]
        prev_q = sorted_quarters[1] if len(sorted_quarters) > 1 else None

        latest = quarter_groups[latest_q]
        total_pct = sum(r.percentage for r in latest)
        total_etfs = len(latest)

        if prev_q:
            prev_pct = sum(r.percentage for r in quarter_groups[prev_q])
            pct_change = total_pct - prev_pct
        else:
            pct_change = 0.0

        gaining = sum(1 for r in latest if r.change_percentage is not None and r.change_percentage > 0)
        losing = sum(1 for r in latest if r.change_percentage is not None and r.change_percentage < 0)

        score = 50.0
        insights = []
        if pct_change > 0:
            score += min(10, pct_change * 2)
            insights.append(f"ETF holdings increased by {pct_change:+.2f}% — passive inflow")
        elif pct_change < 0:
            score -= min(15, abs(pct_change) * 3)
            insights.append(f"ETF holdings decreased by {pct_change:+.2f}% — passive outflow")

        if gaining > losing:
            score += 3
            insights.append(f"{gaining} ETFs increased weight vs {losing} decreased")

        if total_etfs >= 5:
            score += 3
            insights.append(f"Stock held by {total_etfs} ETFs — broad passive coverage")

        score = min(100, max(0, score))

        return {
            "etf_score": round(score, 2),
            "total_etfs": total_etfs,
            "total_holding_pct": round(total_pct, 2),
            "pct_change": round(pct_change, 2),
            "gaining": gaining,
            "losing": losing,
            "insights": insights,
        }

    # ------------------------------------------------------------------
    # AI: Institutional Trends Scoring (cross-category)
    # ------------------------------------------------------------------

    async def analyze_institutional_trends(self, company_id: int) -> dict[str, Any]:
        fii = await self.analyze_fii(company_id)
        dii = await self.analyze_dii(company_id)
        mf = await self.analyze_mf(company_id)
        etf = await self.analyze_etf(company_id)

        fii_score = fii.get("fii_score", 50.0)
        dii_score = dii.get("dii_score", 50.0)
        mf_score = mf.get("mf_score", 50.0)
        etf_score = etf.get("etf_score", 50.0)

        fii_pct = fii.get("total_holding_pct", 0) or 0
        dii_pct = dii.get("total_holding_pct", 0) or 0
        fii_dii_div = fii_pct - dii_pct

        fii_change = fii.get("pct_change", 0) or 0
        dii_change = dii.get("pct_change", 0) or 0
        mf_change = mf.get("pct_change", 0) or 0
        etf_change = etf.get("pct_change", 0) or 0

        trend_score = (fii_score * 0.30 + dii_score * 0.25 + mf_score * 0.25 + etf_score * 0.20)
        trend_score = min(100, max(0, trend_score))

        divergence = "neutral"
        insights = []
        if fii_change > 1 and dii_change < -1:
            divergence = "fii_bullish_dii_bearish"
            insights.append("FIIs buying while DIIs selling — foreign optimism vs domestic caution")
        elif dii_change > 1 and fii_change < -1:
            divergence = "dii_bullish_fii_bearish"
            insights.append("DIIs buying while FIIs selling — domestic confidence vs foreign caution")
        elif fii_change > 0 and dii_change > 0:
            divergence = "both_bullish"
            insights.append("Both FIIs and DIIs accumulating — strong institutional conviction")
        elif fii_change < 0 and dii_change < 0:
            divergence = "both_bearish"
            insights.append("Both FIIs and DIIs reducing — broad institutional caution")

        if abs(fii_dii_div) > 5:
            insights.append(f"FII-DII holding gap of {fii_dii_div:.1f}% — {'FII' if fii_dii_div > 0 else 'DII'} dominated")

        if mf_change > 0:
            insights.append(f"Mutual funds increasing exposure (+{mf_change:+.2f}%) — active fund manager confidence")

        if etf_change > 0:
            insights.append(f"ETF passive inflows increasing (+{etf_change:+.2f}%)")

        return {
            "trend_score": round(trend_score, 2),
            "fii_dii_divergence": round(fii_dii_div, 2),
            "divergence_signal": divergence,
            "aggregate": {
                "fii_score": round(fii_score, 2),
                "dii_score": round(dii_score, 2),
                "mf_score": round(mf_score, 2),
                "etf_score": round(etf_score, 2),
            },
            "changes": {
                "fii_pct_change": round(fii_change, 2),
                "dii_pct_change": round(dii_change, 2),
                "mf_pct_change": round(mf_change, 2),
                "etf_pct_change": round(etf_change, 2),
            },
            "fii_analysis": fii,
            "dii_analysis": dii,
            "mf_analysis": mf,
            "etf_analysis": etf,
            "insights": insights,
        }

    # ------------------------------------------------------------------
    # AI: Full Institutional Analysis
    # ------------------------------------------------------------------

    def _compute_signal(self, score: float) -> str:
        if score >= 75: return "strong_buy"
        if score >= 60: return "buy"
        if score >= 45: return "hold"
        if score >= 30: return "sell"
        return "strong_sell"

    def _compute_confidence(self, data: dict[str, Any]) -> float:
        counts = [
            data.get("fii_analysis", {}).get("total_fiis", 0),
            data.get("dii_analysis", {}).get("total_diis", 0),
            data.get("mf_analysis", {}).get("total_schemes", 0),
            data.get("etf_analysis", {}).get("total_etfs", 0),
        ]
        has_data = sum(1 for c in counts if c > 0)
        total_entities = sum(counts)
        confidence = 40.0 + has_data * 10
        if total_entities > 20: confidence += 10
        elif total_entities > 10: confidence += 5
        return min(100, max(0, confidence))

    async def generate_analysis(self, company_id: int) -> InstitutionalAnalysis:
        trends = await self.analyze_institutional_trends(company_id)

        composite_score = trends["trend_score"]
        signal = self._compute_signal(composite_score)
        confidence = self._compute_confidence(trends)
        divergence = trends.get("fii_dii_divergence", 0)

        all_insights = []
        for src in ("fii_analysis", "dii_analysis", "mf_analysis", "etf_analysis"):
            all_insights.extend(trends.get(src, {}).get("insights", []))
        all_insights.extend(trends.get("insights", []))

        return await self._analysis_repo.create(
            company_id=company_id,
            analysis_date=date.today(),
            fii_score=trends["aggregate"]["fii_score"],
            dii_score=trends["aggregate"]["dii_score"],
            mf_score=trends["aggregate"]["mf_score"],
            etf_score=trends["aggregate"]["etf_score"],
            institutional_trend_score=trends["trend_score"],
            fii_dii_divergence=divergence,
            composite_score=round(composite_score, 2),
            signal=signal,
            confidence=round(confidence, 2),
            insights_json=json.dumps({
                "insights": all_insights,
                "divergence_signal": trends.get("divergence_signal"),
                "aggregate": trends["aggregate"],
                "changes": trends["changes"],
            }),
        )

    async def get_analysis(self, analysis_id: int) -> InstitutionalAnalysis | None:
        return await self._analysis_repo.get(analysis_id)

    async def list_analyses(
        self, company_id: int | None = None, signal: str | None = None,
        skip: int = 0, limit: int = 100,
    ) -> tuple[Sequence[InstitutionalAnalysis], int]:
        query = select(InstitutionalAnalysis)
        cq = select(func.count()).select_from(InstitutionalAnalysis)
        if company_id is not None:
            query = query.where(InstitutionalAnalysis.company_id == company_id)
            cq = cq.where(InstitutionalAnalysis.company_id == company_id)
        if signal is not None:
            query = query.where(InstitutionalAnalysis.signal == signal)
            cq = cq.where(InstitutionalAnalysis.signal == signal)
        total = (await self._session.execute(cq)).scalar() or 0
        query = query.order_by(InstitutionalAnalysis.generated_at.desc()).offset(skip).limit(limit)
        rows = (await self._session.execute(query)).scalars().all()
        return rows, total

    async def get_latest_analysis(self, company_id: int) -> InstitutionalAnalysis | None:
        result = await self._session.execute(
            select(InstitutionalAnalysis)
            .where(InstitutionalAnalysis.company_id == company_id)
            .order_by(InstitutionalAnalysis.generated_at.desc()).limit(1)
        )
        return result.scalar_one_or_none()

    async def delete_analysis(self, analysis_id: int) -> bool:
        return await self._analysis_repo.delete(analysis_id)
