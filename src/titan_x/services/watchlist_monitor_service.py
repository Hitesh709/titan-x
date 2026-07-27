from collections.abc import Sequence
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
import json

import structlog
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.db.repository import BaseRepository
from titan_x.models.watchlist import Watchlist, WatchlistItem, WatchlistMonitorEvent
from titan_x.models.dynamic_ai_score import DynamicAIScore
from titan_x.models.news import NewsArticle
from titan_x.models.news_nlp import NewsNLPAnalysis
from titan_x.models.technical import TechnicalIndicator
from titan_x.models.chart_pattern import ChartPattern
from titan_x.models.financial_analysis import QuarterlyResult
from titan_x.models.risk import RiskMetrics
from titan_x.models.company import Company

logger = structlog.get_logger(__name__)

AI_SCORE_SIGNAL_CHANGE = "ai_score_change"
NEWS_EVENT = "news"
TECHNICAL_BREAKOUT = "technical_breakout"
EARNINGS = "earnings"
RISK_EVENT = "risk_event"


class WatchlistMonitorService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._watchlist_repo = BaseRepository(session, Watchlist)
        self._item_repo = BaseRepository(session, WatchlistItem)
        self._event_repo = BaseRepository(session, WatchlistMonitorEvent)

    # ── Main entry points ──

    async def check_watchlist(
        self, watchlist_id: int, user_id: int,
    ) -> list[WatchlistMonitorEvent]:
        wl = await self._session.get(Watchlist, watchlist_id)
        if wl is None or wl.user_id != user_id:
            return []
        items = (await self._session.execute(
            select(WatchlistItem).where(WatchlistItem.watchlist_id == watchlist_id)
        )).scalars().all()
        symbols = [item.symbol for item in items]
        return await self._check_symbols(symbols, user_id, watchlist_id)

    async def check_all_watchlists(self, user_id: int) -> list[WatchlistMonitorEvent]:
        wls = (await self._session.execute(
            select(Watchlist).where(Watchlist.user_id == user_id)
        )).scalars().all()
        all_events = []
        for wl in wls:
            items = (await self._session.execute(
                select(WatchlistItem).where(WatchlistItem.watchlist_id == wl.id)
            )).scalars().all()
            symbols = [item.symbol for item in items]
            events = await self._check_symbols(symbols, user_id, wl.id)
            all_events.extend(events)
        return all_events

    async def _check_symbols(
        self, symbols: list[str], user_id: int, watchlist_id: int,
    ) -> list[WatchlistMonitorEvent]:
        all_events = []
        for symbol in symbols:
            events = await self._check_symbol(symbol, user_id, watchlist_id)
            all_events.extend(events)
        return all_events

    async def _check_symbol(
        self, symbol: str, user_id: int, watchlist_id: int,
    ) -> list[WatchlistMonitorEvent]:
        events = []
        ai_event = await self._check_ai_score_change(symbol, user_id, watchlist_id)
        if ai_event:
            events.append(ai_event)
        news_events = await self._check_news(symbol, user_id, watchlist_id)
        events.extend(news_events)
        breakout_event = await self._check_technical_breakout(symbol, user_id, watchlist_id)
        if breakout_event:
            events.append(breakout_event)
        earnings_event = await self._check_earnings(symbol, user_id, watchlist_id)
        if earnings_event:
            events.append(earnings_event)
        risk_event = await self._check_risk_events(symbol, user_id, watchlist_id)
        if risk_event:
            events.append(risk_event)
        return events

    # ── AI Score Changes ──

    async def _check_ai_score_change(
        self, symbol: str, user_id: int, watchlist_id: int,
    ) -> WatchlistMonitorEvent | None:
        scores = (await self._session.execute(
            select(DynamicAIScore)
            .where(DynamicAIScore.symbol == symbol)
            .order_by(DynamicAIScore.as_of_date.desc())
            .limit(2)
        )).scalars().all()
        if len(scores) < 2:
            return None
        latest, previous = scores[0], scores[1]
        if latest.combined_signal != previous.combined_signal:
            change_pct = 0.0
            if previous.combined_score:
                change_pct = round((latest.combined_score - previous.combined_score) / previous.combined_score * 100, 2)
            return await self._create_event(
                user_id=user_id,
                watchlist_id=watchlist_id,
                symbol=symbol,
                event_type=AI_SCORE_SIGNAL_CHANGE,
                severity="warning",
                title=f"AI Score signal changed for {symbol}",
                message=f"Signal changed from {previous.combined_signal} to {latest.combined_signal}",
                previous_value=previous.combined_signal,
                current_value=latest.combined_signal,
                change_pct=change_pct,
            )
        return None

    # ── News ──

    async def _check_news(
        self, symbol: str, user_id: int, watchlist_id: int,
    ) -> list[WatchlistMonitorEvent]:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        articles = (await self._session.execute(
            select(NewsArticle)
            .where(NewsArticle.symbol == symbol, NewsArticle.published_at >= cutoff)
            .order_by(NewsArticle.published_at.desc())
            .limit(10)
        )).scalars().all()
        events = []
        for article in articles:
            nlp = (await self._session.execute(
                select(NewsNLPAnalysis).where(NewsNLPAnalysis.article_id == article.id)
            )).scalar_one_or_none()
            sentiment = nlp.sentiment_label if nlp else "neutral"
            if sentiment in ("positive", "negative"):
                events.append(await self._create_event(
                    user_id=user_id,
                    watchlist_id=watchlist_id,
                    symbol=symbol,
                    event_type=NEWS_EVENT,
                    severity="info" if sentiment == "positive" else "warning",
                    title=f"{sentiment.title()} news for {symbol}",
                    message=article.title[:200],
                    current_value=sentiment,
                    data_json=json.dumps({"article_id": article.id, "sentiment_confidence": nlp.sentiment_confidence if nlp else None}),
                ))
        return events

    # ── Technical Breakouts ──

    async def _check_technical_breakout(
        self, symbol: str, user_id: int, watchlist_id: int,
    ) -> WatchlistMonitorEvent | None:
        cutoff = date.today() - timedelta(days=7)
        patterns = (await self._session.execute(
            select(ChartPattern)
            .where(
                ChartPattern.symbol == symbol,
                ChartPattern.is_active == True,
                ChartPattern.end_date >= cutoff,
            )
            .order_by(ChartPattern.end_date.desc())
            .limit(5)
        )).scalars().all()
        if not patterns:
            return None
        best = max(patterns, key=lambda p: p.confidence_score or 0)
        if best.confidence_score and best.confidence_score >= 0.6:
            return await self._create_event(
                user_id=user_id,
                watchlist_id=watchlist_id,
                symbol=symbol,
                event_type=TECHNICAL_BREAKOUT,
                severity="warning",
                title=f"{best.pattern_type} breakout for {symbol}",
                message=f"{best.direction} {best.pattern_type} detected with {best.confidence_score:.0%} confidence",
                current_value=best.pattern_type,
                change_pct=best.confidence_score,
            )
        return None

    # ── Earnings ──

    async def _check_earnings(
        self, symbol: str, user_id: int, watchlist_id: int,
    ) -> WatchlistMonitorEvent | None:
        cutoff = date.today() - timedelta(days=90)
        results = (await self._session.execute(
            select(QuarterlyResult)
            .where(QuarterlyResult.symbol == symbol, QuarterlyResult.filing_date >= cutoff)
            .order_by(QuarterlyResult.filing_date.desc())
            .limit(1)
        )).scalars().all()
        if not results:
            return None
        result = results[0]
        if result.eps_yoy_growth is not None and abs(result.eps_yoy_growth) >= 20:
            direction = "positive" if result.eps_yoy_growth > 0 else "negative"
            return await self._create_event(
                user_id=user_id,
                watchlist_id=watchlist_id,
                symbol=symbol,
                event_type=EARNINGS,
                severity="info" if result.eps_yoy_growth > 0 else "critical",
                title=f"{direction.title()} earnings for {symbol}",
                message=f"EPS grew {result.eps_yoy_growth:.1f}% YoY in Q{result.quarter} FY{result.fiscal_year}",
                previous_value=f"Q{result.quarter} FY{result.fiscal_year}",
                current_value=f"{result.eps_yoy_growth:+.1f}%",
                change_pct=result.eps_yoy_growth,
            )
        return None

    # ── Risk Events ──

    async def _check_risk_events(
        self, symbol: str, user_id: int, watchlist_id: int,
    ) -> WatchlistMonitorEvent | None:
        cutoff = date.today() - timedelta(days=7)
        risk = (await self._session.execute(
            select(RiskMetrics)
            .where(RiskMetrics.symbol == symbol, RiskMetrics.as_of_date >= cutoff)
            .order_by(RiskMetrics.as_of_date.desc())
            .limit(1)
        )).scalar_one_or_none()
        if risk is None:
            return None
        _SEVERITY_MAP = {"info": 0, "warning": 1, "critical": 2}
        _SEVERITY_REV = {0: "info", 1: "warning", 2: "critical"}
        reasons = []
        severity = "info"
        if risk.composite_risk_score and risk.composite_risk_score >= 0.7:
            reasons.append(f"Composite risk score: {risk.composite_risk_score:.2f}")
            severity = "critical"
        if risk.volatility_20d and risk.volatility_20d >= 0.05:
            reasons.append(f"20-day volatility: {risk.volatility_20d:.1%}")
            severity = _SEVERITY_REV[max(_SEVERITY_MAP[severity], _SEVERITY_MAP["warning"])]
        if risk.event_risk_score and risk.event_risk_score >= 0.6:
            reasons.append(f"Event risk: {risk.event_risk_score:.2f}")
            severity = _SEVERITY_REV[max(_SEVERITY_MAP[severity], _SEVERITY_MAP["warning"])]
        if not reasons:
            return None
        return await self._create_event(
            user_id=user_id,
            watchlist_id=watchlist_id,
            symbol=symbol,
            event_type=RISK_EVENT,
            severity=severity,
            title=f"Risk alert for {symbol}",
            message="; ".join(reasons),
            current_value=risk.risk_rating or "high",
            change_pct=risk.composite_risk_score,
        )

    # ── Event helpers ──

    async def _create_event(
        self, user_id: int, watchlist_id: int, symbol: str,
        event_type: str, severity: str, title: str, message: str,
        previous_value: str | None = None, current_value: str | None = None,
        change_pct: float | None = None, data_json: str | None = None,
    ) -> WatchlistMonitorEvent:
        return await self._event_repo.create(
            user_id=user_id,
            watchlist_id=watchlist_id,
            symbol=symbol,
            event_type=event_type,
            severity=severity,
            title=title,
            message=message,
            previous_value=previous_value,
            current_value=current_value,
            change_pct=change_pct,
            data_json=data_json,
        )

    # ── Query ──

    async def list_events(
        self, user_id: int, event_type: str | None = None,
        symbol: str | None = None, severity: str | None = None,
        is_read: bool | None = None, skip: int = 0, limit: int = 50,
    ) -> tuple[Sequence[WatchlistMonitorEvent], int]:
        stmt = select(WatchlistMonitorEvent).where(WatchlistMonitorEvent.user_id == user_id)
        count_stmt = select(func.count()).select_from(WatchlistMonitorEvent).where(WatchlistMonitorEvent.user_id == user_id)
        if event_type:
            stmt = stmt.where(WatchlistMonitorEvent.event_type == event_type)
            count_stmt = count_stmt.where(WatchlistMonitorEvent.event_type == event_type)
        if symbol:
            stmt = stmt.where(WatchlistMonitorEvent.symbol == symbol.upper())
            count_stmt = count_stmt.where(WatchlistMonitorEvent.symbol == symbol.upper())
        if severity:
            stmt = stmt.where(WatchlistMonitorEvent.severity == severity)
            count_stmt = count_stmt.where(WatchlistMonitorEvent.severity == severity)
        if is_read is not None:
            stmt = stmt.where(WatchlistMonitorEvent.is_read == is_read)
            count_stmt = count_stmt.where(WatchlistMonitorEvent.is_read == is_read)
        total = (await self._session.execute(count_stmt)).scalar() or 0
        stmt = stmt.order_by(desc(WatchlistMonitorEvent.triggered_at)).offset(skip).limit(limit)
        rows = (await self._session.execute(stmt)).scalars().all()
        return list(rows), total

    async def mark_read(self, event_id: int, user_id: int) -> bool:
        event = await self._event_repo.get(event_id)
        if event is None or event.user_id != user_id:
            return False
        event.is_read = True
        await self._session.flush()
        return True

    async def get_event_stats(self, user_id: int) -> dict[str, Any]:
        total_stmt = select(func.count()).select_from(WatchlistMonitorEvent).where(WatchlistMonitorEvent.user_id == user_id)
        unread_stmt = select(func.count()).select_from(WatchlistMonitorEvent).where(
            WatchlistMonitorEvent.user_id == user_id, WatchlistMonitorEvent.is_read == False,
        )
        total = (await self._session.execute(total_stmt)).scalar() or 0
        unread = (await self._session.execute(unread_stmt)).scalar() or 0
        return {"total_events": total, "unread_events": unread}
