import json
from collections.abc import Sequence
from datetime import date, timedelta
from typing import Any

import structlog
from sqlalchemy import and_, desc, func, or_, select, text
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
                if section in filters and as_of_date is not None:
                    filters[section] = dict(filters[section])
                    filters[section].setdefault("as_of_date", as_of_date)

        symbol_sets: list[set[str]] = []

        if filters.get("sector") or filters.get("exchange") or filters.get("market_cap") or filters.get("status"):
            company_set = await self._filter_companies(filters)
            symbol_sets.append(company_set)

        if filters.get("technical"):
            tech_set = await self._filter_technical(filters["technical"])
            symbol_sets.append(tech_set)

        if filters.get("fundamental"):
            fund_set = await self._filter_fundamental(filters["fundamental"])
            symbol_sets.append(fund_set)

        if filters.get("news"):
            news_set = await self._filter_news(filters["news"])
            symbol_sets.append(news_set)

        if filters.get("liquidity"):
            liq_set = await self._filter_liquidity(filters["liquidity"])
            symbol_sets.append(liq_set)

        if filters.get("ai_score"):
            ai_set = await self._filter_ai_score(filters["ai_score"])
            symbol_sets.append(ai_set)

        if not symbol_sets:
            all_syms = await self._get_all_active_symbols()
            symbol_sets = [set(all_syms)]

        matching = symbol_sets[0]
        for s in symbol_sets[1:]:
            matching = matching & s

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
            if isinstance(sector, list):
                stmt = stmt.where(Company.sector.in_(sector))
            else:
                stmt = stmt.where(Company.sector == sector)

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
            if isinstance(industry, list):
                stmt = stmt.where(Company.industry.in_(industry))
            else:
                stmt = stmt.where(Company.industry == industry)

        rows = await self._session.execute(stmt)
        return {r[0] for r in rows.all()}

    async def _filter_technical(self, tech: dict[str, Any]) -> set[str]:
        as_of = tech.get("as_of_date")
        if as_of is None:
            as_of = date.today()

        sets: list[set[str]] = []

        rsi = tech.get("rsi")
        if rsi:
            rows = await self._session.execute(
                select(TechnicalIndicator.symbol)
                .where(
                    TechnicalIndicator.indicator == "rsi",
                    TechnicalIndicator.trade_date <= as_of,
                    TechnicalIndicator.value.isnot(None),
                )
                .order_by(TechnicalIndicator.symbol, desc(TechnicalIndicator.trade_date))
                .distinct(TechnicalIndicator.symbol)
            )
            rsi_set: set[str] = set()
            for r in rows.all():
                sym = r[0]
                val_row = await self._session.execute(
                    select(TechnicalIndicator.value)
                    .where(
                        TechnicalIndicator.symbol == sym,
                        TechnicalIndicator.indicator == "rsi",
                        TechnicalIndicator.trade_date <= as_of,
                        TechnicalIndicator.value.isnot(None),
                    )
                    .order_by(desc(TechnicalIndicator.trade_date))
                    .limit(1)
                )
                val = val_row.scalar_one_or_none()
                if val is not None:
                    rsi_min = rsi.get("min")
                    rsi_max = rsi.get("max")
                    if (rsi_min is None or val >= rsi_min) and (rsi_max is None or val <= rsi_max):
                        rsi_set.add(sym)
            sets.append(rsi_set)

        macd = tech.get("macd")
        if macd:
            rows = await self._session.execute(
                select(TechnicalIndicator.symbol, TechnicalIndicator.value, TechnicalIndicator.value_secondary)
                .where(
                    TechnicalIndicator.indicator == "macd",
                    TechnicalIndicator.trade_date <= as_of,
                    TechnicalIndicator.value.isnot(None),
                    TechnicalIndicator.value_secondary.isnot(None),
                )
                .order_by(TechnicalIndicator.symbol, desc(TechnicalIndicator.trade_date))
                .distinct(TechnicalIndicator.symbol)
            )
            macd_set: set[str] = set()
            for r in rows.all():
                if macd == "bullish" and r[1] > r[2]:
                    macd_set.add(r[0])
                elif macd == "bearish" and r[1] < r[2]:
                    macd_set.add(r[0])
            sets.append(macd_set)

        sma_cross = tech.get("sma_cross")
        if sma_cross:
            fast_sma = sma_cross.get("fast", 20)
            slow_sma = sma_cross.get("slow", 50)
            cross_type = sma_cross.get("type", "golden")  # golden or death

            fast_rows = await self._session.execute(
                select(TechnicalIndicator.symbol, TechnicalIndicator.value)
                .where(
                    TechnicalIndicator.indicator == "sma",
                    TechnicalIndicator.period == fast_sma,
                    TechnicalIndicator.trade_date <= as_of,
                    TechnicalIndicator.value.isnot(None),
                )
                .order_by(TechnicalIndicator.symbol, desc(TechnicalIndicator.trade_date))
                .distinct(TechnicalIndicator.symbol)
            )
            fast_vals = {r[0]: r[1] for r in fast_rows.all()}

            slow_rows = await self._session.execute(
                select(TechnicalIndicator.symbol, TechnicalIndicator.value)
                .where(
                    TechnicalIndicator.indicator == "sma",
                    TechnicalIndicator.period == slow_sma,
                    TechnicalIndicator.trade_date <= as_of,
                    TechnicalIndicator.value.isnot(None),
                )
                .order_by(TechnicalIndicator.symbol, desc(TechnicalIndicator.trade_date))
                .distinct(TechnicalIndicator.symbol)
            )
            slow_vals = {r[0]: r[1] for r in slow_rows.all()}

            sma_set: set[str] = set()
            for sym in set(fast_vals.keys()) & set(slow_vals.keys()):
                if cross_type == "golden" and fast_vals[sym] > slow_vals[sym]:
                    sma_set.add(sym)
                elif cross_type == "death" and fast_vals[sym] < slow_vals[sym]:
                    sma_set.add(sym)
            sets.append(sma_set)

        volume_ratio = tech.get("volume_ratio")
        if volume_ratio is not None:
            start = as_of - timedelta(days=30)
            vol_set: set[str] = set()

            all_syms = await self._get_all_active_symbols()
            for sym in all_syms:
                prices = (await self._session.execute(
                    select(DailyPrice.volume)
                    .where(
                        DailyPrice.symbol == sym,
                        DailyPrice.trade_date.between(start, as_of),
                    )
                    .order_by(desc(DailyPrice.trade_date))
                    .limit(22)
                )).scalars().all()

                if len(prices) >= 2:
                    latest_vol = prices[0] or 0
                    avg_vol = sum(prices[1:]) / len(prices[1:]) if len(prices) > 1 else latest_vol
                    if avg_vol > 0 and (latest_vol / avg_vol) >= volume_ratio:
                        vol_set.add(sym)
            sets.append(vol_set)

        if not sets:
            rows = await self._session.execute(
                select(TechnicalIndicator.symbol).where(
                    TechnicalIndicator.trade_date <= as_of,
                ).limit(1)
            )
            if rows.first():
                return {r[0] for r in (await self._session.execute(select(Company.symbol).where(Company.status == "active"))).all()}
            return set()

        result = sets[0]
        for s in sets[1:]:
            result = result & s
        return result

    async def _filter_fundamental(self, fund: dict[str, Any]) -> set[str]:
        metric_filters: dict[str, dict[str, float | None]] = {}

        pe = fund.get("pe_ratio")
        if pe is not None:
            metric_filters["PE_RATIO"] = pe

        roe = fund.get("roe")
        if roe is not None:
            metric_filters["ROE"] = roe

        quality = fund.get("quality_score")
        if quality is not None:
            metric_filters["QUALITY_SCORE"] = quality

        metric_filters.update(fund.get("custom_metrics", {}))

        if not metric_filters:
            rows = await self._session.execute(
                select(FundamentalMetric.symbol).where(FundamentalMetric.period_type == "annual").limit(1)
            )
            if rows.first():
                return {r[0] for r in (await self._session.execute(select(Company.symbol).where(Company.status == "active"))).all()}
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
                .distinct(FundamentalMetric.symbol)
            )

            matching = set()
            for r in rows.all():
                v = r[1]
                if v is not None:
                    if (constraint_min is None or v >= constraint_min) and (constraint_max is None or v <= constraint_max):
                        matching.add(r[0])

            if result_set is None:
                result_set = matching
            else:
                result_set = result_set & matching

        return result_set or set()

    async def _filter_news(self, news: dict[str, Any]) -> set[str]:
        days = news.get("days", 30)
        as_of = news.get("as_of_date")
        if as_of is None:
            as_of = date.today()
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
        for r in rows.all():
            sym = r[0]
            net = r[1]
            count = r[2]
            if net is None:
                continue
            if count < min_articles:
                continue
            if sentiment is not None:
                sent_min = sentiment.get("min") if isinstance(sentiment, dict) else sentiment
                sent_max = sentiment.get("max") if isinstance(sentiment, dict) else None
                if sent_min is not None and (net if isinstance(net, float) else 0) < sent_min:
                    continue
                if sent_max is not None and (net if isinstance(net, float) else 0) > sent_max:
                    continue
            result_set.add(sym)
        return result_set

    async def _filter_liquidity(self, liq: dict[str, Any]) -> set[str]:
        as_of = liq.get("as_of_date")
        if as_of is None:
            as_of = date.today()

        rows = await self._session.execute(
            select(RiskMetrics)
            .where(
                RiskMetrics.as_of_date <= as_of,
            )
            .order_by(RiskMetrics.symbol, desc(RiskMetrics.as_of_date))
            .distinct(RiskMetrics.symbol)
        )

        result_set: set[str] = set()
        for r in rows.scalars().all():
            match = True
            avg_vol = liq.get("avg_volume_20d")
            if avg_vol is not None:
                vol_min = avg_vol.get("min") if isinstance(avg_vol, dict) else avg_vol
                if r.avg_daily_volume_20d is None or r.avg_daily_volume_20d < (vol_min or 0):
                    match = False

            dol_vol = liq.get("avg_dollar_volume_20d")
            if dol_vol is not None:
                dv_min = dol_vol.get("min") if isinstance(dol_vol, dict) else dol_vol
                if r.avg_dollar_volume_20d is None or r.avg_dollar_volume_20d < (dv_min or 0):
                    match = False

            liq_score = liq.get("liquidity_score")
            if liq_score is not None:
                ls_min = liq_score.get("min") if isinstance(liq_score, dict) else liq_score
                ls_max = liq_score.get("max") if isinstance(liq_score, dict) else None
                if r.liquidity_score is None:
                    match = False
                else:
                    if ls_min is not None and r.liquidity_score < ls_min:
                        match = False
                    if ls_max is not None and r.liquidity_score > ls_max:
                        match = False

            if match:
                result_set.add(r.symbol)
        return result_set

    async def _filter_ai_score(self, ai: dict[str, Any]) -> set[str]:
        as_of = ai.get("as_of_date")
        if as_of is None:
            as_of = date.today()

        rows = await self._session.execute(
            select(DynamicAIScore)
            .where(DynamicAIScore.as_of_date <= as_of)
            .order_by(DynamicAIScore.symbol, desc(DynamicAIScore.as_of_date))
            .distinct(DynamicAIScore.symbol)
        )

        result_set: set[str] = set()
        for r in rows.scalars().all():
            match = True

            combined = ai.get("combined_score")
            if combined is not None:
                cs_min = combined.get("min") if isinstance(combined, dict) else combined
                cs_max = combined.get("max") if isinstance(combined, dict) else None
                if cs_min is not None and r.combined_score < cs_min:
                    match = False
                if cs_max is not None and r.combined_score > cs_max:
                    match = False

            signal = ai.get("combined_signal")
            if signal and r.combined_signal != signal:
                match = False

            min_conf = ai.get("min_confidence")
            if min_conf is not None and r.combined_confidence < min_conf:
                match = False

            if match:
                result_set.add(r.symbol)
        return result_set

    async def _build_results(
        self, symbols: list[str], filters: dict[str, Any],
        as_of_date: date | None = None,
    ) -> list[dict[str, Any]]:
        if not symbols:
            return []

        company_rows = await self._session.execute(
            select(Company).where(Company.symbol.in_(symbols))
        )
        companies = {c.symbol: c for c in company_rows.scalars().all()}

        now = as_of_date or date.today()
        price_rows = await self._session.execute(
            select(DailyPrice.symbol, DailyPrice.close, DailyPrice.volume, DailyPrice.trade_date)
            .where(
                DailyPrice.symbol.in_(symbols),
                DailyPrice.trade_date <= now,
            )
            .order_by(DailyPrice.symbol, desc(DailyPrice.trade_date))
            .distinct(DailyPrice.symbol)
        )
        prices = {r[0]: {"close": r[1], "volume": r[2], "trade_date": r[3]} for r in price_rows.all()}

        prev_rows = await self._session.execute(
            select(DailyPrice.symbol, DailyPrice.close, DailyPrice.trade_date)
            .where(
                DailyPrice.symbol.in_(symbols),
                DailyPrice.trade_date <= now - timedelta(days=30),
            )
            .order_by(DailyPrice.symbol, desc(DailyPrice.trade_date))
            .distinct(DailyPrice.symbol)
        )
        prev_prices = {r[0]: r[1] for r in prev_rows.all()}

        results = []
        for sym in symbols:
            company = companies.get(sym)
            price = prices.get(sym, {})
            prev_close = prev_prices.get(sym)
            close = price.get("close")
            change_pct = None
            if close and prev_close and prev_close > 0:
                change_pct = round((close - prev_close) / prev_close * 100, 2)

            results.append({
                "symbol": sym,
                "company_name": company.company_name if company else None,
                "sector": company.sector if company else None,
                "industry": company.industry if company else None,
                "exchange": company.exchange if company else None,
                "market_cap": company.market_cap if company else None,
                "close": close,
                "volume": price.get("volume"),
                "change_1m_pct": change_pct,
            })

        return results

    async def _update_last_run(self, screen_id: int, count: int) -> None:
        await self._session.execute(
            select(SavedScreen).where(SavedScreen.id == screen_id)
        )
        stmt = (
            select(SavedScreen).where(SavedScreen.id == screen_id)
        )
        result = await self._session.execute(stmt)
        screen = result.scalar_one_or_none()
        if screen:
            screen.last_run_at = func.now()
            screen.last_results_count = count
            await self._session.flush()

    async def save_screen(
        self, user_id: int, name: str,
        filters_json: str, description: str | None = None,
    ) -> SavedScreen:
        screen = await self._screen_repo.create(
            user_id=user_id, name=name,
            description=description, filters_json=filters_json,
        )
        return screen

    async def update_screen(
        self, screen_id: int, user_id: int,
        name: str | None = None, description: str | None = None,
        filters_json: str | None = None,
    ) -> SavedScreen | None:
        stmt = select(SavedScreen).where(
            SavedScreen.id == screen_id, SavedScreen.user_id == user_id,
        )
        result = await self._session.execute(stmt)
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
        stmt = select(SavedScreen).where(
            SavedScreen.id == screen_id, SavedScreen.user_id == user_id,
        )
        result = await self._session.execute(stmt)
        screen = result.scalar_one_or_none()
        if screen is None:
            return False
        await self._session.delete(screen)
        await self._session.flush()
        return True

    async def get_screen(self, screen_id: int, user_id: int) -> SavedScreen | None:
        stmt = select(SavedScreen).where(
            SavedScreen.id == screen_id, SavedScreen.user_id == user_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_screens(
        self, user_id: int, skip: int = 0, limit: int = 20,
    ) -> tuple[Sequence[SavedScreen], int]:
        stmt = select(SavedScreen).where(SavedScreen.user_id == user_id).order_by(desc(SavedScreen.updated_at))
        count_stmt = select(func.count()).select_from(SavedScreen).where(SavedScreen.user_id == user_id)
        total_result = await self._session.execute(count_stmt)
        total = total_result.scalar_one()
        stmt = stmt.offset(skip).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all()), total

    async def run_saved_screen(
        self, screen_id: int, user_id: int,
        skip: int = 0, limit: int = 50,
    ) -> dict[str, Any] | None:
        screen = await self.get_screen(screen_id, user_id)
        if screen is None:
            return None
        filters = json.loads(screen.filters_json)
        return await self.run_screen(filters, user_id, screen_id, skip, limit)
