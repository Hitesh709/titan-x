from collections.abc import Sequence
from datetime import date
from typing import Any

import structlog
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.models.sector import SectorPerformance

logger = structlog.get_logger(__name__)

SIGNAL_ORDER = {"lagging": 0, "neutral": 1, "leading": 2}
PERIOD_LABELS = ["1W", "1M", "3M", "6M", "YTD", "1Y"]


class SectorRotationService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def detect_rotation(
        self, as_of_date: date | None = None,
    ) -> dict[str, Any]:
        if as_of_date is None:
            as_of_date = date.today()

        current = await self._get_period_data(as_of_date, "1M")
        previous = await self._get_previous_period_data(as_of_date, "1M")

        sectors = await self._get_all_sectors_with_history(as_of_date)

        current_signals = self._compute_rotation_signals(current)
        prev_signals = self._compute_rotation_signals(previous)

        entering_strength = self._detect_entering_strength(current_signals, prev_signals, current)
        losing_strength = self._detect_losing_strength(current_signals, prev_signals, current)

        rankings = self._build_rankings(current, previous, current_signals)

        historical_comparisons = self._build_historical_comparisons(sectors)

        summary = self._build_summary(rankings, entering_strength, losing_strength)

        return {
            "as_of_date": as_of_date.isoformat(),
            "period": "1M",
            "entering_strength": entering_strength,
            "losing_strength": losing_strength,
            "historical_comparisons": historical_comparisons,
            "rankings": rankings,
            "summary": summary,
        }

    async def _get_period_data(
        self, as_of_date: date, period: str,
    ) -> list[dict[str, Any]]:
        rows = await self._session.execute(
            select(SectorPerformance)
            .where(
                SectorPerformance.as_of_date <= as_of_date,
                SectorPerformance.period_label == period,
            )
            .order_by(desc(SectorPerformance.as_of_date))
        )
        seen: set[str] = set()
        result: list[dict[str, Any]] = []
        for r in rows.scalars().all():
            if r.sector not in seen:
                seen.add(r.sector)
                result.append({
                    "sector": r.sector,
                    "as_of_date": r.as_of_date,
                    "return_pct": r.return_pct,
                    "momentum_score": r.momentum_score,
                    "relative_strength": r.relative_strength,
                    "rank": r.rank,
                    "constituent_count": r.constituent_count,
                })
        return result

    async def _get_previous_period_data(
        self, as_of_date: date, period: str,
    ) -> list[dict[str, Any]]:
        current_dates = await self._session.execute(
            select(func.max(SectorPerformance.as_of_date))
            .where(
                SectorPerformance.as_of_date <= as_of_date,
                SectorPerformance.period_label == period,
            )
        )
        max_date = current_dates.scalar_one_or_none()
        if max_date is None:
            return []

        prev_dates = await self._session.execute(
            select(func.max(SectorPerformance.as_of_date))
            .where(
                SectorPerformance.as_of_date < max_date,
                SectorPerformance.period_label == period,
            )
        )
        prev_max = prev_dates.scalar_one_or_none()
        if prev_max is None:
            return []
        return await self._get_period_data(prev_max, period)

    def _compute_rotation_signals(
        self, data: list[dict[str, Any]],
    ) -> dict[str, str]:
        scores = [d.get("momentum_score") for d in data if d.get("momentum_score") is not None]
        signals: dict[str, str] = {}
        if not scores:
            for d in data:
                signals[d["sector"]] = "neutral"
            return signals

        sorted_scores = sorted(scores)
        n = len(sorted_scores)
        top_th = sorted_scores[n * 3 // 4] if n >= 4 else sorted_scores[-1]
        bottom_th = sorted_scores[n // 4] if n >= 4 else sorted_scores[0]

        for d in data:
            ms = d.get("momentum_score")
            if ms is not None:
                if ms >= top_th:
                    signals[d["sector"]] = "leading"
                elif ms <= bottom_th:
                    signals[d["sector"]] = "lagging"
                else:
                    signals[d["sector"]] = "neutral"
            else:
                signals[d["sector"]] = "neutral"
        return signals

    def _detect_entering_strength(
        self, current: dict[str, str], previous: dict[str, str],
        current_data: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for d in current_data:
            sec = d["sector"]
            cur = current.get(sec, "neutral")
            prev = previous.get(sec, "neutral")
            if SIGNAL_ORDER.get(cur, 1) > SIGNAL_ORDER.get(prev, 1):
                entry = {
                    "sector": sec,
                    "previous_signal": prev,
                    "current_signal": cur,
                    "momentum_score": d.get("momentum_score"),
                    "return_pct": d.get("return_pct"),
                    "relative_strength": d.get("relative_strength"),
                    "rank": d.get("rank"),
                }
                result.append(entry)

        result.sort(key=lambda x: (SIGNAL_ORDER.get(x["current_signal"], 1), x.get("momentum_score") or 0), reverse=True)
        return result

    def _detect_losing_strength(
        self, current: dict[str, str], previous: dict[str, str],
        current_data: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for d in current_data:
            sec = d["sector"]
            cur = current.get(sec, "neutral")
            prev = previous.get(sec, "neutral")
            if SIGNAL_ORDER.get(cur, 1) < SIGNAL_ORDER.get(prev, 1):
                entry = {
                    "sector": sec,
                    "previous_signal": prev,
                    "current_signal": cur,
                    "momentum_score": d.get("momentum_score"),
                    "return_pct": d.get("return_pct"),
                    "relative_strength": d.get("relative_strength"),
                    "rank": d.get("rank"),
                }
                result.append(entry)

        result.sort(key=lambda x: (SIGNAL_ORDER.get(x["current_signal"], 1), x.get("momentum_score") or 0))
        return result

    async def _get_all_sectors_with_history(
        self, as_of_date: date,
    ) -> dict[str, list[dict[str, Any]]]:
        rows = await self._session.execute(
            select(SectorPerformance)
            .where(
                SectorPerformance.as_of_date <= as_of_date,
                SectorPerformance.period_label.in_(["1W", "1M", "3M", "6M", "YTD", "1Y"]),
            )
            .order_by(desc(SectorPerformance.as_of_date))
        )
        sectors: dict[str, list[dict[str, Any]]] = {}
        for r in rows.scalars().all():
            if r.sector not in sectors:
                sectors[r.sector] = []
            if len(sectors[r.sector]) < 12:
                sectors[r.sector].append({
                    "as_of_date": r.as_of_date.isoformat(),
                    "period_label": r.period_label,
                    "return_pct": r.return_pct,
                    "momentum_score": r.momentum_score,
                    "relative_strength": r.relative_strength,
                    "rank": r.rank,
                })
        return sectors

    def _build_rankings(
        self, current: list[dict[str, Any]], previous: list[dict[str, Any]],
        current_signals: dict[str, str],
    ) -> list[dict[str, Any]]:
        prev_ranks: dict[str, int] = {
            d["sector"]: d["rank"] for d in previous if d.get("rank") is not None
        }

        rankings = []
        for d in current:
            sec = d["sector"]
            prev_r = prev_ranks.get(sec)
            cur_r = d.get("rank")
            rank_change = None
            if cur_r is not None and prev_r is not None:
                rank_change = prev_r - cur_r

            rankings.append({
                "sector": sec,
                "rank": cur_r,
                "previous_rank": prev_r,
                "rank_change": rank_change,
                "momentum_score": d.get("momentum_score"),
                "return_pct": d.get("return_pct"),
                "relative_strength": d.get("relative_strength"),
                "rotation_signal": current_signals.get(sec, "neutral"),
            })

        rankings.sort(key=lambda x: x["rank"] if x["rank"] is not None else 999)
        return rankings

    def _build_historical_comparisons(
        self, sectors: dict[str, list[dict[str, Any]]],
    ) -> list[dict[str, Any]]:
        comparisons = []
        for sec, records in sectors.items():
            month_over_month = self._compute_period_comparison(records)
            score_trend = self._compute_score_trend(records)

            leading_count = sum(1 for r in records if r.get("rotation_signal") == "leading" if "rotation_signal" in r)
            stable = score_trend.get("stable", True)

            entry = {
                "sector": sec,
                "record_count": len(records),
                "month_over_month": month_over_month,
                "score_trend": score_trend,
            }
            comparisons.append(entry)

        comparisons.sort(key=lambda x: abs(x.get("score_trend", {}).get("slope", 0) or 0), reverse=True)
        return comparisons

    def _compute_period_comparison(
        self, records: list[dict[str, Any]],
    ) -> dict[str, Any]:
        by_period: dict[str, list[float]] = {}
        for r in records:
            pl = r.get("period_label", "1M")
            ret = r.get("return_pct")
            if ret is not None:
                if pl not in by_period:
                    by_period[pl] = []
                by_period[pl].append(ret)

        comparison: dict[str, Any] = {}
        for pl in PERIOD_LABELS:
            vals = by_period.get(pl, [])
            if len(vals) >= 2:
                comparison[pl] = {
                    "latest": round(vals[0], 2),
                    "previous": round(vals[1], 2),
                    "change": round(vals[0] - vals[1], 2),
                }
            elif len(vals) == 1:
                comparison[pl] = {
                    "latest": round(vals[0], 2),
                    "previous": None,
                    "change": None,
                }
        return comparison

    def _compute_score_trend(
        self, records: list[dict[str, Any]],
    ) -> dict[str, Any]:
        one_m_vals = [r for r in records if r.get("period_label") == "1M"]
        momentum_vals = [r.get("momentum_score") for r in one_m_vals if r.get("momentum_score") is not None]

        if len(momentum_vals) < 2:
            return {"direction": "stable", "slope": 0, "stable": True}

        slope = momentum_vals[0] - momentum_vals[-1]

        if slope > 5:
            direction = "improving"
        elif slope < -5:
            direction = "declining"
        else:
            direction = "stable"

        return {
            "direction": direction,
            "slope": round(slope, 2),
            "latest": momentum_vals[0],
            "earliest": momentum_vals[-1],
            "stable": direction == "stable",
        }

    def _build_summary(
        self, rankings: list[dict[str, Any]],
        entering: list[dict[str, Any]], losing: list[dict[str, Any]],
    ) -> dict[str, Any]:
        improving = sum(1 for r in rankings if r.get("rank_change") is not None and r["rank_change"] > 0)
        declining = sum(1 for r in rankings if r.get("rank_change") is not None and r["rank_change"] < 0)
        stable = sum(1 for r in rankings if r.get("rank_change") is None or r["rank_change"] == 0)

        return {
            "total_sectors": len(rankings),
            "entering_strength_count": len(entering),
            "losing_strength_count": len(losing),
            "ranks_improving": improving,
            "ranks_declining": declining,
            "ranks_stable": stable,
            "avg_return_pct": round(
                sum(r.get("return_pct") or 0 for r in rankings) / len(rankings), 2,
            ) if rankings else None,
        }
