from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from titan_x.db.base import Base
from titan_x.db.mixins import PrimaryKeyMixin, TimestampMixin


class WatchlistFolder(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "watchlist_folders"

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("watchlist_folders.id", ondelete="SET NULL"), nullable=True)
    color: Mapped[str | None] = mapped_column(String(7), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    watchlists: Mapped[list["Watchlist"]] = relationship(back_populates="folder", cascade="all, delete-orphan")
    children: Mapped[list["WatchlistFolder"]] = relationship(back_populates="parent", cascade="all, delete-orphan")
    parent: Mapped["WatchlistFolder | None"] = relationship(back_populates="children", remote_side="WatchlistFolder.id")


class Watchlist(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "watchlists"
    __table_args__ = (
        Index("ix_watchlist_user_name", "user_id", "name"),
    )

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    folder_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("watchlist_folders.id", ondelete="SET NULL"), nullable=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    folder: Mapped["WatchlistFolder | None"] = relationship(back_populates="watchlists")
    items: Mapped[list["WatchlistItem"]] = relationship(back_populates="watchlist", cascade="all, delete-orphan")
    ai_insights: Mapped[list["WatchlistAiInsight"]] = relationship(back_populates="watchlist", cascade="all, delete-orphan")


class WatchlistItem(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "watchlist_items"
    __table_args__ = (
        Index("ix_watchlist_item_watchlist_symbol", "watchlist_id", "symbol"),
    )

    watchlist_id: Mapped[int] = mapped_column(Integer, ForeignKey("watchlists.id", ondelete="CASCADE"), nullable=False)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    watchlist: Mapped["Watchlist"] = relationship(back_populates="items")
    tags: Mapped[list["WatchlistTag"]] = relationship(
        secondary="watchlist_item_tags", back_populates="items",
    )
    alerts: Mapped[list["WatchlistAlert"]] = relationship(back_populates="item", cascade="all, delete-orphan")


class WatchlistTag(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "watchlist_tags"

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    color: Mapped[str | None] = mapped_column(String(7), nullable=True)

    items: Mapped[list["WatchlistItem"]] = relationship(
        secondary="watchlist_item_tags", back_populates="tags",
    )


class WatchlistItemTag(Base):
    __tablename__ = "watchlist_item_tags"

    watchlist_item_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("watchlist_items.id", ondelete="CASCADE"), primary_key=True,
    )
    watchlist_tag_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("watchlist_tags.id", ondelete="CASCADE"), primary_key=True,
    )


class WatchlistAlert(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "watchlist_alerts"

    watchlist_item_id: Mapped[int] = mapped_column(Integer, ForeignKey("watchlist_items.id", ondelete="CASCADE"), nullable=False, index=True)
    alert_type: Mapped[str] = mapped_column(String(32), nullable=False)
    operator: Mapped[str] = mapped_column(String(8), nullable=False)
    threshold_value: Mapped[float] = mapped_column(Float, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    item: Mapped["WatchlistItem"] = relationship(back_populates="alerts")


class WatchlistAiInsight(PrimaryKeyMixin, Base):
    __tablename__ = "watchlist_ai_insights"
    __table_args__ = (
        Index("ix_watchlist_ai_insight_watchlist", "watchlist_id"),
    )

    watchlist_id: Mapped[int] = mapped_column(Integer, ForeignKey("watchlists.id", ondelete="CASCADE"), nullable=False)
    insight_type: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    symbol: Mapped[str | None] = mapped_column(String(16), nullable=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    watchlist: Mapped["Watchlist"] = relationship(back_populates="ai_insights")


class Notification(PrimaryKeyMixin, Base):
    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notification_user_read", "user_id", "is_read"),
    )

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    watchlist_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("watchlists.id", ondelete="SET NULL"), nullable=True)
    alert_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("watchlist_alerts.id", ondelete="SET NULL"), nullable=True)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    notification_type: Mapped[str] = mapped_column(String(32), nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class WatchlistMonitorEvent(PrimaryKeyMixin, Base):
    __tablename__ = "watchlist_monitor_events"
    __table_args__ = (
        Index("ix_wme_user_type", "user_id", "event_type"),
        Index("ix_wme_symbol_type", "symbol", "event_type"),
    )

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    watchlist_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("watchlists.id", ondelete="CASCADE"), nullable=True)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(16), default="info", nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    previous_value: Mapped[str | None] = mapped_column(String(64), nullable=True)
    current_value: Mapped[str | None] = mapped_column(String(64), nullable=True)
    change_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    data_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
