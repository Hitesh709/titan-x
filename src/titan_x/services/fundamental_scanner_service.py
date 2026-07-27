"""Fundamental scanner service.

Scans all symbols for ROE, ROCE, Debt, Revenue Growth, EPS Growth,
Cash Flow, and Valuation signals. Generates composite scores and rankings.
"""
from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import date
from typing import Any

import structlog
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.models.company import Company
from titan_x.models.financial import FinancialStatement
from titan_x.models.fundamental import FundamentalMetric
from titan_x.models.fundamental_scanner import FundamentalScanResult

logger = structlog.get_logger(__name__)

SIGNAL_STRENGTH_MAX = 100


def _gv(stmt: FinancialStatement | None, concept: str) -> float | None:
    if stmt is None or not stmt.line_items:
        return None
    item_map = {li.concept: li.value for li in stmt.line_items}
    return item_map.get(concept)


class FundamentalScannerService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def scan_all(self) -> list[FundamentalScanResult]:
        companies = await self._get_active_symbols()
        results: list[FundamentalScanResult] = []
        today = date.today()

        for company in companies:
            try:
                r = await self._scan_symbol(company.symbol, today)
                results.append(r)
            except Exception as exc:
                logger.error("fs_scan_failed", symbol=company.symbol, error=str(exc))

        await self.session.commit()

        for r in results:
            await self.session.refresh(r)
        return results

    async def scan_symbol(
        self, symbol: str, scan_date: date | None = None,
    ) -> FundamentalScanResult:
        today = scan_date or date.today()
        result = await self._scan_symbol(symbol.upper(), today)
        await self.session.commit()
        await self.session.refresh(result)
        return result

    async def _scan_symbol(
        self, symbol: str, scan_date: date,
    ) -> FundamentalScanResult:
        metrics = await self._get_latest_metrics(symbol)
        fs = await self._get_latest_financial_statement(symbol)

        signals: dict[str, Any] = {}
        scores: dict[str, float] = {}
        signal_values: dict[str, str | None] = {}

        scorers: list[tuple[str, Any]] = [
            ("roe", (metrics.get("ROE"),)),
            ("roce", (metrics.get("ROCE"),)),
            ("debt", (metrics.get("DEBT_EQUITY"),)),
            ("revenue_growth", (metrics.get("REVENUE_GROWTH"),)),
            ("eps_growth", (metrics.get("EPS_GROWTH"),)),
            ("cash_flow", (metrics.get("QUALITY_SCORE"),)),
            ("valuation", (metrics.get("PE"), metrics.get("PB"))),
        ]

        for name, args in scorers:
            scorer = getattr(self, f"_score_{name}")
            try:
                result = scorer(*args)
                signals[name] = result
                scores[name] = result["score"]
                signal_values[name] = result.get("signal")
            except Exception as exc:
                logger.warning("fs_scorer_failed", symbol=symbol, scorer=name, error=str(exc))

        valid_scores = [s for s in scores.values() if s > 0]
        composite = sum(valid_scores) / len(valid_scores) if valid_scores else 0.0
        composite = max(0.0, min(SIGNAL_STRENGTH_MAX, composite))

        result = FundamentalScanResult(
            symbol=symbol,
            scan_date=scan_date,
            composite_score=round(composite, 2),
            roe_score=round(scores.get("roe", 0.0), 2),
            roce_score=round(scores.get("roce", 0.0), 2),
            debt_score=round(scores.get("debt", 0.0), 2),
            revenue_growth_score=round(scores.get("revenue_growth", 0.0), 2),
            eps_growth_score=round(scores.get("eps_growth", 0.0), 2),
            cash_flow_score=round(scores.get("cash_flow", 0.0), 2),
            valuation_score=round(scores.get("valuation", 0.0), 2),
            roe_signal=signal_values.get("roe"),
            roce_signal=signal_values.get("roce"),
            debt_signal=signal_values.get("debt"),
            revenue_growth_signal=signal_values.get("revenue_growth"),
            eps_growth_signal=signal_values.get("eps_growth"),
            cash_flow_signal=signal_values.get("cash_flow"),
            valuation_signal=signal_values.get("valuation"),
            signals_json=json.dumps(signals, default=str),
        )
        self.session.add(result)
        await self.session.flush()
        return result

    # ================================================================
    # 7 Scorers
    # ================================================================

    def _score_roe(self, roe: float | None) -> dict[str, Any]:
        if roe is None:
            return _neutral("roe")
        if roe > 25:
            return {
                "name": "roe", "signal": "strong_bullish", "score": 95,
                "description": f"Exceptional ROE of {roe:.1f}%",
                "value": roe,
            }
        if roe > 18:
            return {
                "name": "roe", "signal": "bullish", "score": 80,
                "description": f"Strong ROE of {roe:.1f}%",
                "value": roe,
            }
        if roe > 12:
            return {
                "name": "roe", "signal": "bullish", "score": 65,
                "description": f"Good ROE of {roe:.1f}%",
                "value": roe,
            }
        if roe > 8:
            return {
                "name": "roe", "signal": "neutral", "score": 50,
                "description": f"Adequate ROE of {roe:.1f}%",
                "value": roe,
            }
        if roe > 0:
            return {
                "name": "roe", "signal": "bearish", "score": 30,
                "description": f"Weak ROE of {roe:.1f}%",
                "value": roe,
            }
        return {
            "name": "roe", "signal": "strong_bearish", "score": 10,
            "description": f"Negative ROE of {roe:.1f}%",
            "value": roe,
        }

    def _score_roce(self, roce: float | None) -> dict[str, Any]:
        if roce is None:
            return _neutral("roce")
        if roce > 25:
            return {
                "name": "roce", "signal": "strong_bullish", "score": 95,
                "description": f"Exceptional ROCE of {roce:.1f}%",
                "value": roce,
            }
        if roce > 18:
            return {
                "name": "roce", "signal": "bullish", "score": 80,
                "description": f"Strong ROCE of {roce:.1f}%",
                "value": roce,
            }
        if roce > 12:
            return {
                "name": "roce", "signal": "bullish", "score": 65,
                "description": f"Good ROCE of {roce:.1f}%",
                "value": roce,
            }
        if roce > 8:
            return {
                "name": "roce", "signal": "neutral", "score": 50,
                "description": f"Adequate ROCE of {roce:.1f}%",
                "value": roce,
            }
        if roce > 0:
            return {
                "name": "roce", "signal": "bearish", "score": 30,
                "description": f"Weak ROCE of {roce:.1f}%",
                "value": roce,
            }
        return {
            "name": "roce", "signal": "strong_bearish", "score": 10,
            "description": f"Negative ROCE of {roce:.1f}%",
            "value": roce,
        }

    def _score_debt(self, debt_equity: float | None) -> dict[str, Any]:
        if debt_equity is None:
            return _neutral("debt")
        if debt_equity < 0.3:
            return {
                "name": "debt", "signal": "strong_bullish", "score": 95,
                "description": f"Very low debt-to-equity of {debt_equity:.2f}",
                "value": debt_equity,
            }
        if debt_equity < 0.8:
            return {
                "name": "debt", "signal": "bullish", "score": 80,
                "description": f"Low debt-to-equity of {debt_equity:.2f}",
                "value": debt_equity,
            }
        if debt_equity < 1.5:
            return {
                "name": "debt", "signal": "neutral", "score": 55,
                "description": f"Moderate debt-to-equity of {debt_equity:.2f}",
                "value": debt_equity,
            }
        if debt_equity < 3.0:
            return {
                "name": "debt", "signal": "bearish", "score": 30,
                "description": f"High debt-to-equity of {debt_equity:.2f}",
                "value": debt_equity,
            }
        return {
            "name": "debt", "signal": "strong_bearish", "score": 10,
            "description": f"Very high debt-to-equity of {debt_equity:.2f}",
            "value": debt_equity,
        }

    def _score_revenue_growth(self, growth: float | None) -> dict[str, Any]:
        if growth is None:
            return _neutral("revenue_growth")
        if growth > 30:
            return {
                "name": "revenue_growth", "signal": "strong_bullish", "score": 95,
                "description": f"Exceptional revenue growth of {growth:.1f}%",
                "value": growth,
            }
        if growth > 15:
            return {
                "name": "revenue_growth", "signal": "bullish", "score": 80,
                "description": f"Strong revenue growth of {growth:.1f}%",
                "value": growth,
            }
        if growth > 8:
            return {
                "name": "revenue_growth", "signal": "bullish", "score": 65,
                "description": f"Good revenue growth of {growth:.1f}%",
                "value": growth,
            }
        if growth > 0:
            return {
                "name": "revenue_growth", "signal": "neutral", "score": 50,
                "description": f"Positive revenue growth of {growth:.1f}%",
                "value": growth,
            }
        if growth > -10:
            return {
                "name": "revenue_growth", "signal": "bearish", "score": 25,
                "description": f"Declining revenue of {growth:.1f}%",
                "value": growth,
            }
        return {
            "name": "revenue_growth", "signal": "strong_bearish", "score": 5,
            "description": f"Sharp revenue decline of {growth:.1f}%",
            "value": growth,
        }

    def _score_eps_growth(self, growth: float | None) -> dict[str, Any]:
        if growth is None:
            return _neutral("eps_growth")
        if growth > 30:
            return {
                "name": "eps_growth", "signal": "strong_bullish", "score": 95,
                "description": f"Exceptional EPS growth of {growth:.1f}%",
                "value": growth,
            }
        if growth > 15:
            return {
                "name": "eps_growth", "signal": "bullish", "score": 80,
                "description": f"Strong EPS growth of {growth:.1f}%",
                "value": growth,
            }
        if growth > 8:
            return {
                "name": "eps_growth", "signal": "bullish", "score": 65,
                "description": f"Good EPS growth of {growth:.1f}%",
                "value": growth,
            }
        if growth > 0:
            return {
                "name": "eps_growth", "signal": "neutral", "score": 50,
                "description": f"Positive EPS growth of {growth:.1f}%",
                "value": growth,
            }
        if growth > -10:
            return {
                "name": "eps_growth", "signal": "bearish", "score": 25,
                "description": f"Declining EPS of {growth:.1f}%",
                "value": growth,
            }
        return {
            "name": "eps_growth", "signal": "strong_bearish", "score": 5,
            "description": f"Sharp EPS decline of {growth:.1f}%",
            "value": growth,
        }

    def _score_cash_flow(self, quality_score: float | None) -> dict[str, Any]:
        if quality_score is None:
            return _neutral("cash_flow")
        if quality_score >= 8:
            return {
                "name": "cash_flow", "signal": "strong_bullish", "score": 95,
                "description": f"Excellent cash flow quality score of {quality_score:.1f}/10",
                "value": quality_score,
            }
        if quality_score >= 6:
            return {
                "name": "cash_flow", "signal": "bullish", "score": 75,
                "description": f"Good cash flow quality score of {quality_score:.1f}/10",
                "value": quality_score,
            }
        if quality_score >= 4:
            return {
                "name": "cash_flow", "signal": "neutral", "score": 50,
                "description": f"Average cash flow quality score of {quality_score:.1f}/10",
                "value": quality_score,
            }
        if quality_score >= 2:
            return {
                "name": "cash_flow", "signal": "bearish", "score": 25,
                "description": f"Weak cash flow quality score of {quality_score:.1f}/10",
                "value": quality_score,
            }
        return {
            "name": "cash_flow", "signal": "strong_bearish", "score": 5,
            "description": f"Poor cash flow quality score of {quality_score:.1f}/10",
            "value": quality_score,
        }

    def _score_valuation(self, pe: float | None, pb: float | None) -> dict[str, Any]:
        if pe is None and pb is None:
            return _neutral("valuation")
        pe_score = 50.0
        pb_score = 50.0
        if pe is not None and pe > 0:
            if pe < 10:
                pe_score = 90
            elif pe < 18:
                pe_score = 75
            elif pe < 25:
                pe_score = 55
            elif pe < 40:
                pe_score = 35
            elif pe < 60:
                pe_score = 20
            else:
                pe_score = 10
        elif pe is not None and pe <= 0:
            pe_score = 5
        if pb is not None and pb > 0:
            if pb < 1:
                pb_score = 85
            elif pb < 3:
                pb_score = 70
            elif pb < 5:
                pb_score = 50
            elif pb < 10:
                pb_score = 30
            else:
                pb_score = 15
        elif pb is not None and pb <= 0:
            pb_score = 5
        score = (pe_score + pb_score) / 2
        if pe is not None and pb is None:
            score = pe_score
        if pb is not None and pe is None:
            score = pb_score
        if score >= 80:
            signal = "bullish"
            desc_text = f"Attractive valuation"
        elif score >= 50:
            signal = "neutral"
            desc_text = f"Fair valuation"
        elif score >= 30:
            signal = "bearish"
            desc_text = f"Rich valuation"
        else:
            signal = "strong_bearish"
            desc_text = f"Expensive valuation"
        parts = []
        if pe is not None:
            parts.append(f"PE: {pe:.1f}")
        if pb is not None:
            parts.append(f"PB: {pb:.1f}")
        return {
            "name": "valuation", "signal": signal, "score": round(score),
            "description": f"{desc_text} ({', '.join(parts)})",
            "pe": pe, "pb": pb,
        }

    # ================================================================
    # Query helpers
    # ================================================================

    async def get_rankings(
        self, scan_date: date | None = None,
        min_score: float = 0, limit: int = 100,
    ) -> list[FundamentalScanResult]:
        d = scan_date or date.today()
        stmt = (
            select(FundamentalScanResult)
            .where(
                FundamentalScanResult.scan_date == d,
                FundamentalScanResult.composite_score >= min_score,
            )
            .order_by(FundamentalScanResult.composite_score.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_latest_scan(
        self, symbol: str,
    ) -> FundamentalScanResult | None:
        result = await self.session.execute(
            select(FundamentalScanResult)
            .where(FundamentalScanResult.symbol == symbol.upper())
            .order_by(FundamentalScanResult.scan_date.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_scan_history(
        self, symbol: str, limit: int = 30,
    ) -> list[FundamentalScanResult]:
        result = await self.session.execute(
            select(FundamentalScanResult)
            .where(FundamentalScanResult.symbol == symbol.upper())
            .order_by(FundamentalScanResult.scan_date.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_top_by_dimension(
        self, dimension: str, scan_date: date | None = None,
        limit: int = 20,
    ) -> list[FundamentalScanResult]:
        d = scan_date or date.today()
        score_col = getattr(FundamentalScanResult, f"{dimension}_score", None)
        if score_col is None:
            return []
        sig_col = getattr(FundamentalScanResult, f"{dimension}_signal", None)
        stmt = select(FundamentalScanResult).where(
            FundamentalScanResult.scan_date == d,
        )
        if sig_col is not None:
            stmt = stmt.where(
                sig_col.in_(["strong_bullish", "bullish", "strong_bearish", "bearish"])
            )
        stmt = stmt.order_by(score_col.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_scan_summary(
        self, scan_date: date | None = None,
    ) -> dict[str, Any]:
        d = scan_date or date.today()
        total = await self.session.execute(
            select(func.count(FundamentalScanResult.id)).where(
                FundamentalScanResult.scan_date == d,
            )
        )
        avg = await self.session.execute(
            select(func.avg(FundamentalScanResult.composite_score)).where(
                FundamentalScanResult.scan_date == d,
            )
        )
        strong = await self.session.execute(
            select(func.count(FundamentalScanResult.id)).where(
                FundamentalScanResult.scan_date == d,
                FundamentalScanResult.composite_score >= 75,
            )
        )
        weak = await self.session.execute(
            select(func.count(FundamentalScanResult.id)).where(
                FundamentalScanResult.scan_date == d,
                FundamentalScanResult.composite_score <= 40,
            )
        )
        return {
            "scan_date": d.isoformat(),
            "total_scanned": total.scalar() or 0,
            "avg_composite_score": round(float(avg.scalar() or 0), 2),
            "strong_count": strong.scalar() or 0,
            "weak_count": weak.scalar() or 0,
        }

    async def get_all_scan_dates(self) -> list[date]:
        result = await self.session.execute(
            select(FundamentalScanResult.scan_date)
            .distinct()
            .order_by(FundamentalScanResult.scan_date.desc())
        )
        return [r[0] for r in result.all()]

    # ================================================================
    # Internal helpers
    # ================================================================

    async def _get_active_symbols(self) -> list[Company]:
        result = await self.session.execute(
            select(Company).where(Company.status == "active")
        )
        return list(result.scalars().all())

    async def _get_latest_metrics(
        self, symbol: str,
    ) -> dict[str, float | None]:
        result = await self.session.execute(
            select(FundamentalMetric)
            .where(
                FundamentalMetric.symbol == symbol.upper(),
                FundamentalMetric.period_type == "annual",
            )
            .order_by(
                FundamentalMetric.fiscal_year.desc(),
                FundamentalMetric.metric_name.asc(),
            )
        )
        rows = list(result.scalars().all())
        metric_names = {
            "ROE", "ROCE", "DEBT_EQUITY", "REVENUE_GROWTH",
            "EPS_GROWTH", "QUALITY_SCORE", "PE", "PB",
        }
        seen_years: set[int] = set()
        metrics: dict[str, float | None] = {}
        for r in rows:
            if r.metric_name in metric_names and r.metric_name not in metrics:
                metrics[r.metric_name] = r.value
                seen_years.add(r.fiscal_year)
        return metrics

    async def _get_latest_financial_statement(
        self, symbol: str,
    ) -> FinancialStatement | None:
        result = await self.session.execute(
            select(FinancialStatement)
            .where(
                FinancialStatement.symbol == symbol.upper(),
                FinancialStatement.statement_type == "cash_flow",
            )
            .order_by(FinancialStatement.fiscal_year.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()


def _neutral(name: str) -> dict[str, Any]:
    return {
        "name": name, "signal": "neutral",
        "score": 0, "description": "No data available",
    }
