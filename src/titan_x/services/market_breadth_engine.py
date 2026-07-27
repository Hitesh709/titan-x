from collections.abc import Sequence
from datetime import date, timedelta
from typing import Any

import structlog
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.db.repository import BaseRepository
from titan_x.models.company import Company
from titan_x.models.price import DailyPrice
from titan_x.models.market_breadth import MarketBreadth

logger = structlog.get_logger(__name__)

OSCILLATOR_PERIOD = 10
HIGH_LOW_LOOKBACK_DAYS = 365


class MarketBreadthEngine:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = BaseRepository(session, MarketBreadth)

    async def _get_active_symbols(self) -> list[str]:
        result = await self._session.execute(
            select(Company.symbol).where(Company.status == "active"),
        )
        return [r[0] for r in result.all()]

    async def _get_today_prices(
        self, symbols: list[str], trade_date: date,
    ) -> dict[str, dict[str, Any]]:
        if not symbols:
            return {}
        result = await self._session.execute(
            select(DailyPrice.symbol, DailyPrice.close, DailyPrice.volume)
            .where(
                DailyPrice.symbol.in_(symbols),
                DailyPrice.trade_date == trade_date,
            )
        )
        return {
            r[0]: {"close": r[1], "volume": r[2]}
            for r in result.all()
        }

    async def _get_prev_close(self, symbol: str, trade_date: date) -> float | None:
        result = await self._session.execute(
            select(DailyPrice.close)
            .where(
                DailyPrice.symbol == symbol,
                DailyPrice.trade_date < trade_date,
            )
            .order_by(DailyPrice.trade_date.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _get_bulk_prev_close(
        self, symbols: list[str], trade_date: date,
    ) -> dict[str, float | None]:
        if not symbols:
            return {}
        subq = (
            select(
                DailyPrice.symbol,
                func.max(DailyPrice.trade_date).label("max_date"),
            )
            .where(
                DailyPrice.symbol.in_(symbols),
                DailyPrice.trade_date < trade_date,
            )
            .group_by(DailyPrice.symbol)
        ).subquery()

        result = await self._session.execute(
            select(DailyPrice.symbol, DailyPrice.close)
            .join(
                subq,
                and_(
                    DailyPrice.symbol == subq.c.symbol,
                    DailyPrice.trade_date == subq.c.max_date,
                ),
            )
        )
        return {r[0]: r[1] for r in result.all()}

    async def _get_52w_high_low(
        self, symbols: list[str], trade_date: date,
    ) -> dict[str, dict[str, float | None]]:
        if not symbols:
            return {}
        start_date = trade_date - timedelta(days=HIGH_LOW_LOOKBACK_DAYS)
        result = await self._session.execute(
            select(
                DailyPrice.symbol,
                func.max(DailyPrice.close).label("high_52w"),
                func.min(DailyPrice.close).label("low_52w"),
            )
            .where(
                DailyPrice.symbol.in_(symbols),
                DailyPrice.trade_date.between(start_date, trade_date),
            )
            .group_by(DailyPrice.symbol)
        )
        return {
            r[0]: {"high": r[1], "low": r[2]}
            for r in result.all()
        }

    async def _get_recent_breadth_dates(
        self, limit: int = OSCILLATOR_PERIOD,
    ) -> list[date]:
        result = await self._session.execute(
            select(MarketBreadth.trade_date)
            .order_by(MarketBreadth.trade_date.desc())
            .limit(limit)
        )
        return [r[0] for r in result.all()]

    async def _get_previous_ad_line(self, trade_date: date) -> float:
        result = await self._session.execute(
            select(MarketBreadth.advance_decline_line)
            .where(MarketBreadth.trade_date < trade_date)
            .order_by(MarketBreadth.trade_date.desc())
            .limit(1)
        )
        val = result.scalar_one_or_none()
        return val if val is not None else 0.0

    async def _get_net_advances_pct_for_dates(
        self, dates: list[date],
    ) -> list[float]:
        if not dates:
            return []
        result = await self._session.execute(
            select(MarketBreadth.trade_date, MarketBreadth.advancing, MarketBreadth.declining)
            .where(MarketBreadth.trade_date.in_(dates))
        )
        rows = {r[0]: (r[1], r[2]) for r in result.all()}
        values: list[float] = []
        for d in sorted(dates):
            adv, dec = rows.get(d, (0, 0))
            total = adv + dec
            if total > 0:
                values.append((adv - dec) / total * 100)
            else:
                values.append(0.0)
        return values

    async def compute_daily_breadth(
        self, trade_date: date,
    ) -> dict[str, Any]:
        symbols = await self._get_active_symbols()

        today_prices = await self._get_today_prices(symbols, trade_date)
        traded_symbols = list(today_prices.keys())

        prev_closes = await self._get_bulk_prev_close(traded_symbols, trade_date)

        advancing = 0
        declining = 0
        unchanged = 0
        adv_volume = 0
        dec_volume = 0
        unc_volume = 0

        for sym in traded_symbols:
            today = today_prices[sym]
            prev = prev_closes.get(sym)
            if prev is None:
                unchanged += 1
                unc_volume += today["volume"]
            elif today["close"] > prev:
                advancing += 1
                adv_volume += today["volume"]
            elif today["close"] < prev:
                declining += 1
                dec_volume += today["volume"]
            else:
                unchanged += 1
                unc_volume += today["volume"]

        total_stocks = len(traded_symbols)
        total_volume = adv_volume + dec_volume + unc_volume
        ad_ratio = round(advancing / max(declining, 1), 4)
        vol_breadth_ratio = round(
            adv_volume / max(dec_volume, 1), 4,
        ) if dec_volume > 0 else None

        high_low = await self._get_52w_high_low(traded_symbols, trade_date)
        new_highs = 0
        new_lows = 0
        for sym in traded_symbols:
            today_close = today_prices[sym]["close"]
            hl = high_low.get(sym)
            if hl is not None:
                if hl["high"] is not None and today_close >= hl["high"]:
                    new_highs += 1
                if hl["low"] is not None and today_close <= hl["low"]:
                    new_lows += 1

        prev_ad_line = await self._get_previous_ad_line(trade_date)
        net_advances = advancing - declining
        ad_line = round(prev_ad_line + net_advances, 4)

        recent_dates = await self._get_recent_breadth_dates(OSCILLATOR_PERIOD)
        recent_pcts = await self._get_net_advances_pct_for_dates(recent_dates)
        current_net_pct = (
            (net_advances / max(total_stocks, 1)) * 100
            if total_stocks > 0 else 0.0
        )
        all_pcts = recent_pcts + [current_net_pct]
        oscillator = round(sum(all_pcts) / max(len(all_pcts), 1), 4)

        index_strength = self._compute_index_strength(
            advancing=advancing, declining=declining,
            adv_volume=adv_volume, dec_volume=dec_volume,
            new_highs=new_highs, new_lows=new_lows,
            oscillator=oscillator,
        )

        return {
            "trade_date": trade_date.isoformat(),
            "advancing": advancing,
            "declining": declining,
            "unchanged": unchanged,
            "total_stocks": total_stocks,
            "advancing_volume": adv_volume,
            "declining_volume": dec_volume,
            "unchanged_volume": unc_volume,
            "total_volume": total_volume,
            "new_highs": new_highs,
            "new_lows": new_lows,
            "advance_decline_ratio": ad_ratio,
            "advance_decline_line": ad_line,
            "volume_breadth_ratio": vol_breadth_ratio,
            "breadth_oscillator": oscillator,
            "index_strength_score": round(index_strength, 4),
        }

    def _compute_index_strength(
        self, advancing: int, declining: int,
        adv_volume: int, dec_volume: int,
        new_highs: int, new_lows: int,
        oscillator: float,
    ) -> float:
        total_ad = advancing + declining
        ad_strength = (advancing / max(total_ad, 1)) * 100 if total_ad > 0 else 50.0

        total_v = adv_volume + dec_volume
        vol_strength = (adv_volume / max(total_v, 1)) * 100 if total_v > 0 else 50.0

        total_hl = new_highs + new_lows
        hl_strength = (new_highs / max(total_hl, 1)) * 100 if total_hl > 0 else 50.0

        osc_strength = 50.0 + (oscillator / 2)
        osc_strength = max(0.0, min(100.0, osc_strength))

        score = (
            ad_strength * 0.35 +
            vol_strength * 0.25 +
            hl_strength * 0.20 +
            osc_strength * 0.20
        )
        return max(0.0, min(100.0, score))

    async def compute_and_store(self, trade_date: date) -> dict[str, Any]:
        existing = await self._session.execute(
            select(MarketBreadth).where(MarketBreadth.trade_date == trade_date)
        )
        if existing.scalar_one_or_none() is not None:
            raise ValueError(f"Breadth data already exists for {trade_date}")

        breadth = await self.compute_daily_breadth(trade_date)
        db_record = await self._repo.create(
            trade_date=trade_date,
            advancing=breadth["advancing"],
            declining=breadth["declining"],
            unchanged=breadth["unchanged"],
            total_stocks=breadth["total_stocks"],
            advancing_volume=breadth["advancing_volume"],
            declining_volume=breadth["declining_volume"],
            unchanged_volume=breadth["unchanged_volume"],
            total_volume=breadth["total_volume"],
            new_highs=breadth["new_highs"],
            new_lows=breadth["new_lows"],
            advance_decline_ratio=breadth["advance_decline_ratio"],
            advance_decline_line=breadth["advance_decline_line"],
            volume_breadth_ratio=breadth["volume_breadth_ratio"],
            breadth_oscillator=breadth["breadth_oscillator"],
            index_strength_score=breadth["index_strength_score"],
        )
        breadth["id"] = db_record.id
        return breadth

    async def get_breadth_summary(self, as_of_date: date | None = None) -> dict[str, Any]:
        if as_of_date is None:
            result = await self._session.execute(
                select(MarketBreadth).order_by(MarketBreadth.trade_date.desc()).limit(1)
            )
            record = result.scalar_one_or_none()
            if record is None:
                return {}
            as_of_date = record.trade_date
        else:
            result = await self._session.execute(
                select(MarketBreadth).where(MarketBreadth.trade_date == as_of_date)
            )
            record = result.scalar_one_or_none()
            if record is None:
                return {}

        return {
            "trade_date": record.trade_date.isoformat(),
            "advancing": record.advancing,
            "declining": record.declining,
            "advance_decline_ratio": record.advance_decline_ratio,
            "advance_decline_line": record.advance_decline_line,
            "new_highs": record.new_highs,
            "new_lows": record.new_lows,
            "advancing_volume": record.advancing_volume,
            "declining_volume": record.declining_volume,
            "volume_breadth_ratio": record.volume_breadth_ratio,
            "breadth_oscillator": record.breadth_oscillator,
            "index_strength_score": record.index_strength_score,
        }

    async def get_advance_decline_line(
        self, limit: int = 100,
    ) -> list[dict[str, Any]]:
        result = await self._session.execute(
            select(MarketBreadth.trade_date, MarketBreadth.advance_decline_line)
            .order_by(MarketBreadth.trade_date.desc())
            .limit(limit)
        )
        return [
            {"trade_date": r[0].isoformat(), "advance_decline_line": r[1]}
            for r in result.all()
        ]

    async def get_oscillator_history(
        self, limit: int = 100,
    ) -> list[dict[str, Any]]:
        result = await self._session.execute(
            select(MarketBreadth.trade_date, MarketBreadth.breadth_oscillator)
            .order_by(MarketBreadth.trade_date.desc())
            .limit(limit)
        )
        return [
            {"trade_date": r[0].isoformat(), "breadth_oscillator": r[1]}
            for r in result.all()
        ]

    async def get_high_low_data(
        self, limit: int = 100,
    ) -> list[dict[str, Any]]:
        result = await self._session.execute(
            select(
                MarketBreadth.trade_date,
                MarketBreadth.new_highs,
                MarketBreadth.new_lows,
            )
            .order_by(MarketBreadth.trade_date.desc())
            .limit(limit)
        )
        return [
            {
                "trade_date": r[0].isoformat(),
                "new_highs": r[1],
                "new_lows": r[2],
            }
            for r in result.all()
        ]

    async def get_volume_breadth_data(
        self, limit: int = 100,
    ) -> list[dict[str, Any]]:
        result = await self._session.execute(
            select(
                MarketBreadth.trade_date,
                MarketBreadth.advancing_volume,
                MarketBreadth.declining_volume,
                MarketBreadth.volume_breadth_ratio,
            )
            .order_by(MarketBreadth.trade_date.desc())
            .limit(limit)
        )
        return [
            {
                "trade_date": r[0].isoformat(),
                "advancing_volume": r[1],
                "declining_volume": r[2],
                "volume_breadth_ratio": r[3],
            }
            for r in result.all()
        ]

    async def get_historical(
        self, start_date: date | None = None, end_date: date | None = None,
        skip: int = 0, limit: int = 100,
    ) -> tuple[Sequence[MarketBreadth], int]:
        stmt = select(MarketBreadth)
        if start_date:
            stmt = stmt.where(MarketBreadth.trade_date >= start_date)
        if end_date:
            stmt = stmt.where(MarketBreadth.trade_date <= end_date)

        count_result = await self._session.execute(stmt)
        total = len(count_result.scalars().all())

        stmt = stmt.order_by(MarketBreadth.trade_date.desc()).offset(skip).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all()), total

    async def delete(self, trade_date: date) -> bool:
        result = await self._session.execute(
            select(MarketBreadth).where(MarketBreadth.trade_date == trade_date)
        )
        record = result.scalar_one_or_none()
        if record is None:
            return False
        await self._session.delete(record)
        await self._session.flush()
        return True
