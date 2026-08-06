import math
from collections.abc import Sequence
from datetime import date, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from titan_x.core.time import utcnow
from titan_x.models.company import Company
from titan_x.models.price import DailyPrice
from titan_x.models.watchlist import (
    Notification,
    Watchlist,
    WatchlistAlert,
    WatchlistAiInsight,
    WatchlistItem,
)
from titan_x.services.notification_delivery_service import NotificationDeliveryService

logger = structlog.get_logger(__name__)


class AlertEvaluationService:
    def __init__(self, session: AsyncSession, delivery_service: NotificationDeliveryService | None = None) -> None:
        self._session = session
        self._delivery = delivery_service

    async def evaluate_all_active_alerts(self) -> int:
        result = await self._session.execute(
            select(WatchlistAlert)
            .options(
                selectinload(WatchlistAlert.item).selectinload(WatchlistItem.watchlist),
            )
            .where(WatchlistAlert.is_active == True)
        )
        alerts = result.unique().scalars().all()
        if not alerts:
            return 0
        triggered = 0
        for alert in alerts:
            try:
                if await self._evaluate_alert(alert):
                    triggered += 1
            except Exception:
                logger.exception("alert_evaluation_failed", alert_id=alert.id, alert_type=alert.alert_type)
        return triggered

    async def evaluate_watchlist_alerts(self, watchlist_id: int) -> list[dict[str, Any]]:
        result = await self._session.execute(
            select(WatchlistAlert)
            .options(selectinload(WatchlistAlert.item))
            .where(
                WatchlistAlert.is_active == True,
                WatchlistAlert.watchlist_item_id.in_(
                    select(WatchlistItem.id).where(WatchlistItem.watchlist_id == watchlist_id)
                ),
            )
        )
        alerts = result.unique().scalars().all()
        triggered: list[dict[str, Any]] = []
        for alert in alerts:
            if await self._evaluate_alert(alert):
                triggered.append({"alert_id": alert.id, "alert_type": alert.alert_type, "symbol": alert.item.symbol})
        return triggered

    async def _evaluate_alert(self, alert: WatchlistAlert) -> bool:
        item = alert.item
        if item is None:
            return False
        watchlist = item.watchlist
        if watchlist is None:
            return False

        triggered = False
        alert_type = alert.alert_type
        op = alert.operator
        threshold = alert.threshold_value
        symbol = item.symbol

        if alert_type.startswith("price."):
            triggered = await self._evaluate_price_alert(symbol, alert_type, op, threshold)

        elif alert_type.startswith("volume."):
            triggered = await self._evaluate_volume_alert(symbol, alert_type, op, threshold)

        elif alert_type.startswith("news."):
            triggered = await self._evaluate_news_alert(symbol, alert_type, op, threshold)

        elif alert_type.startswith("pattern."):
            triggered = await self._evaluate_pattern_alert(symbol, alert_type)

        elif alert_type.startswith("ai_score."):
            triggered = await self._evaluate_ai_score_alert(watchlist.id, symbol, alert_type, op, threshold)

        elif alert_type.startswith("portfolio."):
            triggered = await self._evaluate_portfolio_alert(watchlist.id, alert_type, op, threshold)

        if triggered:
            alert.last_triggered_at = utcnow()
            await self._create_and_deliver_notification(alert, watchlist)

        return triggered

    async def _evaluate_price_alert(self, symbol: str, alert_type: str, op: str, threshold: float) -> bool:
        price = await self._get_latest_price(symbol)
        if price is None:
            return False
        if alert_type == "price.above":
            return self._compare(price, op, threshold)
        elif alert_type == "price.below":
            return self._compare(price, op, threshold)
        elif alert_type == "price.change_pct":
            change = await self._get_price_change_pct(symbol)
            if change is None:
                return False
            return self._compare(change, op, threshold)
        elif alert_type == "price.crosses_ma":
            ma = await self._get_moving_average(symbol, int(threshold) if threshold > 0 else 20)
            if ma is None or price is None:
                return False
            prev_price = await self._get_prev_price(symbol)
            if prev_price is None:
                return False
            return prev_price <= ma and price > ma if op == "crosses_above" else prev_price >= ma and price < ma
        return False

    async def _evaluate_volume_alert(self, symbol: str, alert_type: str, op: str, threshold: float) -> bool:
        if alert_type == "volume.above":
            vol = await self._get_latest_volume(symbol)
            return vol is not None and self._compare(float(vol), op, threshold)
        elif alert_type == "volume.below":
            vol = await self._get_latest_volume(symbol)
            return vol is not None and self._compare(float(vol), op, threshold)
        elif alert_type == "volume.spike":
            return await self._detect_volume_spike(symbol, threshold)
        return False

    async def _evaluate_news_alert(self, symbol: str, alert_type: str, op: str, threshold: float) -> bool:
        from titan_x.models.news import NewsArticle
        two_days_ago = date.today() - timedelta(days=2)
        result = await self._session.execute(
            select(func.count()).select_from(NewsArticle).where(
                NewsArticle.symbol == symbol,
                NewsArticle.published_at >= two_days_ago,
            )
        )
        count = result.scalar() or 0
        if alert_type == "news.mention":
            return self._compare(float(count), op, threshold)
        return False

    async def _evaluate_pattern_alert(self, symbol: str, alert_type: str) -> bool:
        from titan_x.models.chart_pattern import ChartPattern
        pattern_name = alert_type.replace("pattern.", "")
        three_days_ago = date.today() - timedelta(days=3)
        result = await self._session.execute(
            select(func.count()).select_from(ChartPattern).where(
                ChartPattern.symbol == symbol,
                ChartPattern.pattern_name == pattern_name,
                func.date(ChartPattern.created_at) >= three_days_ago,
            )
        )
        return (result.scalar() or 0) > 0

    async def _evaluate_ai_score_alert(self, watchlist_id: int, symbol: str | None, alert_type: str, op: str, threshold: float) -> bool:
        query = select(func.avg(WatchlistAiInsight.score)).where(WatchlistAiInsight.watchlist_id == watchlist_id)
        if symbol:
            query = query.where(WatchlistAiInsight.symbol == symbol)
        result = await self._session.execute(query)
        avg_score = result.scalar()
        if avg_score is None:
            return False
        return self._compare(float(avg_score), op, threshold)

    async def _evaluate_portfolio_alert(self, watchlist_id: int, alert_type: str, op: str, threshold: float) -> bool:
        if alert_type == "portfolio.holding_count":
            result = await self._session.execute(
                select(func.count()).select_from(WatchlistItem).where(WatchlistItem.watchlist_id == watchlist_id)
            )
            count = result.scalar() or 0
            return self._compare(float(count), op, threshold)
        elif alert_type == "portfolio.sector_exposure":
            result = await self._session.execute(
                select(func.count()).select_from(WatchlistItem).where(
                    WatchlistItem.watchlist_id == watchlist_id,
                    WatchlistItem.symbol.in_(select(Company.symbol).where(Company.sector.isnot(None))),
                )
            )
            count = result.scalar() or 0
            return self._compare(float(count), op, threshold)
        return False

    async def _create_and_deliver_notification(self, alert: WatchlistAlert, watchlist: Watchlist) -> None:
        symbol = alert.item.symbol if alert.item else "unknown"
        title = f"Alert: {alert.alert_type} ({symbol})"
        message = f"Alert '{alert.alert_type}' triggered for {symbol} (operator={alert.operator}, threshold={alert.threshold_value})"

        notif = Notification(
            user_id=watchlist.user_id,
            watchlist_id=watchlist.id,
            alert_id=alert.id,
            title=title,
            message=message,
            notification_type="alert",
        )
        self._session.add(notif)
        await self._session.flush()

        if self._delivery:
            await self._delivery.deliver(watchlist.user_id, title, message, {"alert_id": alert.id})

    def _compare(self, value: float, operator: str, threshold: float) -> bool:
        if operator == "gt":
            return value > threshold
        elif operator == "gte":
            return value >= threshold
        elif operator == "lt":
            return value < threshold
        elif operator == "lte":
            return value <= threshold
        elif operator == "eq":
            return abs(value - threshold) < 0.0001
        return False

    async def _get_latest_price(self, symbol: str) -> float | None:
        result = await self._session.execute(
            select(DailyPrice.close).where(DailyPrice.symbol == symbol.upper())
            .order_by(desc(DailyPrice.trade_date)).limit(1)
        )
        row = result.scalar_one_or_none()
        return float(row) if row is not None else None

    async def _get_prev_price(self, symbol: str) -> float | None:
        result = await self._session.execute(
            select(DailyPrice.close).where(DailyPrice.symbol == symbol.upper())
            .order_by(desc(DailyPrice.trade_date)).offset(1).limit(1)
        )
        row = result.scalar_one_or_none()
        return float(row) if row is not None else None

    async def _get_price_change_pct(self, symbol: str) -> float | None:
        result = await self._session.execute(
            select(DailyPrice.close).where(DailyPrice.symbol == symbol.upper())
            .order_by(desc(DailyPrice.trade_date)).limit(2)
        )
        rows = result.scalars().all()
        if len(rows) < 2:
            return None
        p0, p1 = float(rows[0]), float(rows[1])
        if p1 == 0:
            return None
        return ((p0 - p1) / p1) * 100

    async def _get_moving_average(self, symbol: str, period: int) -> float | None:
        result = await self._session.execute(
            select(DailyPrice.close).where(DailyPrice.symbol == symbol.upper())
            .order_by(desc(DailyPrice.trade_date)).limit(period)
        )
        prices = result.scalars().all()
        if len(prices) < period:
            return None
        return sum(float(p) for p in prices) / period

    async def _get_latest_volume(self, symbol: str) -> int | None:
        result = await self._session.execute(
            select(DailyPrice.volume).where(DailyPrice.symbol == symbol.upper())
            .order_by(desc(DailyPrice.trade_date)).limit(1)
        )
        return result.scalar_one_or_none()

    async def _detect_volume_spike(self, symbol: str, z_threshold: float = 2.0) -> bool:
        result = await self._session.execute(
            select(DailyPrice.volume).where(DailyPrice.symbol == symbol.upper())
            .order_by(desc(DailyPrice.trade_date)).limit(21)
        )
        volumes = [float(v) for v in result.scalars().all()]
        if len(volumes) < 10:
            return False
        latest = volumes[0]
        rest = volumes[1:]
        mu = sum(rest) / len(rest)
        variance = sum((v - mu) ** 2 for v in rest) / len(rest)
        std = math.sqrt(variance) if variance > 0 else 1
        return (latest - mu) / std > z_threshold
