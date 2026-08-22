import json
from collections.abc import Sequence
from datetime import date, timedelta
from typing import Any

import structlog
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.db.repository import BaseRepository
from titan_x.models.company import Company
from titan_x.models.dynamic_ai_score import DynamicAIScore
from titan_x.models.fundamental import FundamentalMetric
from titan_x.models.news import NewsArticle
from titan_x.models.news_nlp import NewsNLPAnalysis
from titan_x.models.price import DailyPrice
from titan_x.models.risk import RiskMetrics
from titan_x.models.saved_screen import SavedScreen
from titan_x.models.technical import TechnicalIndicator

logger = structlog.get_logger(__name__)


class AdvancedScreenerService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._screen_repo = BaseRepository(session, SavedScreen)

    async def run_screen(
        self, filters: dict[str, Any], user_id: int | None = None,
        screen_id: int | None = None, skip: int = 0, limit: int = 50,
        as_of_date: date | None = None,
    ) -> dict[str, Any]:
        if as_of_date is not None:
            filters = dict(filters)
            for section in ("technical", "fundamental", "news", "liquidity", "ai_score"):
                if section in filters:
                    filters[section] = dict(filters[section])
                    filters[section].setdefault("as_of_date", as_of_date)

        symbol_sets: list[set[str]] = []

        if filters.get("sector") or filters.get("exchange") or filters.get("market_cap") or filters.get("status"):
            symbol_sets.append(await self._filter_companies(filters))

        if filters.get("technical"):
            symbol_sets.append(await self._filter_technical(filters["technical"]))

        if filters.get("fundamental"):
            symbol_sets.append(await self._filter_fundamental(filters["fundamental"]))

        if filters.get("news"):
            symbol_sets.append(await self._filter_news(filters["news"]))

        if filters.get("liquidity"):
            symbol_sets.append(await self._filter_liquidity(filters["liquidity"]))

        if filters.get("ai_score"):
            symbol_sets.append(await self._filter_ai_score(filters["ai_score"]))

        if not symbol_sets:
            symbol_sets = [set(await self._get_all_active_symbols())]

        matching = symbol_sets[0]
        for symbol_set in symbol_sets[1:]:
            matching &= symbol_set

        all_symbols = sorted(matching)
        total = len(all_symbols)
        page = all_symbols[skip:skip + limit]
        results = await self._build_results(page, filters, as_of_date)

        if screen_id and user_id:
            await self._update_last_run(screen_id, total)

        return {
            "total": total,
            "skip": skip,
            "limit": limit,
            "results": results,
            "filters_applied": [list(s) for s in symbol_sets],
        }

    async def _get_all_active_symbols(self) -> list[str]:
        rows = await self._session.execute(
            select(Company.symbol).where(Company.status == "active"),
        )
        return [r[0] for r in rows.all()]

    async def _filter_companies(self, filters: dict[str, Any]) -> set[str]:
        stmt = select(Company.symbol).where(Company.status == "active")

        sector = filters.get("sector")
        if sector:
            stmt = stmt.where(Company.sector.in_(sector) if isinstance(sector, list) else Company.sector == sector)

        exchange = filters.get("exchange")
        if exchange:
            stmt = stmt.where(Company.exchange == exchange)

        market_cap = filters.get("market_cap")
        if market_cap:
            mc_min = market_cap.get("min")
            mc_max = market_cap.get("max")
            if mc_min is not None:
                stmt = stmt.where(Company.market_cap >= mc_min)
            if mc_max is not None:
                stmt = stmt.where(Company.market_cap <= mc_max)

        industry = filters.get("industry")
        if industry:
            stmt = stmt.where(Company.industry.in_(industry) if isinstance(industry, list) else Company.industry == industry)

        rows = await self._session.execute(stmt)
        return {r[0] for r in rows.all()}

    async def _filter_technical(self, tech: dict[str, Any]) -> set[str]:
        as_of = tech.get("as_of_date") or date.today()
        sets: list[set[str]] = []

        # Fetch the latest RSI observation per symbol in one query. The old
        # implementation performed one additional query for every symbol.
        rsi = tech.get("rsi")
        if rsi:
            rows = await self._session.execute(
                select(TechnicalIndicator.symbol, TechnicalIndicator.trade_date, TechnicalIndicator.value)
                .where(
                    TechnicalIndicator.indicator == "rsi",
                    TechnicalIndicator.trade_date <= as_of,
                    TechnicalIndicator.value.isnot(None),
                )
                .order_by(TechnicalIndicator.symbol, desc(TechnicalIndicator.trade_date))
            )
            latest: dict[str, float] = {}
            for symbol, _trade_date, value in rows.all():
                if symbol not in latest:
                    latest[symbol] = float(value)

            rsi_min = rsi.get("min")
            rsi_max = rsi.get("max")
            sets.append({
                symbol for symbol, value in latest.items()
                if (rsi_min is None or value >= rsi_min)
                and (rsi_max is None or value <= rsi_max)
            })

        macd = tech.get("macd")
        if macd:
            rows = await self._session.execute(
                select(TechnicalIndicator.symbol, TechnicalIndicator.trade_date,
                       TechnicalIndicator.value, TechnicalIndicator.value_secondary)
                .where(
                    TechnicalIndicator.indicator == "macd",
                    TechnicalIndicator.trade_date <= as_of,
                    TechnicalIndicator.value.isnot(None),
                    TechnicalIndicator.value_secondary.isnot(None),
                )
                .order_by(TechnicalIndicator.symbol, desc(TechnicalIndicator.trade_date))
            )
            latest_macd: dict[str, tuple[float, float]] = {}
            for symbol, _trade_date, value, secondary in rows.all():
                if symbol not in latest_macd:
                    latest_macd[symbol] = (float(value), float(secondary))

            if macd == "bullish":
                sets.append({s for s, (value, signal) in latest_macd.items() if value > signal})
            elif macd == "bearish":
                sets.append({s for s, (value, signal) in latest_macd.items() if value < signal})

        # A Golden/Death Cross is an EVENT, not simply the current ordering
        # of two moving averages. We therefore need the latest two observations
        # for both periods and require their dates to match.
        sma_cross = tech.get("sma_cross")
        if sma_cross:
            fast_sma = int(sma_cross.get("fast", 20))
            slow_sma = int(sma_cross.get("slow", 50))
            cross_type = str(sma_cross.get("type", "golden")).lower()

            sma_rows = await self._session.execute(
                select(TechnicalIndicator.symbol, TechnicalIndicator.period,
                       TechnicalIndicator.trade_date, TechnicalIndicator.value)
                .where(
                    TechnicalIndicator.indicator == "sma",
                    TechnicalIndicator.period.in_([fast_sma, slow_sma]),
                    TechnicalIndicator.trade_date <= as_of,
                    TechnicalIndicator.value.isnot(None),
                )
                .order_by(TechnicalIndicator.symbol, TechnicalIndicator.period,
                          desc(TechnicalIndicator.trade_date))
            )

            observations: dict[str, dict[int, list[tuple[date, float]]]] = {}
            for symbol, period, trade_date, value in sma_rows.all():
                by_period = observations.setdefault(symbol, {})
                values = by_period.setdefault(int(period), [])
                if len(values) < 2:
                    values.append((trade_date, float(value)))

            sma_set: set[str] = set()
            if fast_sma != slow_sma and cross_type in {"golden", "death"}:
                for symbol, by_period in observations.items():
                    fast = by_period.get(fast_sma, [])
                    slow = by_period.get(slow_sma, [])
                    if len(fast) < 2 or len(slow) < 2:
                        continue

                    current_fast_date, current_fast = fast[0]
                    previous_fast_date, previous_fast = fast[1]
                    current_slow_date, current_slow = slow[0]
                    previous_slow_date, previous_slow = slow[1]

                    if current_fast_date != current_slow_date or previous_fast_date != previous_slow_date:
                        continue

                    if cross_type == "golden":
                        crossed = previous_fast <= previous_slow and current_fast > current_slow
                    else:
                        crossed = previous_fast >= previous_slow and current_fast < current_slow

                    if crossed:
                        sma_set.add(symbol)
            sets.append(sma_set)

        volume_ratio = tech.get("volume_ratio")
        if volume_ratio is not None:
            start = as_of - timedelta(days=30)
            rows = await self._session.execute(
                select(DailyPrice.symbol, DailyPrice.trade_date, DailyPrice.volume)
                .where(
                    DailyPrice.trade_date.between(start, as_of),
                    DailyPrice.volume.isnot(None),
                )
                .order_by(DailyPrice.symbol, desc(DailyPrice.trade_date))
            )
            volumes: dict[str, list[float]] = {}
            for symbol, _trade_date, volume in rows.all():
                values = volumes.setdefault(symbol, [])
                if len(values) < 22:
                    values.append(float(volume))

            vol_set: set[str] = set()
            for symbol, values in volumes.items():
                if len(values) >= 2:
                    latest_vol = values[0]
                    avg_vol = sum(values[1:]) / len(values[1:])
                    if avg_vol > 0 and latest_vol / avg_vol >= volume_ratio:
                        vol_set.add(symbol)
            sets.append(vol_set)

        if not sets:
            return set(await self._get_all_active_symbols())

        result = sets[0]
        for symbol_set in sets[1:]:
            result &= symbol_set
        return result

    async def _filter_fundamental(self, fund: dict[str, Any]) -> set[str]:
        metric_filters: dict[str, dict[str, float | None]] = {}
        if fund.get("pe_ratio") is not None:
            metric_filters["PE_RATIO"] = fund["pe_ratio"]
        if fund.get("roe") is not None:
            metric_filters["ROE"] = fund["roe"]
        if fund.get("quality_score") is not None:
            metric_filters["QUALITY_SCORE"] = fund["quality_score"]
        metric_filters.update(fund.get("custom_metrics", {}))

        if not metric_filters:
            rows = await self._session.execute(
                select(FundamentalMetric.symbol).where(FundamentalMetric.period_type == "annual").limit(1)
            )
            if rows.first():
                return set(await self._get_all_active_symbols())
            return set()

        result_set: set[str] | None = None
        for metric_name, constraint in metric_filters.items():
            constraint_min = constraint.get("min") if isinstance(constraint, dict) else None
            constraint_max = constraint.get("max") if isinstance(constraint, dict) else None

            rows = await self._session.execute(
                select(FundamentalMetric.symbol, FundamentalMetric.value)
                .where(
                    FundamentalMetric.metric_name == metric_name,
                    FundamentalMetric.period_type == "annual",
                    FundamentalMetric.value.isnot(None),
                )
                .order_by(FundamentalMetric.fiscal_year.desc())
            )

            latest_by_symbol: dict[str, float] = {}
            for symbol, value in rows.all():
                if symbol not in latest_by_symbol:
                    latest_by_symbol[symbol] = float(value)

            matching = {
                symbol for symbol, value in latest_by_symbol.items()
                if (constraint_min is None or value >= constraint_min)
                and (constraint_max is None or value <= constraint_max)
            }
            result_set = matching if result_set is None else result_set & matching

        return result_set or set()

    async def _filter_news(self, news: dict[str, Any]) -> set[str]:
        days = news.get("days", 30)
        as_of = news.get("as_of_date") or date.today()
        start = as_of - timedelta(days=days)
        sentiment = news.get("sentiment")
        min_articles = news.get("min_articles", 1)

        rows = await self._session.execute(
            select(
                NewsArticle.symbol,
                func.avg(NewsNLPAnalysis.sentiment_positive - NewsNLPAnalysis.sentiment_negative).label("net_sentiment"),
                func.count(NewsNLPAnalysis.id).label("article_count"),
            )
            .join(NewsNLPAnalysis, NewsNLPAnalysis.article_id == NewsArticle.id)
            .where(
                NewsArticle.symbol.isnot(None),
                NewsArticle.published_at.between(start, as_of),
                NewsNLPAnalysis.sentiment_positive.isnot(None),
                NewsNLPAnalysis.sentiment_negative.isnot(None),
            )
            .group_by(NewsArticle.symbol)
        )

        result_set: set[str] = set()
        for symbol, net, count in rows.all():
            if net is None or count < min_articles:
                continue
            sent_min = sentiment.get("min") if isinstance(sentiment, dict) else sentiment
            sent_max = sentiment.get("max") if isinstance(sentiment, dict) else None
            if sent_min is not None and net < sent_min:
                continue
            if sent_max is not None and net > sent_max:
                continue
            result_set.add(symbol)
        return result_set

    async def _filter_liquidity(self, liq: dict[str, Any]) -> set[str]:
        as_of = liq.get("as_of_date") or date.today()
        rows = await self._session.execute(
            select(RiskMetrics)
            .where(RiskMetrics.as_of_date <= as_of)
            .order_by(RiskMetrics.symbol, desc(RiskMetrics.as_of_date))
        )

        latest: dict[str, RiskMetrics] = {}
        for row in rows.scalars().all():
            if row.symbol not in latest:
                latest[row.symbol] = row

        result_set: set[str] = set()
        for symbol, row in latest.items():
            match = True
            avg_vol = liq.get("avg_volume_20d")
            if avg_vol is not None:
                vol_min = avg_vol.get("min") if isinstance(avg_vol, dict) else avg_vol
                if row.avg_daily_volume_20d is None or row.avg_daily_volume_20d < (vol_min or 0):
                    match = False

            dol_vol = liq.get("avg_dollar_volume_20d")
            if dol_vol is not None:
                dv_min = dol_vol.get("min") if isinstance(dol_vol, dict) else dol_vol
                if row.avg_dollar_volume_20d is None or row.avg_dollar_volume_20d < (dv_min or 0):
                    match = False

            liq_score = liq.get("liquidity_score")
            if liq_score is not None:
                ls_min = liq_score.get("min") if isinstance(liq_score, dict) else liq_score
                ls_max = liq_score.get("max") if isinstance(liq_score, dict) else None
                if row.liquidity_score is None:
                    match = False
                elif (ls_min is not None and row.liquidity_score < ls_min) or (ls_max is not None and row.liquidity_score > ls_max):
                    match = False

            if match:
                result_set.add(symbol)
        return result_set

    async def _filter_ai_score(self, ai: dict[str, Any]) -> set[str]:
        as_of = ai.get("as_of_date") or date.today()
        rows = await self._session.execute(
            select(DynamicAIScore)
            .where(DynamicAIScore.as_of_date <= as_of)
            .order_by(DynamicAIScore.symbol, desc(DynamicAIScore.as_of_date))
        )

        latest: dict[str, DynamicAIScore] = {}
        for row in rows.scalars().all():
            if row.symbol not in latest:
                latest[row.symbol] = row

        result_set: set[str] = set()
        for symbol, row in latest.items():
            combined = ai.get("combined_score")
            if combined is not None:
                cs_min = combined.get("min") if isinstance(combined, dict) else combined
                cs_max = combined.get("max") if isinstance(combined, dict) else None
                if cs_min is not None and row.combined_score < cs_min:
                    continue
                if cs_max is not None and row.combined_score > cs_max:
                    continue

            signal = ai.get("combined_signal")
            if signal and row.combined_signal != signal:
                continue

            min_conf = ai.get("min_confidence")
            if min_conf is not None and row.combined_confidence < min_conf:
                continue

            result_set.add(symbol)
        return result_set

    async def _build_results(
        self, symbols: list[str], filters: dict[str, Any],
        as_of_date: date | None = None,
    ) -> list[dict[str, Any]]:
        if not symbols:
            return []

        company_rows = await self._session.execute(select(Company).where(Company.symbol.in_(symbols)))
        companies = {c.symbol: c for c in company_rows.scalars().all()}
        now = as_of_date or date.today()

        price_rows = await self._session.execute(
            select(DailyPrice.symbol, DailyPrice.close, DailyPrice.volume, DailyPrice.trade_date)
            .where(DailyPrice.symbol.in_(symbols), DailyPrice.trade_date <= now)
            .order_by(DailyPrice.symbol, desc(DailyPrice.trade_date))
        )
        prices: dict[str, dict[str, Any]] = {}
        for symbol, close, volume, trade_date in price_rows.all():
            if symbol not in prices:
                prices[symbol] = {"close": close, "volume": volume, "trade_date": trade_date}

        prev_rows = await self._session.execute(
            select(DailyPrice.symbol, DailyPrice.close, DailyPrice.trade_date)
            .where(DailyPrice.symbol.in_(symbols), DailyPrice.trade_date <= now - timedelta(days=30))
            .order_by(DailyPrice.symbol, desc(DailyPrice.trade_date))
        )
        prev_prices: dict[str, float] = {}
        for symbol, close, _trade_date in prev_rows.all():
            if symbol not in prev_prices:
                prev_prices[symbol] = close

        results = []
        for symbol in symbols:
            company = companies.get(symbol)
            price = prices.get(symbol, {})
            close = price.get("close")
            prev_close = prev_prices.get(symbol)
            change_pct = round((close - prev_close) / prev_close * 100, 2) if close and prev_close and prev_close > 0 else None
            results.append({
                "symbol": symbol,
                "company_name": company.company_name if company else None,
                "sector": company.sector if company else None,
                "industry": company.industry if company else None,
                "exchange": company.exchange if company else None,
                "market_cap": company.market_cap if company else None,
                "close": close,
                "volume": price.get("volume"),
                "change_1m_pct": change_pct,
                "as_of_date": price.get("trade_date"),
            })
        return results

    async def _update_last_run(self, screen_id: int, count: int) -> None:
        result = await self._session.execute(select(SavedScreen).where(SavedScreen.id == screen_id))
        screen = result.scalar_one_or_none()
        if screen:
            screen.last_run_at = func.now()
            screen.last_results_count = count
            await self._session.flush()

    async def save_screen(self, user_id: int, name: str, filters_json: str, description: str | None = None) -> SavedScreen:
        return await self._screen_repo.create(
            user_id=user_id, name=name, description=description, filters_json=filters_json,
        )

    async def update_screen(
        self, screen_id: int, user_id: int,
        name: str | None = None, description: str | None = None,
        filters_json: str | None = None,
    ) -> SavedScreen | None:
        result = await self._session.execute(select(SavedScreen).where(SavedScreen.id == screen_id, SavedScreen.user_id == user_id))
        screen = result.scalar_one_or_none()
        if screen is None:
            return None
        if name is not None:
            screen.name = name
        if description is not None:
            screen.description = description
        if filters_json is not None:
            screen.filters_json = filters_json
        await self._session.flush()
        return screen

    async def delete_screen(self, screen_id: int, user_id: int) -> bool:
        result = await self._session.execute(select(SavedScreen).where(SavedScreen.id == screen_id, SavedScreen.user_id == user_id))
        screen = result.scalar_one_or_none()
        if screen is None:
            return False
        await self._session.delete(screen)
        await self._session.flush()
        return True

    async def get_screen(self, screen_id: int, user_id: int) -> SavedScreen | None:
        result = await self._session.execute(select(SavedScreen).where(SavedScreen.id == screen_id, SavedScreen.user_id == user_id))
        return result.scalar_one_or_none()

    async def list_screens(self, user_id: int, skip: int = 0, limit: int = 20) -> tuple[Sequence[SavedScreen], int]:
        stmt = select(SavedScreen).where(SavedScreen.user_id == user_id).order_by(desc(SavedScreen.updated_at)).offset(skip).limit(limit)
        count_stmt = select(func.count()).select_from(SavedScreen).where(SavedScreen.user_id == user_id)
        total_result = await self._session.execute(count_stmt)
        result = await self._session.execute(stmt)
        return list(result.scalars().all()), total_result.scalar_one()

    async def run_saved_screen(self, screen_id: int, user_id: int, skip: int = 0, limit: int = 50) -> dict[str, Any] | None:
        screen = await self.get_screen(screen_id, user_id)
        if screen is None:
            return None
        filters = json.loads(screen.filters_json)
        return await self.run_screen(filters, user_id, screen_id, skip, limit)
