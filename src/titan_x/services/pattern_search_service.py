import math
from collections import defaultdict
from datetime import date, timedelta
from typing import Any

import structlog
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.db.repository import BaseRepository
from titan_x.models.pattern_search import PatternSearchMatch, PatternSearchQuery
from titan_x.models.price import DailyPrice

logger = structlog.get_logger(__name__)

FORWARD_HORIZONS = [1, 5, 10, 20, 60]
PRICE_WEIGHT = 0.5
CORRELATION_WEIGHT = 0.3
VOLUME_WEIGHT = 0.2


class PatternSearchService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.query_repo = BaseRepository(session, PatternSearchQuery)
        self.match_repo = BaseRepository(session, PatternSearchMatch)

    async def search(
        self, symbol: str, pattern_type: str,
        start_date: date, end_date: date, window_days: int = 20,
        lookback_years: int = 30, min_similarity: float = 0.8,
        max_matches: int = 50,
    ) -> PatternSearchQuery:
        self._window_days = window_days
        query_seq = await self._get_price_sequence(symbol, start_date, end_date)
        if len(query_seq) < window_days:
            raise ValueError(f"Insufficient price data: need {window_days} days, got {len(query_seq)}")

        lookback_start = end_date - timedelta(days=lookback_years * 365)
        result = await self.session.execute(
            select(DailyPrice).where(
                DailyPrice.trade_date >= lookback_start,
                DailyPrice.trade_date <= end_date - timedelta(days=1),
            ).order_by(DailyPrice.symbol, DailyPrice.trade_date)
        )
        all_prices = list(result.scalars().all())

        grouped = defaultdict(list)
        for p in all_prices:
            grouped[p.symbol].append(p)

        query_close = [float(p.close) for p in query_seq[:window_days]]
        query_vol = [float(p.volume) for p in query_seq[:window_days]]
        query_norm = self._normalize(query_close)
        query_ret = self._returns(query_close)

        matches: list[dict[str, Any]] = []

        for sym, px_list in grouped.items():
            if sym == symbol.upper():
                continue
            if len(px_list) < window_days + 60:
                continue

            for i in range(len(px_list) - window_days + 1):
                segment = px_list[i:i + window_days]
                seg_close = [float(p.close) for p in segment]
                seg_norm = self._normalize(seg_close)

                price_dist = self._euclidean(query_norm, seg_norm)
                if price_dist > 1.0:
                    continue

                seg_vol = [float(p.volume) for p in segment]
                vol_sim = self._volume_similarity(query_vol, seg_vol)
                corr = self._pearson(query_close, seg_close)

                sim = (
                    PRICE_WEIGHT * (1.0 - price_dist) +
                    CORRELATION_WEIGHT * abs(corr) +
                    VOLUME_WEIGHT * vol_sim
                )

                if sim >= min_similarity:
                    match_end = segment[-1].trade_date
                    forward_rets = self._compute_forward_returns(sym, match_end, px_list, i)
                    winning = forward_rets.get("fwd_20d", 0) > 0

                    matches.append({
                        "match_symbol": sym,
                        "match_start_date": segment[0].trade_date,
                        "match_end_date": match_end,
                        "similarity_score": round(sim, 4),
                        "price_correlation": round(corr, 4),
                        "price_distance": round(price_dist, 4),
                        "volume_similarity": round(vol_sim, 4),
                        **{f"forward_return_{k}d": v for k, v in forward_rets.items()},
                        "is_winning": winning,
                    })

        matches.sort(key=lambda x: -x["similarity_score"])
        matches = matches[:max_matches]

        winning = [m for m in matches if m.get("is_winning")]
        losing = [m for m in matches if not m.get("is_winning")]
        win_rate = len(winning) / len(matches) * 100 if matches else 0
        avg_ret = sum(m.get("forward_return_20d", 0) for m in matches) / len(matches) if matches else 0
        avg_loss = sum(m.get("forward_return_20d", 0) for m in losing) / len(losing) if losing else 0

        best_sim = matches[0]["similarity_score"] if matches else 0
        worst_sim = matches[-1]["similarity_score"] if matches else 0

        horizon_rets = {}
        for h in FORWARD_HORIZONS:
            vals = [m.get(f"forward_return_{h}d", 0) for m in matches]
            horizon_rets[f"avg_return_{h}d"] = round(sum(vals) / len(vals), 4) if vals else 0

        optimal_holding = self._find_optimal_holding(matches)

        query = PatternSearchQuery(
            symbol=symbol.upper(), pattern_type=pattern_type,
            start_date=start_date, end_date=end_date,
            window_days=window_days, lookback_years=lookback_years,
            total_matches=len(matches),
            avg_similarity=round(sum(m["similarity_score"] for m in matches) / len(matches), 4) if matches else 0,
            best_similarity=round(best_sim, 4),
            avg_return=round(avg_ret, 4),
            avg_loss=round(avg_loss, 4),
            win_rate=round(win_rate, 2),
            optimal_holding_days=optimal_holding,
            **horizon_rets,
        )
        self.session.add(query)
        await self.session.flush()

        for rank, m in enumerate(matches, 1):
            match = PatternSearchMatch(query_id=query.id, match_rank=rank, **m)
            self.session.add(match)
        await self.session.flush()
        await self.session.refresh(query)
        return query

    async def get_query(self, query_id: int) -> PatternSearchQuery | None:
        result = await self.session.execute(
            select(PatternSearchQuery).where(PatternSearchQuery.id == query_id)
        )
        return result.scalar_one_or_none()

    async def get_matches(
        self, query_id: int, limit: int = 100,
    ) -> list[PatternSearchMatch]:
        result = await self.session.execute(
            select(PatternSearchMatch).where(
                PatternSearchMatch.query_id == query_id,
            ).order_by(PatternSearchMatch.match_rank).limit(limit)
        )
        return list(result.scalars().all())

    async def get_history(
        self, symbol: str | None = None, limit: int = 20,
    ) -> list[PatternSearchQuery]:
        stmt = select(PatternSearchQuery)
        if symbol:
            stmt = stmt.where(PatternSearchQuery.symbol == symbol.upper())
        stmt = stmt.order_by(desc(PatternSearchQuery.created_at)).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def _get_price_sequence(
        self, symbol: str, start_date: date, end_date: date,
    ) -> list:
        result = await self.session.execute(
            select(DailyPrice).where(
                DailyPrice.symbol == symbol,
                DailyPrice.trade_date.between(start_date, end_date),
            ).order_by(DailyPrice.trade_date)
        )
        return list(result.scalars().all())

    def _normalize(self, values: list[float]) -> list[float]:
        if not values:
            return []
        mn, mx = min(values), max(values)
        if mx == mn:
            return [0.5] * len(values)
        return [(v - mn) / (mx - mn) for v in values]

    def _euclidean(self, a: list[float], b: list[float]) -> float:
        if not a or not b:
            return 1.0
        n = min(len(a), len(b))
        dist = math.sqrt(sum((a[i] - b[i]) ** 2 for i in range(n)) / n)
        return min(dist, 1.0)

    def _pearson(self, a: list[float], b: list[float]) -> float:
        n = min(len(a), len(b))
        if n < 3:
            return 0.0
        a = a[:n]
        b = b[:n]
        ma = sum(a) / n
        mb = sum(b) / n
        num = sum((a[i] - ma) * (b[i] - mb) for i in range(n))
        den = math.sqrt(sum((a[i] - ma) ** 2 for i in range(n))) * math.sqrt(sum((b[i] - mb) ** 2 for i in range(n)))
        return num / den if den != 0 else 0.0

    def _returns(self, prices: list[float]) -> list[float]:
        if len(prices) < 2:
            return []
        return [(prices[i] - prices[i - 1]) / prices[i - 1] for i in range(1, len(prices))]

    def _volume_similarity(self, q_vol: list[float], s_vol: list[float]) -> float:
        if not q_vol or not s_vol:
            return 0.5
        n = min(len(q_vol), len(s_vol))
        q_norm = self._normalize(q_vol[:n])
        s_norm = self._normalize(s_vol[:n])
        dist = self._euclidean(q_norm, s_norm)
        return 1.0 - dist

    def _compute_forward_returns(
        self, symbol: str, match_end: date, symbol_prices: list, current_index: int,
    ) -> dict[str, float]:
        wd = getattr(self, "_window_days", 20)
        result = {}
        for horizon in FORWARD_HORIZONS:
            fwd_idx = current_index + wd + horizon - 1
            if fwd_idx < len(symbol_prices):
                entry = symbol_prices[current_index + wd - 1].close
                exit_price = symbol_prices[fwd_idx].close
                result[horizon] = (exit_price - entry) / entry if entry > 0 else 0
            else:
                result[horizon] = 0.0
        return result

    def _find_optimal_holding(self, matches: list[dict]) -> int | None:
        if not matches:
            return None
        best_horizon = 1
        best_return = -999
        for h in FORWARD_HORIZONS:
            key = f"forward_return_{h}d"
            avg = sum(m.get(key, 0) for m in matches) / len(matches)
            if avg > best_return:
                best_return = avg
                best_horizon = h
        return best_horizon
