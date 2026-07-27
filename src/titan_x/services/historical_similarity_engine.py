import json
import math
from collections.abc import Sequence
from datetime import date, timedelta
from typing import Any

import structlog
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.db.repository import BaseRepository
from titan_x.models.historical_similarity import SimilarityAnalysis, SimilarityMatch
from titan_x.models.price import DailyPrice

logger = structlog.get_logger(__name__)

FORWARD_HORIZONS = [1, 5, 10, 20, 60]
PRICE_WEIGHT = 0.5
CORRELATION_WEIGHT = 0.3
VOLUME_WEIGHT = 0.2


class HistoricalSimilarityEngine:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._analysis_repo = BaseRepository(session, SimilarityAnalysis)
        self._match_repo = BaseRepository(session, SimilarityMatch)

    async def _get_price_sequence(
        self, symbol: str, start_date: date, end_date: date,
    ) -> list[dict[str, Any]]:
        result = await self._session.execute(
            select(DailyPrice)
            .where(
                DailyPrice.symbol == symbol,
                DailyPrice.trade_date.between(start_date, end_date),
            )
            .order_by(DailyPrice.trade_date)
        )
        return [
            {"trade_date": r.trade_date, "close": r.close, "volume": r.volume}
            for r in result.scalars().all()
        ]

    def _normalize(self, values: list[float]) -> list[float]:
        if not values:
            return []
        mn, mx = min(values), max(values)
        if mx == mn:
            return [0.5] * len(values)
        return [(v - mn) / (mx - mn) for v in values]

    def _pearson_correlation(self, a: list[float], b: list[float]) -> float:
        n = len(a)
        if n < 3:
            return 0.0
        mean_a = sum(a) / n
        mean_b = sum(b) / n
        num = sum((a[i] - mean_a) * (b[i] - mean_b) for i in range(n))
        den_a = math.sqrt(sum((a[i] - mean_a) ** 2 for i in range(n)))
        den_b = math.sqrt(sum((b[i] - mean_b) ** 2 for i in range(n)))
        den = den_a * den_b
        return num / den if den != 0 else 0.0

    def _euclidean_similarity(self, a: list[float], b: list[float]) -> float:
        n = len(a)
        if n == 0:
            return 0.0
        dist = math.sqrt(sum((a[i] - b[i]) ** 2 for i in range(n)))
        return 1.0 / (1.0 + dist / n)

    def _volume_similarity(self, query_vol: list[float], hist_vol: list[float]) -> float:
        n = len(query_vol)
        if n == 0:
            return 0.0
        q_norm = self._normalize(query_vol)
        h_norm = self._normalize(hist_vol)
        dist = math.sqrt(sum((q_norm[i] - h_norm[i]) ** 2 for i in range(n)))
        return 1.0 / (1.0 + dist / n)

    def _compute_similarity(
        self, query_norm: list[float], hist_norm: list[float],
        query_vol: list[int], hist_vol: list[int],
    ) -> dict[str, float]:
        corr = self._pearson_correlation(query_norm, hist_norm)
        if corr < 0:
            corr = max(corr, -1.0)
        price_dist = self._euclidean_similarity(query_norm, hist_norm)
        vol_sim = self._volume_similarity(
            [float(v) for v in query_vol],
            [float(v) for v in hist_vol],
        )
        combined = (
            max(0, corr) * CORRELATION_WEIGHT +
            price_dist * PRICE_WEIGHT +
            vol_sim * VOLUME_WEIGHT
        )
        return {
            "correlation": round(corr, 4),
            "price_distance": round(price_dist, 4),
            "volume_similarity": round(vol_sim, 4),
            "score": round(combined, 4),
        }

    async def search(
        self, symbol: str, end_date: date | None = None,
        window_days: int = 20, lookback_days: int = 3650,
        max_matches: int = 50, min_similarity: float = 0.0,
        store: bool = False,
    ) -> dict[str, Any]:
        if end_date is None:
            end_date = date.today()

        query_start = end_date - timedelta(days=window_days * 2)
        query_prices = await self._get_price_sequence(symbol, query_start, end_date)
        if len(query_prices) < window_days:
            query_prices = await self._get_price_sequence(
                symbol, end_date - timedelta(days=lookback_days), end_date,
            )
        if len(query_prices) < window_days:
            return {
                "symbol": symbol, "query_end_date": end_date.isoformat(),
                "error": f"Insufficient data: need {window_days} days, got {len(query_prices)}",
                "matches": [], "statistics": {},
            }

        query_window = query_prices[-window_days:]
        query_close = [p["close"] for p in query_window]
        query_vol = [int(p["volume"]) for p in query_window]
        query_norm = self._normalize(query_close)

        history_start = end_date - timedelta(days=lookback_days)
        history_start = max(history_start, query_prices[0]["trade_date"]) if query_prices else history_start
        result = await self._session.execute(
            select(DailyPrice)
            .where(
                DailyPrice.symbol == symbol,
                DailyPrice.trade_date.between(history_start, query_window[0]["trade_date"] - timedelta(days=1)),
            )
            .order_by(DailyPrice.trade_date)
        )
        historical = [
            {"trade_date": r.trade_date, "close": r.close, "volume": r.volume}
            for r in result.scalars().all()
        ]

        if len(historical) < window_days:
            return {
                "symbol": symbol, "query_end_date": end_date.isoformat(),
                "error": f"Insufficient historical data: need {window_days} days, got {len(historical)}",
                "matches": [], "statistics": {},
            }

        candidates: list[dict[str, Any]] = []
        for i in range(len(historical) - window_days + 1):
            hist_window = historical[i:i + window_days]
            hist_close = [p["close"] for p in hist_window]
            hist_vol = [int(p["volume"]) for p in hist_window]
            hist_norm = self._normalize(hist_close)
            sim = self._compute_similarity(query_norm, hist_norm, query_vol, hist_vol)
            if sim["score"] >= min_similarity:
                candidates.append({
                    "match_start_date": hist_window[0]["trade_date"].isoformat(),
                    "match_end_date": hist_window[-1]["trade_date"].isoformat(),
                    "similarity_score": sim["score"],
                    "price_correlation": sim["correlation"],
                    "price_distance": sim["price_distance"],
                    "volume_similarity": sim["volume_similarity"],
                })

        candidates.sort(key=lambda x: x["similarity_score"], reverse=True)
        matches = candidates[:max_matches]
        await self._enrich_matches_with_forward(symbol, matches, end_date)

        for rank, m in enumerate(matches, 1):
            m["match_rank"] = rank
            m["match_symbol"] = symbol

        statistics = self._compute_statistics(matches) if matches else {}

        if store and matches:
            analysis = await self._analysis_repo.create(
                symbol=symbol,
                query_start_date=query_window[0]["trade_date"],
                query_end_date=query_window[-1]["trade_date"],
                window_days=window_days,
                lookback_days=lookback_days,
                max_matches=max_matches,
                min_similarity=min_similarity,
                total_matches=len(matches),
                avg_similarity=statistics.get("avg_similarity"),
                best_similarity=statistics.get("best_similarity"),
                worst_similarity=statistics.get("worst_similarity"),
                avg_return_1d=statistics.get("avg_return_1d"),
                avg_return_5d=statistics.get("avg_return_5d"),
                avg_return_10d=statistics.get("avg_return_10d"),
                avg_return_20d=statistics.get("avg_return_20d"),
                avg_return_60d=statistics.get("avg_return_60d"),
                avg_holding_period=statistics.get("avg_holding_period"),
                optimal_holding_period=statistics.get("optimal_holding_period"),
                optimal_return=statistics.get("optimal_return"),
                metadata_json=json.dumps({"query_close_range": {"min": round(min(query_close), 2), "max": round(max(query_close), 2)}}),
            )
            for m in matches:
                await self._match_repo.create(
                    analysis_id=analysis.id,
                    match_rank=m["match_rank"],
                    match_symbol=m["match_symbol"],
                    match_start_date=date.fromisoformat(m["match_start_date"]),
                    match_end_date=date.fromisoformat(m["match_end_date"]),
                    similarity_score=m["similarity_score"],
                    price_correlation=m["price_correlation"],
                    price_distance=m["price_distance"],
                    volume_similarity=m["volume_similarity"],
                    forward_return_1d=m.get("forward_return_1d"),
                    forward_return_5d=m.get("forward_return_5d"),
                    forward_return_10d=m.get("forward_return_10d"),
                    forward_return_20d=m.get("forward_return_20d"),
                    forward_return_60d=m.get("forward_return_60d"),
                )
            await self._session.flush()

        return {
            "symbol": symbol,
            "query_end_date": end_date.isoformat(),
            "query_window_days": window_days,
            "query_close_range": {"min": round(min(query_close), 2), "max": round(max(query_close), 2)},
            "total_candidates": len(candidates),
            "matches": matches,
            "statistics": statistics,
        }

    async def _compute_forward_returns_for_match(
        self, symbol: str, match_end_date: date, query_end_date: date,
    ) -> dict[str, float | None]:
        result: dict[str, float | None] = {}
        for horizon in FORWARD_HORIZONS:
            target_date = match_end_date + timedelta(days=horizon * 2)
            if target_date > query_end_date:
                target_date = query_end_date
            forward_prices = await self._get_price_sequence(
                symbol, match_end_date + timedelta(days=1), target_date,
            )
            if len(forward_prices) >= horizon:
                future_close = forward_prices[min(horizon, len(forward_prices)) - 1]["close"]
                past_close = forward_prices[0]["close"] if horizon <= len(forward_prices) else None
                if past_close and past_close > 0:
                    result[f"forward_return_{horizon}d"] = round(
                        (future_close - past_close) / past_close * 100, 4,
                    )
                else:
                    result[f"forward_return_{horizon}d"] = None
            else:
                result[f"forward_return_{horizon}d"] = None
        return result

    async def _enrich_matches_with_forward(self, symbol: str, matches: list[dict], query_end_date: date) -> None:
        for m in matches:
            match_end = date.fromisoformat(m["match_end_date"])
            forward = await self._compute_forward_returns_for_match(symbol, match_end, query_end_date)
            m.update(forward)

    def _compute_statistics(self, matches: list[dict[str, Any]]) -> dict[str, Any]:
        if not matches:
            return {}
        scores = [m["similarity_score"] for m in matches if m.get("similarity_score")]
        stats: dict[str, Any] = {
            "total_matches": len(matches),
            "avg_similarity": round(sum(scores) / len(scores), 4) if scores else 0,
            "best_similarity": max(scores) if scores else 0,
            "worst_similarity": min(scores) if scores else 0,
        }

        horizons_stats: dict[str, list[float]] = {}
        for horizon in FORWARD_HORIZONS:
            key = f"forward_return_{horizon}d"
            vals = [
                m[key] for m in matches
                if m.get(key) is not None
            ]
            horizons_stats[key] = vals
            if vals:
                weighted = sum(
                    m[key] * m["similarity_score"] for m in matches if m.get(key) is not None
                )
                total_weight = sum(
                    m["similarity_score"] for m in matches if m.get(key) is not None
                )
                stats[f"avg_return_{horizon}d"] = round(weighted / total_weight, 4) if total_weight > 0 else round(sum(vals) / len(vals), 4)
            else:
                stats[f"avg_return_{horizon}d"] = None

        best_horizon = max(
            FORWARD_HORIZONS,
            key=lambda h: stats.get(f"avg_return_{h}d") or -9999,
            default=20,
        )
        stats["optimal_holding_period"] = best_horizon
        stats["optimal_return"] = stats.get(f"avg_return_{best_horizon}d")

        hold_periods: list[float] = []
        for m in matches:
            best_h = max(
                FORWARD_HORIZONS,
                key=lambda h: m.get(f"forward_return_{h}d") or -9999,
                default=None,
            )
            if best_h is not None and m.get(f"forward_return_{best_h}d") is not None:
                hold_periods.append(float(best_h))
        stats["avg_holding_period"] = round(
            sum(hold_periods) / len(hold_periods), 2,
        ) if hold_periods else None

        return stats

    async def get_analyses(
        self, symbol: str | None = None, skip: int = 0, limit: int = 100,
    ) -> tuple[Sequence[SimilarityAnalysis], int]:
        stmt = select(SimilarityAnalysis)
        if symbol:
            stmt = stmt.where(SimilarityAnalysis.symbol == symbol)
        count_result = await self._session.execute(stmt)
        total = len(count_result.scalars().all())
        stmt = stmt.order_by(SimilarityAnalysis.created_at.desc()).offset(skip).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all()), total

    async def get_analysis_by_id(self, analysis_id: int) -> SimilarityAnalysis | None:
        return await self._analysis_repo.get(analysis_id)

    async def get_matches_for_analysis(
        self, analysis_id: int, skip: int = 0, limit: int = 100,
    ) -> tuple[Sequence[SimilarityMatch], int]:
        stmt = select(SimilarityMatch).where(SimilarityMatch.analysis_id == analysis_id)
        count_result = await self._session.execute(stmt)
        total = len(count_result.scalars().all())
        stmt = stmt.order_by(SimilarityMatch.match_rank).offset(skip).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all()), total

    async def delete_analysis(self, analysis_id: int) -> bool:
        matches_stmt = select(SimilarityMatch).where(SimilarityMatch.analysis_id == analysis_id)
        matches_result = await self._session.execute(matches_stmt)
        for m in matches_result.scalars().all():
            await self._session.delete(m)
        analysis = await self._analysis_repo.get(analysis_id)
        if analysis is None:
            return False
        await self._session.delete(analysis)
        await self._session.flush()
        return True

    async def calculate_forward_returns_for_analysis(self, analysis_id: int) -> dict[str, Any]:
        matches, total = await self.get_matches_for_analysis(analysis_id, limit=500)
        if not matches:
            return {"error": "No matches found", "updated": 0}
        updated = 0
        for m in matches:
            forward = await self._compute_forward_returns_for_match(
                m.match_symbol, m.match_end_date, date.today(),
            )
            for key, val in forward.items():
                col = getattr(m, key, None)
                if col is not None:
                    setattr(m, key, val)
            updated += 1
        if updated:
            await self._session.flush()
            analysis = await self._analysis_repo.get(analysis_id)
            if analysis:
                all_matches, _ = await self.get_matches_for_analysis(analysis_id, limit=500)
                match_dicts = [
                    {
                        "similarity_score": mm.similarity_score,
                        "forward_return_1d": mm.forward_return_1d,
                        "forward_return_5d": mm.forward_return_5d,
                        "forward_return_10d": mm.forward_return_10d,
                        "forward_return_20d": mm.forward_return_20d,
                        "forward_return_60d": mm.forward_return_60d,
                    }
                    for mm in all_matches
                ]
                stats = self._compute_statistics(match_dicts)
                for key, val in stats.items():
                    if hasattr(analysis, key):
                        setattr(analysis, key, val)
                await self._session.flush()
        return {"updated": updated}

    async def search_cross_symbol(
        self, symbol: str, compare_symbols: list[str],
        end_date: date | None = None,
        window_days: int = 20, lookback_days: int = 3650,
        max_matches: int = 50, min_similarity: float = 0.0,
    ) -> dict[str, Any]:
        if end_date is None:
            end_date = date.today()
        query_prices = await self._get_price_sequence(
            symbol, end_date - timedelta(days=window_days * 2), end_date,
        )
        if len(query_prices) < window_days:
            return {"symbol": symbol, "error": "Insufficient query data", "matches_by_symbol": {}}
        query_window = query_prices[-window_days:]
        query_norm = self._normalize([p["close"] for p in query_window])
        query_vol = [int(p["volume"]) for p in query_window]

        results_by_symbol: dict[str, list[dict]] = {}
        for csym in compare_symbols:
            history = await self._get_price_sequence(
                csym, end_date - timedelta(days=lookback_days), end_date - timedelta(days=1),
            )
            if len(history) < window_days:
                continue
            symbol_matches: list[dict] = []
            for i in range(len(history) - window_days + 1):
                hw = history[i:i + window_days]
                hn = self._normalize([p["close"] for p in hw])
                hv = [int(p["volume"]) for p in hw]
                sim = self._compute_similarity(query_norm, hn, query_vol, hv)
                if sim["score"] >= min_similarity:
                    symbol_matches.append({
                        "match_start_date": hw[0]["trade_date"].isoformat(),
                        "match_end_date": hw[-1]["trade_date"].isoformat(),
                        **sim,
                    })
            symbol_matches.sort(key=lambda x: x["score"], reverse=True)
            results_by_symbol[csym] = symbol_matches[:max_matches // max(len(compare_symbols), 1)]

        return {
            "symbol": symbol,
            "query_end_date": end_date.isoformat(),
            "window_days": window_days,
            "compare_symbols": compare_symbols,
            "matches_by_symbol": results_by_symbol,
        }
