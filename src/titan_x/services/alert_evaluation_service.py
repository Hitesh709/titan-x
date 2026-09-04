import math
from datetime import date, timedelta
from typing import Any

import structlog
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from titan_x.core.time import utcnow
from titan_x.models.company import Company
from titan_x.models.price import DailyPrice
from titan_x.models.watchlist import Notification, Watchlist, WatchlistAlert, WatchlistAiInsight, WatchlistItem
from titan_x.services.market_data_service import MarketDataService
from titan_x.services.notification_delivery_service import NotificationDeliveryService

logger = structlog.get_logger(__name__)


class AlertEvaluationService:
    def __init__(self, session: AsyncSession, delivery_service: NotificationDeliveryService | None = None) -> None:
        self._session = session
        self._delivery = delivery_service
        self._market_data = MarketDataService(session)

    async def evaluate_all_active_alerts(self) -> int:
        result = await self._session.execute(select(WatchlistAlert).options(selectinload(WatchlistAlert.item).selectinload(WatchlistItem.watchlist)).where(WatchlistAlert.is_active == True))
        alerts = result.unique().scalars().all()
        triggered = 0
        for alert in alerts:
            try:
                if await self._evaluate_alert(alert):
                    triggered += 1
            except Exception:
                logger.exception("alert_evaluation_failed", alert_id=alert.id, alert_type=alert.alert_type)
        return triggered

    async def evaluate_watchlist_alerts(self, watchlist_id: int) -> list[dict[str, Any]]:
        result = await self._session.execute(select(WatchlistAlert).options(selectinload(WatchlistAlert.item)).where(WatchlistAlert.is_active == True, WatchlistAlert.watchlist_item_id.in_(select(WatchlistItem.id).where(WatchlistItem.watchlist_id == watchlist_id))))
        alerts = result.unique().scalars().all()
        triggered: list[dict[str, Any]] = []
        for alert in alerts:
            if await self._evaluate_alert(alert):
                triggered.append({"alert_id": alert.id, "alert_type": alert.alert_type, "symbol": alert.item.symbol})
        return triggered

    async def _evaluate_alert(self, alert: WatchlistAlert) -> bool:
        item = alert.item
        if item is None or item.watchlist is None:
            return False
        watchlist = item.watchlist
        alert_type, op, threshold, symbol = alert.alert_type, alert.operator, alert.threshold_value, item.symbol
        triggered = False
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
        if alert_type in {"price.above", "price.below"}:
            return self._compare(price, op, threshold)
        if alert_type == "price.change_pct":
            change = await self._get_price_change_pct(symbol)
            return change is not None and self._compare(change, op, threshold)
        if alert_type == "price.crosses_ma":
            ma = await self._get_moving_average(symbol, int(threshold) if threshold > 0 else 20)
            prev_price = await self._get_prev_price(symbol)
            if ma is None or prev_price is None:
                return False
            return prev_price <= ma and price > ma if op == "crosses_above" else prev_price >= ma and price < ma
        return False

    async def _evaluate_volume_alert(self, symbol: str, alert_type: str, op: str, threshold: float) -> bool:
        if alert_type in {"volume.above", "volume.below"}:
            vol = await self._get_latest_volume(symbol)
            return vol is not None and self._compare(float(vol), op, threshold)
        return await self._detect_volume_spike(symbol, threshold) if alert_type == "volume.spike" else False

    async def _evaluate_news_alert(self, symbol: str, alert_type: str, op: str, threshold: float) -> bool:
        from titan_x.models.news import NewsArticle
        cutoff = date.today() - timedelta(days=2)
        result = await self._session.execute(select(func.count()).select_from(NewsArticle).where(NewsArticle.symbol == symbol, NewsArticle.published_at >= cutoff))
        return self._compare(float(result.scalar() or 0), op, threshold) if alert_type == "news.mention" else False

    async def _evaluate_pattern_alert(self, symbol: str, alert_type: str) -> bool:
        from titan_x.models.chart_pattern import ChartPattern
        pattern_name = alert_type.replace("pattern.", "")
        cutoff = date.today() - timedelta(days=3)
        result = await self._session.execute(select(func.count()).select_from(ChartPattern).where(ChartPattern.symbol == symbol, ChartPattern.pattern_name == pattern_name, func.date(ChartPattern.created_at) >= cutoff))
        return (result.scalar() or 0) > 0

    async def _evaluate_ai_score_alert(self, watchlist_id: int, symbol: str | None, alert_type: str, op: str, threshold: float) -> bool:
        query = select(func.avg(WatchlistAiInsight.score)).where(WatchlistAiInsight.watchlist_id == watchlist_id)
        if symbol:
            query = query.where(WatchlistAiInsight.symbol == symbol)
        avg_score = (await self._session.execute(query)).scalar()
        return avg_score is not None and self._compare(float(avg_score), op, threshold)

    async def _evaluate_portfolio_alert(self, watchlist_id: int, alert_type: str, op: str, threshold: float) -> bool:
        if alert_type == "portfolio.holding_count":
            count = (await self._session.execute(select(func.count()).select_from(WatchlistItem).where(WatchlistItem.watchlist_id == watchlist_id))).scalar() or 0
            return self._compare(float(count), op, threshold)
        if alert_type == "portfolio.sector_exposure":
            count = (await self._session.execute(select(func.count()).select_from(WatchlistItem).where(WatchlistItem.watchlist_id == watchlist_id, WatchlistItem.symbol.in_(select(Company.symbol).where(Company.sector.isnot(None)))))).scalar() or 0
            return self._compare(float(count), op, threshold)
        return False

    async def _create_and_deliver_notification(self, alert: WatchlistAlert, watchlist: Watchlist) -> None:
        symbol = alert.item.symbol if alert.item else "unknown"
        title = f"Alert: {alert.alert_type} ({symbol})"
        message = f"Alert '{alert.alert_type}' triggered for {symbol} (operator={alert.operator}, threshold={alert.threshold_value})"
        self._session.add(Notification(user_id=watchlist.user_id, watchlist_id=watchlist.id, alert_id=alert.id, title=title, message=message, notification_type="alert"))
        await self._session.flush()
        if self._delivery:
            await self._delivery.deliver(watchlist.user_id, title, message, {"alert_id": alert.id})

    @staticmethod
    def _compare(value: float, operator: str, threshold: float) -> bool:
        if operator == "gt": return value > threshold
        if operator == "gte": return value >= threshold
        if operator == "lt": return value < threshold
        if operator == "lte": return value <= threshold
        if operator == "eq": return abs(value - threshold) < 0.0001
        return False

    async def _get_latest_price(self, symbol: str) -> float | None:
        try:
            value = (await self._market_data.get_quote(symbol)).get("last_price")
            if value is not None and float(value) > 0:
                return float(value)
        except Exception:
            logger.warning("live_alert_price_unavailable", symbol=symbol)
        value = (await self._session.execute(select(DailyPrice.close).where(DailyPrice.symbol == symbol.upper()).order_by(desc(DailyPrice.trade_date)).limit(1))).scalar_one_or_none()
        return float(value) if value is not None and float(value) > 0 else None

    async def _get_prev_price(self, symbol: str) -> float | None:
        value = (await self._session.execute(select(DailyPrice.close).where(DailyPrice.symbol == symbol.upper()).order_by(desc(DailyPrice.trade_date)).offset(1).limit(1))).scalar_one_or_none()
        return float(value) if value is not None else None

    async def _get_price_change_pct(self, symbol: str) -> float | None:
        try:
            value = (await self._market_data.get_quote(symbol)).get("change_percent")
            if value is not None:
                return float(value)
        except Exception:
            pass
        rows = (await self._session.execute(select(DailyPrice.close).where(DailyPrice.symbol == symbol.upper()).order_by(desc(DailyPrice.trade_date)).limit(2))).scalars().all()
        if len(rows) < 2:
            return None
        p0, p1 = float(rows[0]), float(rows[1])
        return ((p0 - p1) / p1) * 100 if p1 else None

    async def _get_moving_average(self, symbol: str, period: int) -> float | None:
        prices = (await self._session.execute(select(DailyPrice.close).where(DailyPrice.symbol == symbol.upper()).order_by(desc(DailyPrice.trade_date)).limit(period))).scalars().all()
        return sum(float(p) for p in prices) / period if len(prices) >= period else None

    async def _get_latest_volume(self, symbol: str) -> int | None:
        try:
            value = (await self._market_data.get_quote(symbol)).get("volume")
            return int(float(value)) if value is not None and float(value) >= 0 else None
        except Exception:
            return None

    async def _detect_volume_spike(self, symbol: str, z_threshold: float = 2.0) -> bool:
        volumes = [float(v) for v in (await self._session.execute(select(DailyPrice.volume).where(DailyPrice.symbol == symbol.upper()).order_by(desc(DailyPrice.trade_date)).limit(21))).scalars().all()]
        if len(volumes) < 10:
            return False
        latest, rest = volumes[0], volumes[1:]
        mu = sum(rest) / len(rest)
        variance = sum((v - mu) ** 2 for v in rest) / len(rest)
        std = math.sqrt(variance) if variance > 0 else 1
        return (latest - mu) / std > z_threshold