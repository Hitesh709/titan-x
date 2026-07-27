from collections.abc import Sequence
from datetime import date, datetime, timedelta
from typing import Any

import math
import random

import structlog
from sqlalchemy import and_, desc, func, null, select, update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy.orm.attributes import instance_state

from titan_x.db.repository import BaseRepository
from titan_x.models.company import Company
from titan_x.models.price import DailyPrice
from titan_x.models.watchlist import (
    Notification,
    Watchlist,
    WatchlistAiInsight,
    WatchlistAlert,
    WatchlistFolder,
    WatchlistItem,
    WatchlistItemTag,
    WatchlistTag,
)

logger = structlog.get_logger(__name__)


class WatchlistEngine:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._folder_repo = BaseRepository(session, WatchlistFolder)
        self._watchlist_repo = BaseRepository(session, Watchlist)
        self._item_repo = BaseRepository(session, WatchlistItem)
        self._tag_repo = BaseRepository(session, WatchlistTag)
        self._alert_repo = BaseRepository(session, WatchlistAlert)
        self._insight_repo = BaseRepository(session, WatchlistAiInsight)
        self._notification_repo = BaseRepository(session, Notification)

    # ── Folders ──────────────────────────────────────────────────────────

    async def create_folder(
        self, user_id: int, name: str, description: str | None = None,
        parent_id: int | None = None, color: str | None = None,
        sort_order: int = 0,
    ) -> dict[str, Any]:
        folder = await self._folder_repo.create(
            user_id=user_id, name=name, description=description,
            parent_id=parent_id, color=color, sort_order=sort_order,
        )
        return self._folder_to_dict(folder)

    async def list_folders(self, user_id: int) -> list[dict[str, Any]]:
        result = await self._session.execute(
            select(WatchlistFolder)
            .where(WatchlistFolder.user_id == user_id)
            .order_by(WatchlistFolder.sort_order, WatchlistFolder.name)
        )
        folders = result.scalars().all()
        return [self._folder_to_dict(f) for f in folders]

    async def get_folder(self, folder_id: int, user_id: int) -> dict[str, Any] | None:
        folder = await self._folder_repo.get(folder_id)
        if folder is None or folder.user_id != user_id:
            return None
        return self._folder_to_dict(folder)

    async def update_folder(
        self, folder_id: int, user_id: int, **kwargs: Any,
    ) -> dict[str, Any] | None:
        folder = await self._folder_repo.get(folder_id)
        if folder is None or folder.user_id != user_id:
            return None
        allowed = {"name", "description", "parent_id", "color", "sort_order"}
        update_kw = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
        if not update_kw:
            return self._folder_to_dict(folder)
        updated = await self._folder_repo.update(folder_id, **update_kw)
        return self._folder_to_dict(updated) if updated else None

    async def delete_folder(self, folder_id: int, user_id: int) -> bool:
        folder = await self._folder_repo.get(folder_id)
        if folder is None or folder.user_id != user_id:
            return False
        await self._session.execute(
            sql_update(Watchlist).where(Watchlist.folder_id == folder_id).values(folder_id=None)
        )
        await self._session.execute(
            sql_update(WatchlistFolder).where(WatchlistFolder.parent_id == folder_id).values(parent_id=None)
        )
        return await self._folder_repo.delete(folder_id)

    # ── Watchlists ───────────────────────────────────────────────────────

    async def create_watchlist(
        self, user_id: int, name: str, description: str | None = None,
        folder_id: int | None = None, is_default: bool = False,
    ) -> dict[str, Any]:
        if is_default:
            await self._session.execute(
                sql_update(Watchlist)
                .where(and_(Watchlist.user_id == user_id, Watchlist.is_default == True))
                .values(is_default=False)
            )
        watchlist = await self._watchlist_repo.create(
            user_id=user_id, name=name, description=description,
            folder_id=folder_id, is_default=is_default,
        )
        return self._watchlist_to_dict(watchlist)

    async def list_watchlists(
        self, user_id: int, folder_id: int | None = None, skip: int = 0, limit: int = 100,
    ) -> tuple[Sequence[Watchlist], int]:
        query = select(Watchlist).where(Watchlist.user_id == user_id)
        count_query = select(func.count()).select_from(Watchlist).where(Watchlist.user_id == user_id)
        if folder_id is not None:
            query = query.where(Watchlist.folder_id == folder_id)
            count_query = count_query.where(Watchlist.folder_id == folder_id)
        total = (await self._session.execute(count_query)).scalar() or 0
        query = query.order_by(desc(Watchlist.is_default), Watchlist.name).offset(skip).limit(limit)
        rows = (await self._session.execute(query)).scalars().all()
        return rows, total

    async def get_watchlist(self, watchlist_id: int, user_id: int) -> Watchlist | None:
        result = await self._session.execute(
            select(Watchlist)
            .options(selectinload(Watchlist.items).selectinload(WatchlistItem.tags))
            .where(Watchlist.id == watchlist_id, Watchlist.user_id == user_id)
        )
        return result.unique().scalar_one_or_none()

    async def update_watchlist(
        self, watchlist_id: int, user_id: int, **kwargs: Any,
    ) -> dict[str, Any] | None:
        watchlist = await self._watchlist_repo.get(watchlist_id)
        if watchlist is None or watchlist.user_id != user_id:
            return None
        allowed = {"name", "description", "folder_id", "is_default"}
        if kwargs.get("is_default"):
            await self._session.execute(
                sql_update(Watchlist)
                .where(and_(Watchlist.user_id == user_id, Watchlist.is_default == True, Watchlist.id != watchlist_id))
                .values(is_default=False)
            )
        update_kw = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
        if not update_kw:
            return self._watchlist_to_dict(watchlist)
        updated = await self._watchlist_repo.update(watchlist_id, **update_kw)
        return self._watchlist_to_dict(updated) if updated else None

    async def delete_watchlist(self, watchlist_id: int, user_id: int) -> bool:
        watchlist = await self._watchlist_repo.get(watchlist_id)
        if watchlist is None or watchlist.user_id != user_id:
            return False
        return await self._watchlist_repo.delete(watchlist_id)

    # ── Items ────────────────────────────────────────────────────────────

    async def add_item(
        self, watchlist_id: int, user_id: int, symbol: str,
        notes: str | None = None, sort_order: int | None = None,
    ) -> dict[str, Any] | None:
        watchlist = await self._watchlist_repo.get(watchlist_id)
        if watchlist is None or watchlist.user_id != user_id:
            return None
        symbol = symbol.upper()
        existing = await self._session.execute(
            select(WatchlistItem).where(
                WatchlistItem.watchlist_id == watchlist_id,
                WatchlistItem.symbol == symbol,
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError(f"Symbol {symbol} already in watchlist")
        if sort_order is None:
            max_order = await self._session.execute(
                select(func.coalesce(func.max(WatchlistItem.sort_order), -1))
                .where(WatchlistItem.watchlist_id == watchlist_id)
            )
            sort_order = (max_order.scalar() or -1) + 1
        item = await self._item_repo.create(
            watchlist_id=watchlist_id, symbol=symbol,
            notes=notes, sort_order=sort_order,
        )
        await self._session.refresh(item, ["tags"])
        return self._item_to_dict(item)

    async def remove_item(self, item_id: int, watchlist_id: int, user_id: int) -> bool:
        watchlist = await self._watchlist_repo.get(watchlist_id)
        if watchlist is None or watchlist.user_id != user_id:
            return False
        item = await self._item_repo.get(item_id)
        if item is None or item.watchlist_id != watchlist_id:
            return False
        return await self._item_repo.delete(item_id)

    async def update_item(
        self, item_id: int, watchlist_id: int, user_id: int, **kwargs: Any,
    ) -> dict[str, Any] | None:
        watchlist = await self._watchlist_repo.get(watchlist_id)
        if watchlist is None or watchlist.user_id != user_id:
            return None
        item = await self._item_repo.get(item_id)
        if item is None or item.watchlist_id != watchlist_id:
            return None
        allowed = {"notes", "sort_order"}
        update_kw = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
        if not update_kw:
            return self._item_to_dict(item)
        updated = await self._item_repo.update(item_id, **update_kw)
        if updated:
            await self._session.refresh(updated, ["tags"])
        return self._item_to_dict(updated) if updated else None

    async def reorder_items(
        self, watchlist_id: int, user_id: int, item_ids: list[int],
    ) -> bool:
        watchlist = await self._watchlist_repo.get(watchlist_id)
        if watchlist is None or watchlist.user_id != user_id:
            return False
        for idx, item_id in enumerate(item_ids):
            await self._item_repo.update(item_id, sort_order=idx)
        return True

    async def list_items(
        self, watchlist_id: int, user_id: int, skip: int = 0, limit: int = 100,
    ) -> list[dict[str, Any]] | None:
        watchlist = await self._watchlist_repo.get(watchlist_id)
        if watchlist is None or watchlist.user_id != user_id:
            return None
        result = await self._session.execute(
            select(WatchlistItem)
            .options(selectinload(WatchlistItem.tags))
            .where(WatchlistItem.watchlist_id == watchlist_id)
            .order_by(WatchlistItem.sort_order, WatchlistItem.symbol)
            .offset(skip).limit(limit)
        )
        items = result.unique().scalars().all()
        return [self._item_to_dict(i) for i in items]

    # ── Tags ─────────────────────────────────────────────────────────────

    async def create_tag(
        self, user_id: int, name: str, color: str | None = None,
    ) -> dict[str, Any]:
        tag = await self._tag_repo.create(user_id=user_id, name=name, color=color)
        return self._tag_to_dict(tag)

    async def list_tags(self, user_id: int) -> list[dict[str, Any]]:
        result = await self._session.execute(
            select(WatchlistTag)
            .where(WatchlistTag.user_id == user_id)
            .order_by(WatchlistTag.name)
        )
        tags = result.scalars().all()
        return [self._tag_to_dict(t) for t in tags]

    async def delete_tag(self, tag_id: int, user_id: int) -> bool:
        tag = await self._tag_repo.get(tag_id)
        if tag is None or tag.user_id != user_id:
            return False
        return await self._tag_repo.delete(tag_id)

    async def tag_item(self, item_id: int, tag_id: int, watchlist_id: int, user_id: int) -> bool:
        watchlist = await self._watchlist_repo.get(watchlist_id)
        if watchlist is None or watchlist.user_id != user_id:
            return False
        item = await self._item_repo.get(item_id)
        tag = await self._tag_repo.get(tag_id)
        if item is None or tag is None or item.watchlist_id != watchlist_id or tag.user_id != user_id:
            return False
        assoc = WatchlistItemTag(watchlist_item_id=item_id, watchlist_tag_id=tag_id)
        self._session.add(assoc)
        await self._session.flush()
        return True

    async def untag_item(self, item_id: int, tag_id: int, watchlist_id: int, user_id: int) -> bool:
        watchlist = await self._watchlist_repo.get(watchlist_id)
        if watchlist is None or watchlist.user_id != user_id:
            return False
        item = await self._item_repo.get(item_id)
        tag = await self._tag_repo.get(tag_id)
        if item is None or tag is None or item.watchlist_id != watchlist_id or tag.user_id != user_id:
            return False
        assoc = await self._session.get(
            WatchlistItemTag, (item_id, tag_id),
        )
        if assoc:
            await self._session.delete(assoc)
            await self._session.flush()
        return assoc is not None

    # ── Alerts ───────────────────────────────────────────────────────────

    async def create_alert(
        self, item_id: int, watchlist_id: int, user_id: int,
        alert_type: str, operator: str, threshold_value: float,
    ) -> dict[str, Any] | None:
        watchlist = await self._watchlist_repo.get(watchlist_id)
        if watchlist is None or watchlist.user_id != user_id:
            return None
        item = await self._item_repo.get(item_id)
        if item is None or item.watchlist_id != watchlist_id:
            return None
        alert = await self._alert_repo.create(
            watchlist_item_id=item_id, alert_type=alert_type,
            operator=operator, threshold_value=threshold_value,
        )
        return self._alert_to_dict(alert)

    async def list_alerts(self, watchlist_id: int, user_id: int) -> list[dict[str, Any]] | None:
        watchlist = await self._watchlist_repo.get(watchlist_id)
        if watchlist is None or watchlist.user_id != user_id:
            return None
        result = await self._session.execute(
            select(WatchlistAlert)
            .join(WatchlistItem, WatchlistAlert.watchlist_item_id == WatchlistItem.id)
            .where(WatchlistItem.watchlist_id == watchlist_id)
            .order_by(WatchlistAlert.created_at.desc())
        )
        alerts = result.scalars().all()
        return [self._alert_to_dict(a) for a in alerts]

    async def update_alert(
        self, alert_id: int, watchlist_id: int, user_id: int, **kwargs: Any,
    ) -> dict[str, Any] | None:
        watchlist = await self._watchlist_repo.get(watchlist_id)
        if watchlist is None or watchlist.user_id != user_id:
            return None
        alert = await self._alert_repo.get(alert_id)
        if alert is None:
            return None
        item = await self._item_repo.get(alert.watchlist_item_id)
        if item is None or item.watchlist_id != watchlist_id:
            return None
        allowed = {"alert_type", "operator", "threshold_value", "is_active"}
        update_kw = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
        if not update_kw:
            return self._alert_to_dict(alert)
        updated = await self._alert_repo.update(alert_id, **update_kw)
        return self._alert_to_dict(updated) if updated else None

    async def delete_alert(self, alert_id: int, watchlist_id: int, user_id: int) -> bool:
        watchlist = await self._watchlist_repo.get(watchlist_id)
        if watchlist is None or watchlist.user_id != user_id:
            return False
        alert = await self._alert_repo.get(alert_id)
        if alert is None:
            return False
        item = await self._item_repo.get(alert.watchlist_item_id)
        if item is None or item.watchlist_id != watchlist_id:
            return False
        return await self._alert_repo.delete(alert_id)

    # ── AI Monitoring ────────────────────────────────────────────────────

    async def run_ai_analysis(self, watchlist_id: int, user_id: int) -> list[dict[str, Any]]:
        watchlist = await self._watchlist_repo.get(watchlist_id)
        if watchlist is None or watchlist.user_id != user_id:
            return []
        items = await self._get_items_with_prices(watchlist_id)
        if not items:
            return []

        insights: list[dict[str, Any]] = []
        symbols_data = {s: d for s, d in items.items() if d}

        if symbols_data:
            insight = self._analyze_momentum(symbols_data, watchlist_id)
            if insight:
                insights.append(insight)

        if len(symbols_data) >= 2:
            insight = self._analyze_correlation(symbols_data, watchlist_id)
            if insight:
                insights.append(insight)

        insight = self._analyze_volatility(symbols_data, watchlist_id)
        if insight:
            insights.append(insight)

        insight = self._analyze_concentration(symbols_data, watchlist_id)
        if insight:
            insights.append(insight)

        for sym, data in symbols_data.items():
            insight = self._analyze_anomaly(sym, data, watchlist_id)
            if insight:
                insights.append(insight)

        for ins in insights:
            created = await self._insight_repo.create(
                watchlist_id=watchlist_id, insight_type=ins["insight_type"],
                content=ins["content"], score=ins["score"],
                symbol=ins.get("symbol"),
            )
            ins["id"] = created.id
            ins["generated_at"] = created.generated_at.isoformat() if created.generated_at else None

        return insights

    # ── Alerts ───────────────────────────────────────────────────────────

    async def create_alert(
        self, item_id: int, watchlist_id: int, user_id: int,
        alert_type: str, operator: str, threshold_value: float,
    ) -> dict[str, Any] | None:
        watchlist = await self._watchlist_repo.get(watchlist_id)
        if watchlist is None or watchlist.user_id != user_id:
            return None
        item = await self._item_repo.get(item_id)
        if item is None or item.watchlist_id != watchlist_id:
            return None
        alert = await self._alert_repo.create(
            watchlist_item_id=item_id, alert_type=alert_type,
            operator=operator, threshold_value=threshold_value,
        )
        return self._alert_to_dict(alert)

    async def list_alerts(self, watchlist_id: int, user_id: int) -> list[dict[str, Any]] | None:
        watchlist = await self._watchlist_repo.get(watchlist_id)
        if watchlist is None or watchlist.user_id != user_id:
            return None
        result = await self._session.execute(
            select(WatchlistAlert)
            .join(WatchlistItem, WatchlistAlert.watchlist_item_id == WatchlistItem.id)
            .where(WatchlistItem.watchlist_id == watchlist_id)
            .order_by(WatchlistAlert.created_at.desc())
        )
        alerts = result.scalars().all()
        return [self._alert_to_dict(a) for a in alerts]

    async def update_alert(
        self, alert_id: int, watchlist_id: int, user_id: int, **kwargs: Any,
    ) -> dict[str, Any] | None:
        watchlist = await self._watchlist_repo.get(watchlist_id)
        if watchlist is None or watchlist.user_id != user_id:
            return None
        alert = await self._alert_repo.get(alert_id)
        if alert is None:
            return None
        item = await self._item_repo.get(alert.watchlist_item_id)
        if item is None or item.watchlist_id != watchlist_id:
            return None
        allowed = {"alert_type", "operator", "threshold_value", "is_active"}
        update_kw = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
        if not update_kw:
            return self._alert_to_dict(alert)
        updated = await self._alert_repo.update(alert_id, **update_kw)
        return self._alert_to_dict(updated) if updated else None

    async def delete_alert(self, alert_id: int, watchlist_id: int, user_id: int) -> bool:
        watchlist = await self._watchlist_repo.get(watchlist_id)
        if watchlist is None or watchlist.user_id != user_id:
            return False
        alert = await self._alert_repo.get(alert_id)
        if alert is None:
            return False
        item = await self._item_repo.get(alert.watchlist_item_id)
        if item is None or item.watchlist_id != watchlist_id:
            return False
        return await self._alert_repo.delete(alert_id)

    # ── AI Monitoring ────────────────────────────────────────────────────

    async def run_ai_analysis(self, watchlist_id: int, user_id: int) -> list[dict[str, Any]]:
        watchlist = await self._watchlist_repo.get(watchlist_id)
        if watchlist is None or watchlist.user_id != user_id:
            return []
        items = await self._get_items_with_prices(watchlist_id)
        if not items:
            return []

        insights: list[dict[str, Any]] = []
        symbols_data = {s: d for s, d in items.items() if d}

        if symbols_data:
            insight = self._analyze_momentum(symbols_data, watchlist_id)
            if insight:
                insights.append(insight)

        if len(symbols_data) >= 2:
            insight = self._analyze_correlation(symbols_data, watchlist_id)
            if insight:
                insights.append(insight)

        insight = self._analyze_volatility(symbols_data, watchlist_id)
        if insight:
            insights.append(insight)

        insight = self._analyze_concentration(symbols_data, watchlist_id)
        if insight:
            insights.append(insight)

        for sym, data in symbols_data.items():
            insight = self._analyze_anomaly(sym, data, watchlist_id)
            if insight:
                insights.append(insight)

        for ins in insights:
            created = await self._insight_repo.create(
                watchlist_id=watchlist_id, insight_type=ins["insight_type"],
                content=ins["content"], score=ins["score"],
                symbol=ins.get("symbol"),
            )
            ins["id"] = created.id
            ins["generated_at"] = created.generated_at.isoformat() if created.generated_at else None

        return insights

    async def get_insights(
        self, watchlist_id: int, user_id: int,
        insight_type: str | None = None, skip: int = 0, limit: int = 50,
    ) -> list[dict[str, Any]] | None:
        watchlist = await self._watchlist_repo.get(watchlist_id)
        if watchlist is None or watchlist.user_id != user_id:
            return None
        query = select(WatchlistAiInsight).where(WatchlistAiInsight.watchlist_id == watchlist_id)
        if insight_type:
            query = query.where(WatchlistAiInsight.insight_type == insight_type)
        query = query.order_by(WatchlistAiInsight.generated_at.desc()).offset(skip).limit(limit)
        result = await self._session.execute(query)
        insights = result.scalars().all()
        return [self._insight_to_dict(i) for i in insights]

    async def delete_insight(self, insight_id: int, watchlist_id: int, user_id: int) -> bool:
        watchlist = await self._watchlist_repo.get(watchlist_id)
        if watchlist is None or watchlist.user_id != user_id:
            return False
        insight = await self._insight_repo.get(insight_id)
        if insight is None or insight.watchlist_id != watchlist_id:
            return False
        return await self._insight_repo.delete(insight_id)

    # ── Notifications ────────────────────────────────────────────────────

    async def list_notifications(
        self, user_id: int, is_read: bool | None = None,
        skip: int = 0, limit: int = 50,
    ) -> tuple[Sequence[Notification], int]:
        query = select(Notification).where(Notification.user_id == user_id)
        count_query = select(func.count()).select_from(Notification).where(Notification.user_id == user_id)
        if is_read is not None:
            query = query.where(Notification.is_read == is_read)
            count_query = count_query.where(Notification.is_read == is_read)
        total = (await self._session.execute(count_query)).scalar() or 0
        query = query.order_by(desc(Notification.created_at)).offset(skip).limit(limit)
        rows = (await self._session.execute(query)).scalars().all()
        return rows, total

    async def mark_notification_read(self, notification_id: int, user_id: int) -> bool:
        notif = await self._notification_repo.get(notification_id)
        if notif is None or notif.user_id != user_id:
            return False
        await self._notification_repo.update(notification_id, is_read=True)
        return True

    async def mark_all_notifications_read(self, user_id: int) -> int:
        result = await self._session.execute(
            sql_update(Notification)
            .where(and_(Notification.user_id == user_id, Notification.is_read == False))
            .values(is_read=True)
        )
        await self._session.flush()
        return result.rowcount

    async def delete_notification(self, notification_id: int, user_id: int) -> bool:
        notif = await self._notification_repo.get(notification_id)
        if notif is None or notif.user_id != user_id:
            return False
        return await self._notification_repo.delete(notification_id)

    async def create_notification(
        self, user_id: int, title: str, message: str,
        notification_type: str = "system",
        watchlist_id: int | None = None,
        alert_id: int | None = None,
    ) -> dict[str, Any]:
        notif = await self._notification_repo.create(
            user_id=user_id, title=title, message=message,
            notification_type=notification_type,
            watchlist_id=watchlist_id, alert_id=alert_id,
        )
        return self._notification_to_dict(notif)

    # ── Internal helpers ─────────────────────────────────────────────────

    async def _get_items_with_prices(self, watchlist_id: int) -> dict[str, dict[str, Any]]:
        result = await self._session.execute(
            select(WatchlistItem).where(WatchlistItem.watchlist_id == watchlist_id)
        )
        items = result.scalars().all()
        end = date.today()
        start = end - timedelta(days=60)

        symbols_data: dict[str, dict[str, Any]] = {}
        for item in items:
            prices = await self._session.execute(
                select(DailyPrice.close, DailyPrice.trade_date)
                .where(DailyPrice.symbol == item.symbol, DailyPrice.trade_date.between(start, end))
                .order_by(DailyPrice.trade_date)
            )
            rows = prices.all()
            if len(rows) >= 5:
                close_prices = [float(r.close) for r in rows]
                returns = [(close_prices[i] - close_prices[i - 1]) / close_prices[i - 1] for i in range(1, len(close_prices))]
                symbols_data[item.symbol] = {
                    "prices": close_prices,
                    "returns": returns,
                    "current_price": close_prices[-1],
                    "change_5d": (close_prices[-1] - close_prices[-min(6, len(close_prices))]) / close_prices[-min(6, len(close_prices))] * 100,
                    "change_20d": (close_prices[-1] - close_prices[-min(21, len(close_prices))]) / close_prices[-min(21, len(close_prices))] * 100,
                }
        return symbols_data

    def _analyze_momentum(self, symbols_data: dict[str, dict], watchlist_id: int) -> dict[str, Any] | None:
        strongest = max(symbols_data.items(), key=lambda x: x[1]["change_5d"])
        weakest = min(symbols_data.items(), key=lambda x: x[1]["change_5d"])
        if strongest[1]["change_5d"] > 5:
            return {
                "insight_type": "momentum_alert",
                "content": f"{strongest[0]} showing strong momentum: +{strongest[1]['change_5d']:.1f}% (5d).",
                "score": min(100, strongest[1]["change_5d"] * 2),
                "symbol": strongest[0],
            }
        if weakest[1]["change_5d"] < -5:
            return {
                "insight_type": "momentum_alert",
                "content": f"{weakest[0]} showing weakness: {weakest[1]['change_5d']:.1f}% (5d).",
                "score": min(100, abs(weakest[1]["change_5d"]) * 2),
                "symbol": weakest[0],
            }
        return None

    def _analyze_correlation(self, symbols_data: dict[str, dict], watchlist_id: int) -> dict[str, Any] | None:
        symbols = list(symbols_data.keys())
        max_corr = 0.0
        max_pair = (symbols[0], symbols[1])
        for i in range(len(symbols)):
            for j in range(i + 1, len(symbols)):
                r = self._correlate(symbols_data[symbols[i]]["returns"], symbols_data[symbols[j]]["returns"])
                if abs(r) > max_corr:
                    max_corr = abs(r)
                    max_pair = (symbols[i], symbols[j])
        if max_corr > 0.85:
            return {
                "insight_type": "correlation_shift",
                "content": f"High correlation ({max_corr:.2f}) between {max_pair[0]} and {max_pair[1]} — reduced diversification benefit.",
                "score": min(100, max_corr * 100),
                "symbol": None,
            }
        if max_corr < 0.3 and len(symbols) > 2:
            return {
                "insight_type": "correlation_shift",
                "content": f"Low correlation ({max_corr:.2f}) between {max_pair[0]} and {max_pair[1]} — good diversification.",
                "score": min(100, (1 - max_corr) * 50),
                "symbol": None,
            }
        return None

    def _analyze_volatility(self, symbols_data: dict[str, dict], watchlist_id: int) -> dict[str, Any] | None:
        vols: dict[str, float] = {}
        for sym, data in symbols_data.items():
            rets = data["returns"]
            mu = sum(rets) / len(rets)
            variance = sum((r - mu) ** 2 for r in rets) / len(rets)
            vols[sym] = math.sqrt(variance) * math.sqrt(252) * 100
        if not vols:
            return None
        max_vol_sym = max(vols, key=vols.get)
        max_vol = vols[max_vol_sym]
        if max_vol > 50:
            return {
                "insight_type": "volatility_alert",
                "content": f"{max_vol_sym} has elevated volatility ({max_vol:.1f}% annualized). Consider reviewing position size.",
                "score": min(100, max_vol),
                "symbol": max_vol_sym,
            }
        return None

    def _analyze_concentration(self, symbols_data: dict[str, dict], watchlist_id: int) -> dict[str, Any] | None:
        prices = {s: d["current_price"] for s, d in symbols_data.items() if d["current_price"] > 0}
        if not prices:
            return None
        total = sum(prices.values())
        weights = [v / total for v in prices.values()]
        hhi = sum(w ** 2 for w in weights)
        if hhi > 0.3:
            top = max(prices, key=prices.get)
            return {
                "insight_type": "sector_trend",
                "content": f"Watchlist is heavily concentrated in {top} ({prices[top]/total*100:.0f}% weight). HHI: {hhi:.2f}.",
                "score": min(100, hhi * 100),
                "symbol": top,
            }
        return None

    def _analyze_anomaly(self, symbol: str, data: dict[str, Any], watchlist_id: int) -> dict[str, Any] | None:
        rets = data["returns"]
        if len(rets) < 10:
            return None
        mu = sum(rets) / len(rets)
        variance = sum((r - mu) ** 2 for r in rets) / len(rets)
        std = math.sqrt(variance)
        latest_ret = rets[-1]
        if abs(latest_ret) > 3 * std:
            direction = "surge" if latest_ret > 0 else "drop"
            return {
                "insight_type": "anomaly",
                "content": f"Unusual {direction} detected in {symbol}: {latest_ret*100:.2f}% ({(latest_ret - mu)/std if std > 0 else 0:.1f}σ).",
                "score": min(100, abs(latest_ret) * 500),
                "symbol": symbol,
            }
        return None

    def _correlate(self, x: list[float], y: list[float]) -> float:
        n = min(len(x), len(y))
        if n < 5:
            return 0.0
        x, y = x[-n:], y[-n:]
        mx = sum(x) / n
        my = sum(y) / n
        num = sum((x[i] - mx) * (y[i] - my) for i in range(n))
        dx = math.sqrt(sum((xi - mx) ** 2 for xi in x))
        dy = math.sqrt(sum((yi - my) ** 2 for yi in y))
        if dx * dy == 0:
            return 0.0
        return num / (dx * dy)

    # ── Serialization helpers ────────────────────────────────────────────

    def _folder_to_dict(self, folder: WatchlistFolder) -> dict[str, Any]:
        return {
            "id": folder.id,
            "user_id": folder.user_id,
            "name": folder.name,
            "description": folder.description,
            "parent_id": folder.parent_id,
            "color": folder.color,
            "sort_order": folder.sort_order,
            "created_at": folder.created_at.isoformat() if folder.created_at else None,
        }

    def _watchlist_to_dict(self, wl: Watchlist) -> dict[str, Any]:
        return {
            "id": wl.id,
            "user_id": wl.user_id,
            "folder_id": wl.folder_id,
            "name": wl.name,
            "description": wl.description,
            "is_default": wl.is_default,
            "created_at": wl.created_at.isoformat() if wl.created_at else None,
        }

    def _item_to_dict(self, item: WatchlistItem) -> dict[str, Any]:
        tags = []
        if "tags" not in instance_state(item).unloaded:
            tags = [{"id": t.id, "name": t.name, "color": t.color} for t in (item.tags or [])]
        return {
            "id": item.id,
            "watchlist_id": item.watchlist_id,
            "symbol": item.symbol,
            "notes": item.notes,
            "sort_order": item.sort_order,
            "added_at": item.added_at.isoformat() if item.added_at else None,
            "tags": tags,
        }

    def _tag_to_dict(self, tag: WatchlistTag) -> dict[str, Any]:
        return {
            "id": tag.id,
            "name": tag.name,
            "color": tag.color,
        }

    def _alert_to_dict(self, alert: WatchlistAlert) -> dict[str, Any]:
        return {
            "id": alert.id,
            "watchlist_item_id": alert.watchlist_item_id,
            "alert_type": alert.alert_type,
            "operator": alert.operator,
            "threshold_value": alert.threshold_value,
            "is_active": alert.is_active,
            "last_triggered_at": alert.last_triggered_at.isoformat() if alert.last_triggered_at else None,
            "created_at": alert.created_at.isoformat() if alert.created_at else None,
        }

    def _insight_to_dict(self, insight: WatchlistAiInsight) -> dict[str, Any]:
        return {
            "id": insight.id,
            "watchlist_id": insight.watchlist_id,
            "insight_type": insight.insight_type,
            "content": insight.content,
            "score": insight.score,
            "symbol": insight.symbol,
            "generated_at": insight.generated_at.isoformat() if insight.generated_at else None,
        }

    def _notification_to_dict(self, notif: Notification) -> dict[str, Any]:
        return {
            "id": notif.id,
            "user_id": notif.user_id,
            "watchlist_id": notif.watchlist_id,
            "alert_id": notif.alert_id,
            "title": notif.title,
            "message": notif.message,
            "notification_type": notif.notification_type,
            "is_read": notif.is_read,
            "created_at": notif.created_at.isoformat() if notif.created_at else None,
        }
