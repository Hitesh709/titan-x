from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from titan_x.db.repository import BaseRepository
from titan_x.models.dynamic_ai_score import DynamicAIScore
from titan_x.models.news import NewsArticle
from titan_x.models.news_nlp import NewsNLPAnalysis
from titan_x.models.paper_trading import PaperAccount, PaperPosition
from titan_x.models.performance_snapshot import PerformanceSnapshot
from titan_x.models.watchlist import Watchlist, WatchlistItem, WatchlistMonitorEvent
from titan_x.services.paper_analytics_service import PaperAnalyticsService

logger = structlog.get_logger(__name__)


class DashboardService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_dashboard(self, user_id: int) -> dict[str, Any]:
        portfolio = await self._get_portfolio_summary(user_id)
        watchlists = await self._get_watchlists(user_id)
        ai_picks = await self._get_ai_picks(user_id)
        news = await self._get_recent_news(user_id)
        performance = await self._get_performance(user_id)
        alerts = await self._get_recent_alerts(user_id)
        return {
            "portfolio": portfolio,
            "watchlists": watchlists,
            "ai_picks": ai_picks,
            "news": news,
            "performance": performance,
            "alerts": alerts,
        }

    async def _get_portfolio_summary(self, user_id: int) -> dict[str, Any]:
        account = (await self._session.execute(
            select(PaperAccount).where(PaperAccount.user_id == user_id)
        )).scalar_one_or_none()
        if account is None:
            return {"has_account": False}
        positions = (await self._session.execute(
            select(PaperPosition).where(PaperPosition.account_id == account.id)
        )).scalars().all()
        positions_value = Decimal("0")
        unrealized_pnl = Decimal("0")
        positions_list = []
        for p in positions:
            mkt_val = Decimal("0")
            if p.current_price and p.quantity:
                mkt_val = p.current_price * p.quantity
                positions_value += mkt_val
                unrealized_pnl += mkt_val - p.cost_basis
            positions_list.append({
                "symbol": p.symbol,
                "quantity": p.quantity,
                "avg_price": float(p.average_price),
                "current_price": float(p.current_price) if p.current_price else None,
                "cost_basis": float(p.cost_basis),
                "market_value": float(mkt_val),
                "unrealized_pnl": float(p.current_price * p.quantity - p.cost_basis) if p.current_price and p.quantity else 0,
                "realized_pnl": float(p.realized_pnl),
            })
        total_equity = account.cash_balance + positions_value
        return {
            "has_account": True,
            "account_id": account.id,
            "cash_balance": float(account.cash_balance),
            "positions_value": float(positions_value),
            "total_equity": float(total_equity),
            "unrealized_pnl": float(unrealized_pnl),
            "total_return": float(total_equity - account.initial_capital),
            "total_return_pct": float((total_equity - account.initial_capital) / account.initial_capital * 100) if account.initial_capital > 0 else 0.0,
            "positions_count": len(positions_list),
            "positions": positions_list,
        }

    async def _get_watchlists(self, user_id: int) -> list[dict[str, Any]]:
        wls = (await self._session.execute(
            select(Watchlist).where(Watchlist.user_id == user_id)
        )).scalars().all()
        results = []
        for wl in wls:
            items = (await self._session.execute(
                select(WatchlistItem).where(WatchlistItem.watchlist_id == wl.id)
            )).scalars().all()
            results.append({
                "id": wl.id,
                "name": wl.name,
                "description": wl.description,
                "item_count": len(items),
                "symbols": [item.symbol for item in items[:10]],
            })
        return results

    async def _get_ai_picks(self, user_id: int) -> list[dict[str, Any]]:
        watchlisted_symbols = (await self._session.execute(
            select(WatchlistItem.symbol)
            .join(Watchlist, WatchlistItem.watchlist_id == Watchlist.id)
            .where(Watchlist.user_id == user_id)
            .distinct()
        )).scalars().all()
        if not watchlisted_symbols:
            return []
        picks = []
        for symbol in watchlisted_symbols:
            score = (await self._session.execute(
                select(DynamicAIScore)
                .where(DynamicAIScore.symbol == symbol)
                .order_by(DynamicAIScore.as_of_date.desc())
                .limit(1)
            )).scalar_one_or_none()
            if score and score.combined_signal in ("buy", "strong_buy"):
                picks.append({
                    "symbol": symbol,
                    "combined_score": score.combined_score,
                    "combined_signal": score.combined_signal,
                    "combined_confidence": score.combined_confidence,
                    "as_of_date": score.as_of_date.isoformat() if score.as_of_date else None,
                })
        return picks

    async def _get_recent_news(self, user_id: int) -> list[dict[str, Any]]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=3)
        watchlisted_symbols = (await self._session.execute(
            select(WatchlistItem.symbol)
            .join(Watchlist, WatchlistItem.watchlist_id == Watchlist.id)
            .where(Watchlist.user_id == user_id)
            .distinct()
        )).scalars().all()
        if not watchlisted_symbols:
            return []
        articles = (await self._session.execute(
            select(NewsArticle)
            .where(NewsArticle.symbol.in_(watchlisted_symbols), NewsArticle.published_at >= cutoff)
            .order_by(desc(NewsArticle.published_at))
            .limit(20)
        )).scalars().all()
        results = []
        for article in articles:
            nlp = (await self._session.execute(
                select(NewsNLPAnalysis).where(NewsNLPAnalysis.article_id == article.id)
            )).scalar_one_or_none()
            sentiment = nlp.sentiment_label if nlp else "neutral"
            results.append({
                "id": article.id,
                "symbol": article.symbol,
                "title": article.title,
                "source": article.source,
                "published_at": article.published_at.isoformat() if article.published_at else None,
                "sentiment": sentiment,
                "sentiment_confidence": nlp.sentiment_confidence if nlp else None,
            })
        return results

    async def _get_performance(self, user_id: int) -> dict[str, Any]:
        analytics_svc = PaperAnalyticsService(self._session)
        analytics = await analytics_svc.compute_analytics(user_id)
        if not analytics:
            return {"has_data": False}
        latest_snapshot = (await self._session.execute(
            select(func.avg(PerformanceSnapshot.total_trades), func.sum(PerformanceSnapshot.total_pnl))
            .select_from(PerformanceSnapshot)
            .where(PerformanceSnapshot.user_id == user_id)
        )).one_or_none()
        return {
            "has_data": True,
            "cagr": analytics.get("cagr"),
            "win_rate": analytics.get("win_rate"),
            "profit_factor": analytics.get("profit_factor"),
            "sharpe_ratio": analytics.get("sharpe_ratio"),
            "sortino_ratio": analytics.get("sortino_ratio"),
            "max_drawdown": analytics.get("max_drawdown"),
            "expectancy": analytics.get("expectancy"),
            "total_trades": analytics.get("total_trades"),
            "winning_trades": analytics.get("winning_trades"),
            "losing_trades": analytics.get("losing_trades"),
        }

    async def _get_recent_alerts(self, user_id: int) -> list[dict[str, Any]]:
        events = (await self._session.execute(
            select(WatchlistMonitorEvent)
            .where(WatchlistMonitorEvent.user_id == user_id)
            .order_by(desc(WatchlistMonitorEvent.triggered_at))
            .limit(20)
        )).scalars().all()
        return [
            {
                "id": e.id,
                "symbol": e.symbol,
                "event_type": e.event_type,
                "severity": e.severity,
                "title": e.title,
                "message": e.message,
                "is_read": e.is_read,
                "triggered_at": e.triggered_at.isoformat() if e.triggered_at else None,
            }
            for e in events
        ]
