from collections.abc import Sequence
from datetime import date, timedelta
from typing import Any

import structlog
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.models.company import Company
from titan_x.models.price import DailyPrice
from titan_x.models.sector import SectorPerformance
from titan_x.models.market_breadth import MarketBreadth

logger = structlog.get_logger(__name__)


class MarketHeatmapService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_heatmap(
        self, as_of_date: date | None = None, period: str = "1M",
    ) -> dict[str, Any]:
        if as_of_date is None:
            as_of_date = date.today()

        sectors = await self._get_sectors()
        sector_data: list[dict[str, Any]] = []
        all_leaders: list[dict[str, Any]] = []
        all_laggards: list[dict[str, Any]] = []

        for sector in sectors:
            info = await self._build_sector_info(sector, as_of_date, period)
            sector_data.append(info["sector"])
            all_leaders.extend(info["leaders"])
            all_laggards.extend(info["laggards"])

        sector_data.sort(key=lambda s: (s.get("return_pct") or 0), reverse=True)

        breadth = await self._get_breadth(as_of_date)
        summary = self._build_summary(sector_data, breadth, all_leaders, all_laggards)

        return {
            "as_of_date": as_of_date.isoformat(),
            "period": period,
            "sectors": sector_data,
            "leaders": sorted(all_leaders, key=lambda x: (x.get("return_pct") or 0), reverse=True)[:10],
            "laggards": sorted(all_laggards, key=lambda x: (x.get("return_pct") or 0))[:10],
            "breadth": breadth,
            "summary": summary,
        }

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

    async def _get_industries_for_sector(self, sector: str) -> list[str]:
        result = await self._session.execute(
            select(Company.industry).distinct().where(
                Company.sector == sector,
                Company.industry.isnot(None),
                Company.status == "active",
            )
        )
        return [r[0] for r in result.all() if r[0]]

    async def _get_symbols_for_industry(self, sector: str, industry: str) -> list[str]:
        result = await self._session.execute(
            select(Company.symbol).where(
                Company.sector == sector,
                Company.industry == industry,
                Company.status == "active",
            )
        )
        return [r[0] for r in result.all()]

    async def _get_stock_prices(
        self, symbols: list[str], as_of_date: date, days: int,
    ) -> dict[str, dict[str, Any]]:
        if not symbols:
            return {}
        if days == 0:
            start_date = date(as_of_date.year, 1, 1)
        else:
            start_date = as_of_date - timedelta(days=days)

        rows = (await self._session.execute(
            select(DailyPrice.symbol, DailyPrice.close, DailyPrice.volume, DailyPrice.trade_date)
            .where(
                DailyPrice.symbol.in_(symbols),
                DailyPrice.trade_date <= as_of_date,
            )
            .order_by(DailyPrice.symbol, DailyPrice.trade_date.desc())
        )).all()

        latest: dict[str, tuple[float, int]] = {}
        seen: set[str] = set()
        for r in rows:
            if r.symbol not in seen:
                seen.add(r.symbol)
                latest[r.symbol] = (r.close, r.volume)

        start_prices: dict[str, float] = {}
        for sym in symbols:
            after = (await self._session.execute(
                select(DailyPrice.close, DailyPrice.trade_date)
                .where(
                    DailyPrice.symbol == sym,
                    DailyPrice.trade_date >= start_date,
                    DailyPrice.trade_date < as_of_date,
                )
                .order_by(DailyPrice.trade_date.asc())
                .limit(1)
            )).one_or_none()
            if after is not None:
                start_prices[sym] = after[0]
            else:
                before = (await self._session.execute(
                    select(DailyPrice.close)
                    .where(DailyPrice.symbol == sym, DailyPrice.trade_date < start_date)
                    .order_by(DailyPrice.trade_date.desc())
                    .limit(1)
                )).scalar_one_or_none()
                if before is not None:
                    start_prices[sym] = before

        result: dict[str, dict[str, Any]] = {}
        for sym in symbols:
            close_vol = latest.get(sym)
            sp = start_prices.get(sym)
            result[sym] = {
                "close": close_vol[0] if close_vol else None,
                "volume": close_vol[1] if close_vol else None,
                "start_price": sp,
            }
        return result

    async def _build_sector_info(
        self, sector: str, as_of_date: date, period: str,
    ) -> dict[str, Any]:
        symbols = await self._get_symbols_for_sector(sector)
        perf = await self._get_sector_performance(sector, as_of_date, period)

        industries_raw = await self._get_industries_for_sector(sector)
        industries = []
        for ind in industries_raw:
            ind_symbols = await self._get_symbols_for_industry(sector, ind)
            ind_prices = await self._get_stock_prices(ind_symbols, as_of_date, PERIOD_DAYS.get(period, 30))
            ind_returns = []
            ind_volume = 0
            for sym in ind_symbols:
                info = ind_prices.get(sym, {})
                close = info.get("close")
                sp = info.get("start_price")
                vol = info.get("volume") or 0
                ind_volume += vol
                if close and sp and sp > 0:
                    ind_returns.append((close - sp) / sp * 100)
            ind_avg = sum(ind_returns) / len(ind_returns) if ind_returns else None
            industries.append({
                "name": ind,
                "constituent_count": len(ind_symbols),
                "return_pct": round(ind_avg, 2) if ind_avg is not None else None,
                "volume": ind_volume,
            })

        days = PERIOD_DAYS.get(period, 30)
        prices = await self._get_stock_prices(symbols, as_of_date, days)

        stock_returns: list[dict[str, Any]] = []
        sector_volume = 0
        for sym in symbols:
            info = prices.get(sym, {})
            close = info.get("close")
            sp = info.get("start_price")
            vol = info.get("volume") or 0
            sector_volume += vol
            ret_pct = None
            if close and sp and sp > 0:
                ret_pct = round((close - sp) / sp * 100, 2)
            stock_returns.append({
                "symbol": sym,
                "return_pct": ret_pct,
                "close": close,
                "volume": vol,
            })

        sorted_stocks = sorted(stock_returns, key=lambda x: (x.get("return_pct") or 0) if x.get("return_pct") is not None else 0, reverse=True)
        leaders = [s for s in sorted_stocks if s["return_pct"] is not None][:5]
        laggards = [s for s in reversed(sorted_stocks) if s["return_pct"] is not None][:5]

        avg_return = None
        valid = [s["return_pct"] for s in stock_returns if s["return_pct"] is not None]
        if valid:
            avg_return = round(sum(valid) / len(valid), 2)

        return {
            "sector": {
                "name": sector,
                "return_pct": avg_return,
                "momentum_score": perf.get("momentum_score"),
                "relative_strength": perf.get("relative_strength"),
                "rank": perf.get("rank"),
                "constituent_count": len(symbols),
                "volume": sector_volume,
                "industries": industries,
            },
            "leaders": leaders,
            "laggards": laggards,
        }

    async def _get_sector_performance(
        self, sector: str, as_of_date: date, period: str,
    ) -> dict[str, Any]:
        result = await self._session.execute(
            select(SectorPerformance)
            .where(
                SectorPerformance.sector == sector,
                SectorPerformance.as_of_date <= as_of_date,
                SectorPerformance.period_label == period,
            )
            .order_by(desc(SectorPerformance.as_of_date))
            .limit(1)
        )
        sp = result.scalar_one_or_none()
        if sp is None:
            return {}
        return {
            "return_pct": sp.return_pct,
            "momentum_score": sp.momentum_score,
            "relative_strength": sp.relative_strength,
            "rank": sp.rank,
            "constituent_count": sp.constituent_count,
        }

    async def _get_breadth(self, as_of_date: date) -> dict[str, Any]:
        result = await self._session.execute(
            select(MarketBreadth)
            .where(MarketBreadth.trade_date <= as_of_date)
            .order_by(desc(MarketBreadth.trade_date))
            .limit(1)
        )
        mb = result.scalar_one_or_none()
        if mb is None:
            return {
                "advancing": None, "declining": None, "total_stocks": None,
                "advance_decline_ratio": None,
                "new_highs": None, "new_lows": None,
                "breadth_oscillator": None, "index_strength_score": None,
            }
        ad_ratio = None
        if mb.declining and mb.declining > 0:
            ad_ratio = round(mb.advancing / mb.declining, 2)
        return {
            "advancing": mb.advancing,
            "declining": mb.declining,
            "unchanged": mb.unchanged,
            "total_stocks": mb.total_stocks,
            "advance_decline_ratio": ad_ratio,
            "advancing_volume": mb.advancing_volume,
            "declining_volume": mb.declining_volume,
            "total_volume": mb.total_volume,
            "new_highs": mb.new_highs,
            "new_lows": mb.new_lows,
            "breadth_oscillator": mb.breadth_oscillator,
            "index_strength_score": mb.index_strength_score,
        }

    def _build_summary(
        self, sector_data: list[dict[str, Any]],
        breadth: dict[str, Any],
        all_leaders: list[dict[str, Any]],
        all_laggards: list[dict[str, Any]],
    ) -> dict[str, Any]:
        advancing_sectors = sum(1 for s in sector_data if (s.get("return_pct") or 0) > 0)
        declining_sectors = sum(1 for s in sector_data if (s.get("return_pct") or 0) < 0)
        total_volume = sum((s.get("volume") or 0) for s in sector_data)

        valid_returns = [s["return_pct"] for s in sector_data if s.get("return_pct") is not None]
        avg_sector_return = round(sum(valid_returns) / len(valid_returns), 2) if valid_returns else None

        best_sector = max(sector_data, key=lambda s: s.get("return_pct") or 0) if sector_data else {}
        worst_sector = min(sector_data, key=lambda s: s.get("return_pct") or 0) if sector_data else {}

        return {
            "total_sectors": len(sector_data),
            "advancing_sectors": advancing_sectors,
            "declining_sectors": declining_sectors,
            "avg_sector_return_pct": avg_sector_return,
            "total_volume": total_volume,
            "best_sector": best_sector.get("name"),
            "best_sector_return": best_sector.get("return_pct"),
            "worst_sector": worst_sector.get("name"),
            "worst_sector_return": worst_sector.get("return_pct"),
            "market_breadth": breadth.get("breadth_oscillator"),
            "index_strength": breadth.get("index_strength_score"),
        }


PERIOD_DAYS: dict[str, int] = {
    "1W": 7, "1M": 30, "3M": 90, "6M": 180,
    "YTD": 0, "1Y": 365, "3Y": 1095, "5Y": 1825,
}
