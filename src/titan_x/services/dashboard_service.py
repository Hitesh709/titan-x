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

_PILLARS = [
    ("Technical", "technical_score", "technical_signal"),
    ("Fundamentals", "fundamental_score", "fundamental_signal"),
    ("News", "news_score", "news_signal"),
    ("Macro", "macro_score", "macro_signal"),
    ("Liquidity", "liquidity_score", "liquidity_signal"),
    ("Market Regime", "market_regime_score", "market_regime_signal"),
]

_POSITIVE_SIGNALS = ("buy", "strong_buy", "bullish", "positive")
_NEGATIVE_SIGNALS = ("sell", "strong_sell", "bearish", "negative")


def _score_to_expected_return(score: float) -> float:
    return max(1.0, round(2.0 + (score - 55.0) * 0.5, 2))


def _score_to_holding_period(confidence: float) -> int:
    return max(5, min(60, round(10 + confidence * 30)))


def _risk_label(risk_score: float | None, combined_score: float) -> str:
    if risk_score is not None:
        if risk_score >= 65:
            return "High"
        if risk_score >= 40:
            return "Medium"
        return "Low"
    if combined_score >= 75:
        return "Medium"
    return "Low"


def _build_pick_explanation(score: DynamicAIScore) -> tuple[list[str], list[str], list[str]]:
    pillars: list[tuple[str, float, str | None]] = []
    for label, score_attr, signal_attr in _PILLARS:
        s = getattr(score, score_attr, None)
        if s is None:
            continue
        pillars.append((label, s, getattr(score, signal_attr, None)))

    evidence: list[str] = []
    why_buy: list[str] = []
    why_not_buy: list[str] = []

    for label, s, sig in pillars:
        sig_low = (sig or "").lower()
        if s >= 65 or sig_low in _POSITIVE_SIGNALS:
            evidence.append(f"{label} {s:.0f}")
            why_buy.append(f"{label} strength ({s:.0f}/100)")
        if s < 55 or sig_low in _NEGATIVE_SIGNALS:
            why_not_buy.append(f"Weak {label.lower()} ({s:.0f}/100)")

    risk_score = score.risk_score
    risk_sig = (score.risk_signal or "").lower()
    if risk_score is not None and risk_score >= 60:
        why_not_buy.append(f"Elevated risk score ({risk_score:.0f}/100)")
    elif risk_score is not None and risk_score < 40:
        why_buy.append(f"Low risk profile ({risk_score:.0f}/100)")
    if risk_sig in _NEGATIVE_SIGNALS:
        why_not_buy.append("Adverse risk outlook")

    if not evidence:
        evidence = ["Composite AI score"]
    if not why_buy:
        why_buy = ["Positive momentum vs. benchmark"]
    if not why_not_buy:
        why_not_buy = ["Limited negative catalysts detected"]

    return evidence, why_buy, why_not_buy


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
            select(Watchlist)
            .where(Watchlist.user_id == user_id)
            .options(joinedload(Watchlist.items))
        )).scalars().unique().all()
        results = []
        for wl in wls:
            items = wl.items or []
            results.append({
                "id": wl.id,
                "name": wl.name,
                "description": wl.description,
                "item_count": len(items),
                "symbols": [item.symbol for item in items[:10]],
            })
        return results

    async def get_ai_picks(self, user_id: int) -> list[dict[str, Any]]:
        return await self._get_ai_picks(user_id)

    async def _get_ai_picks(self, user_id: int) -> list[dict[str, Any]]:
        watchlisted_symbols = (await self._session.execute(
            select(WatchlistItem.symbol)
            .join(Watchlist, WatchlistItem.watchlist_id == Watchlist.id)
            .where(Watchlist.user_id == user_id)
            .distinct()
        )).scalars().all()
        if not watchlisted_symbols:
            return []
        scores = (await self._session.execute(
            select(DynamicAIScore)
            .where(DynamicAIScore.symbol.in_(watchlisted_symbols))
            .order_by(DynamicAIScore.symbol, DynamicAIScore.as_of_date.desc())
        )).scalars().all()
        latest: dict[str, DynamicAIScore] = {}
        for s in scores:
            if s.symbol not in latest:
                latest[s.symbol] = s
        picks = []
        for symbol in watchlisted_symbols:
            score = latest.get(symbol)
            if score and score.combined_signal in ("buy", "strong_buy"):
                evidence, why_buy, why_not_buy = _build_pick_explanation(score)
                picks.append({
                    "symbol": symbol,
                    "combined_score": score.combined_score,
                    "combined_signal": score.combined_signal,
                    "combined_confidence": score.combined_confidence,
                    "as_of_date": score.as_of_date.isoformat() if score.as_of_date else None,
                    "expected_return_pct": _score_to_expected_return(score.combined_score),
                    "risk": _risk_label(score.risk_score, score.combined_score),
                    "holding_period_days": _score_to_holding_period(score.combined_confidence),
                    "evidence": evidence,
                    "why_buy": why_buy,
                    "why_not_buy": why_not_buy,
                })
        picks.sort(key=lambda p: p["combined_score"], reverse=True)
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
        article_ids = [a.id for a in articles]
        nlp_map = {}
        if article_ids:
            nlp_rows = (await self._session.execute(
                select(NewsNLPAnalysis).where(NewsNLPAnalysis.article_id.in_(article_ids))
            )).scalars().all()
            nlp_map = {n.article_id: n for n in nlp_rows}
        results = []
        for article in articles:
            nlp = nlp_map.get(article.id)
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
