import json
from collections.abc import Sequence
from datetime import date, timedelta
from typing import Any

import structlog
from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.db.repository import BaseRepository
from titan_x.models.company import Company
from titan_x.models.price import DailyPrice
from titan_x.models.sector import SectorPerformance

logger = structlog.get_logger(__name__)

PERIOD_LABELS = ["1W", "1M", "3M", "6M", "YTD", "1Y", "3Y", "5Y"]
PERIOD_DAYS: dict[str, int] = {
    "1W": 7, "1M": 30, "3M": 90, "6M": 180,
    "YTD": 0, "1Y": 365, "3Y": 1095, "5Y": 1825,
}

MOMENTUM_WEIGHTS = {
    "1M": 0.40,
    "3M": 0.30,
    "6M": 0.20,
    "1Y": 0.10,
}


class SectorEngine:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = BaseRepository(session, SectorPerformance)

    async def _get_sectors(self) -> list[str]:
        result = await self._session.execute(
            select(Company.sector).distinct().where(
                Company.sector.isnot(None), Company.status == "active",
            ).order_by(Company.sector)
        )
        return [r[0] for r in result.all() if r[0]]

    async def _get_symbols_for_sector(self, sector: str) -> list[str]:
        result = await self._session.execute(
            select(Company.symbol).where(
                Company.sector == sector, Company.status == "active",
            )
        )
        return [r[0] for r in result.all()]

    async def _get_prices_for_period(
        self, symbols: list[str], end_date: date, days: int,
    ) -> dict[str, tuple[float | None, float | None]]:
        if not symbols:
            return {}
        if days == 0:
            start_date = date(end_date.year, 1, 1)
        else:
            start_date = end_date - timedelta(days=days)

        latest_prices: dict[str, float | None] = {}
        for sym in symbols:
            result = await self._session.execute(
                select(DailyPrice.close)
                .where(DailyPrice.symbol == sym, DailyPrice.trade_date <= end_date)
                .order_by(DailyPrice.trade_date.desc())
                .limit(1)
            )
            latest_prices[sym] = result.scalar_one_or_none()

        start_prices: dict[str, float | None] = {}
        for sym in symbols:
            result = await self._session.execute(
                select(DailyPrice.close)
                .where(DailyPrice.symbol == sym, DailyPrice.trade_date >= start_date)
                .order_by(DailyPrice.trade_date.asc())
                .limit(1)
            )
            sp = result.scalar_one_or_none()
            if sp is None:
                result2 = await self._session.execute(
                    select(DailyPrice.close)
                    .where(DailyPrice.symbol == sym, DailyPrice.trade_date < start_date)
                    .order_by(DailyPrice.trade_date.desc())
                    .limit(1)
                )
                sp = result2.scalar_one_or_none()
            start_prices[sym] = sp

        result_dict: dict[str, tuple[float | None, float | None]] = {}
        for sym in symbols:
            result_dict[sym] = (latest_prices.get(sym), start_prices.get(sym))
        return result_dict

    async def _sector_return(self, sector: str, end_date: date, days: int) -> float | None:
        symbols = await self._get_symbols_for_sector(sector)
        if not symbols:
            return None
        prices = await self._get_prices_for_period(symbols, end_date, days)
        returns: list[float] = []
        for sym in symbols:
            latest, start = prices.get(sym, (None, None))
            if latest is not None and start is not None and start > 0:
                returns.append((latest - start) / start * 100)
        if not returns:
            return None
        return round(sum(returns) / len(returns), 4)

    async def compute_sector_performance(
        self, sector: str, end_date: date | None = None,
    ) -> dict[str, Any]:
        if end_date is None:
            end_date = date.today()

        results: dict[str, Any] = {
            "sector": sector, "as_of_date": end_date.isoformat(),
            "constituent_count": len(await self._get_symbols_for_sector(sector)),
            "periods": {},
            "momentum_score": None,
            "relative_strength": None,
            "ytd_return": None,
        }

        returns: dict[str, float | None] = {}
        for label in PERIOD_LABELS:
            days = PERIOD_DAYS[label]
            ret = await self._sector_return(sector, end_date, days)
            returns[label] = ret
            results["periods"][label] = ret

        usable_returns = {k: v for k, v in returns.items() if v is not None and k in MOMENTUM_WEIGHTS}
        if usable_returns:
            momentum = sum(usable_returns[k] * MOMENTUM_WEIGHTS[k] for k in usable_returns)
            results["momentum_score"] = round(momentum, 4)

        results["ytd_return"] = returns.get("YTD")

        all_sectors = await self._get_sectors()
        benchmark_returns: dict[str, float | None] = {}
        for label in ["1M", "3M", "6M", "1Y"]:
            all_rets: list[float] = []
            for s in all_sectors:
                if s == sector:
                    continue
                sr = await self._sector_return(s, end_date, PERIOD_DAYS[label])
                if sr is not None:
                    all_rets.append(sr)
            benchmark_returns[label] = round(sum(all_rets) / len(all_rets), 4) if all_rets else None

        rs_scores: list[float] = []
        for label in ["1M", "3M", "6M", "1Y"]:
            sr = returns.get(label)
            br = benchmark_returns.get(label)
            if sr is not None and br is not None and br != 0:
                rs_scores.append(sr / br)
        results["relative_strength"] = round(sum(rs_scores) / len(rs_scores), 4) if rs_scores else None

        return results

    async def compute_all_sectors(
        self, end_date: date | None = None, store: bool = True,
    ) -> list[dict[str, Any]]:
        if end_date is None:
            end_date = date.today()

        sectors = await self._get_sectors()
        all_results: list[dict[str, Any]] = []

        for sector in sectors:
            perf = await self.compute_sector_performance(sector, end_date)
            all_results.append(perf)

        all_results.sort(key=lambda x: x.get("momentum_score") or -9999, reverse=True)
        for rank, perf in enumerate(all_results, 1):
            perf["rank"] = rank

        if store:
            for perf in all_results:
                for label in PERIOD_LABELS:
                    ret = perf["periods"].get(label)
                    if ret is not None:
                        await self._store_sector_perf(
                            sector=perf["sector"], as_of_date=end_date,
                            period_label=label, return_pct=ret,
                            momentum_score=perf.get("momentum_score"),
                            relative_strength=perf.get("relative_strength"),
                            rank=perf.get("rank"),
                            constituent_count=perf.get("constituent_count"),
                        )
            await self._session.flush()

        self._enrich_rotation_signal(all_results)
        return all_results

    async def _load_latest_stored(
        self, end_date: date | None = None,
    ) -> dict[str, Sequence[SectorPerformance]]:
        q = select(func.max(SectorPerformance.as_of_date))
        if end_date is not None:
            q = q.where(SectorPerformance.as_of_date <= end_date)
        result = await self._session.execute(q)
        latest = result.scalar_one_or_none()
        if latest is None:
            return {}

        rows_result = await self._session.execute(
            select(SectorPerformance).where(SectorPerformance.as_of_date == latest)
        )
        grouped: dict[str, list[SectorPerformance]] = {}
        for r in rows_result.scalars().all():
            grouped.setdefault(r.sector, []).append(r)
        return grouped

    async def get_ranking(
        self, end_date: date | None = None,
    ) -> list[dict[str, Any]]:
        stored = await self._load_latest_stored(end_date)
        if not stored:
            return []

        results: list[dict[str, Any]] = []
        for sector, rows in stored.items():
            by_label = {r.period_label: r for r in rows}
            results.append({
                "rank": None,
                "sector": sector,
                "momentum_score": next(
                    (r.momentum_score for r in rows if r.momentum_score is not None), None,
                ),
                "relative_strength": next(
                    (r.relative_strength for r in rows if r.relative_strength is not None), None,
                ),
                "ytd_return": by_label.get("YTD").return_pct if by_label.get("YTD") else None,
                "constituent_count": next(
                    (r.constituent_count for r in rows if r.constituent_count is not None), None,
                ),
                "periods": {
                    label: (by_label.get(label).return_pct if by_label.get(label) else None)
                    for label in ["1M", "3M", "6M", "1Y"]
                },
                "rotation_signal": None,
            })

        results.sort(key=lambda x: x.get("momentum_score") if x.get("momentum_score") is not None else -9999, reverse=True)
        for rank, r in enumerate(results, 1):
            r["rank"] = rank
        self._enrich_rotation_signal(results)
        return results

    async def get_rotation(
        self, end_date: date | None = None,
    ) -> dict[str, Any]:
        sectors = await self.get_ranking(end_date)
        as_of_date = None
        if sectors:
            stored = await self._load_latest_stored(end_date)
            if stored:
                as_of_date = next(iter(next(iter(stored.values())))).as_of_date

        leading = [s for s in sectors if s.get("rotation_signal") == "leading"]
        lagging = [s for s in sectors if s.get("rotation_signal") == "lagging"]
        neutral = [s for s in sectors if s.get("rotation_signal") == "neutral"]

        return {
            "as_of_date": as_of_date.isoformat() if as_of_date else (end_date or date.today()).isoformat(),
            "leading": [{"sector": s["sector"], "momentum_score": s.get("momentum_score"), "rank": s.get("rank")} for s in leading],
            "lagging": [{"sector": s["sector"], "momentum_score": s.get("momentum_score"), "rank": s.get("rank")} for s in lagging],
            "neutral": [{"sector": s["sector"], "momentum_score": s.get("momentum_score"), "rank": s.get("rank")} for s in neutral],
            "rotation_breadth": len(leading) / max(len(sectors), 1),
        }

    async def get_historical_performance(
        self, sector: str, period_label: str = "1M", limit: int = 20,
    ) -> list[dict[str, Any]]:
        stmt = (
            select(SectorPerformance)
            .where(
                SectorPerformance.sector == sector,
                SectorPerformance.period_label == period_label,
            )
            .order_by(SectorPerformance.as_of_date.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        rows = result.scalars().all()
        return [
            {
                "as_of_date": r.as_of_date.isoformat(),
                "return_pct": r.return_pct,
                "momentum_score": r.momentum_score,
                "relative_strength": r.relative_strength,
                "rank": r.rank,
            }
            for r in rows
        ]

    async def get_sector_summary(self, sector: str) -> dict[str, Any]:
        symbols = await self._get_symbols_for_sector(sector)
        latest_result = await self._session.execute(
            select(SectorPerformance)
            .where(SectorPerformance.sector == sector)
            .order_by(SectorPerformance.as_of_date.desc())
            .limit(1)
        )
        latest = latest_result.scalar_one_or_none()

        return {
            "sector": sector,
            "constituent_count": len(symbols),
            "latest_performance": {
                "as_of_date": latest.as_of_date.isoformat() if latest else None,
                "momentum_score": latest.momentum_score if latest else None,
                "relative_strength": latest.relative_strength if latest else None,
                "rank": latest.rank if latest else None,
            } if latest else None,
        }

    async def get_stored_performance(
        self, sector: str | None = None, *, period_label: str | None = None,
        as_of_date: date | None = None, skip: int = 0, limit: int = 100,
    ) -> tuple[Sequence[SectorPerformance], int]:
        stmt = select(SectorPerformance)
        if sector:
            stmt = stmt.where(SectorPerformance.sector == sector)
        if period_label:
            stmt = stmt.where(SectorPerformance.period_label == period_label)
        if as_of_date:
            stmt = stmt.where(SectorPerformance.as_of_date == as_of_date)

        count_result = await self._session.execute(stmt)
        total = len(count_result.scalars().all())
        stmt = stmt.order_by(SectorPerformance.as_of_date.desc(), SectorPerformance.rank.asc().nullslast()).offset(skip).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all()), total

    def _enrich_rotation_signal(self, results: list[dict[str, Any]]) -> None:
        scores = [r.get("momentum_score") for r in results if r.get("momentum_score") is not None]
        if not scores:
            return
        sorted_scores = sorted(scores)
        n = len(sorted_scores)
        top_threshold = sorted_scores[n * 3 // 4] if n >= 4 else sorted_scores[-1] if n > 0 else 0
        bottom_threshold = sorted_scores[n // 4] if n >= 4 else sorted_scores[0] if n > 0 else 0

        for r in results:
            ms = r.get("momentum_score")
            if ms is not None:
                if ms >= top_threshold:
                    r["rotation_signal"] = "leading"
                elif ms <= bottom_threshold:
                    r["rotation_signal"] = "lagging"
                else:
                    r["rotation_signal"] = "neutral"
            else:
                r["rotation_signal"] = "neutral"

    async def _store_sector_perf(
        self, sector: str, as_of_date: date, period_label: str,
        return_pct: float | None, momentum_score: float | None,
        relative_strength: float | None, rank: int | None,
        constituent_count: int | None,
    ) -> None:
        existing = await self._session.execute(
            select(SectorPerformance).where(
                SectorPerformance.sector == sector,
                SectorPerformance.as_of_date == as_of_date,
                SectorPerformance.period_label == period_label,
            )
        )
        if existing.scalar_one_or_none() is not None:
            return
        await self._repo.create(
            sector=sector, as_of_date=as_of_date, period_label=period_label,
            return_pct=return_pct, momentum_score=momentum_score,
            relative_strength=relative_strength, rank=rank,
            constituent_count=constituent_count,
        )

    async def list_all_sectors(self) -> list[str]:
        return await self._get_sectors()
