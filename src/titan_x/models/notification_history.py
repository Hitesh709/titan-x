from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from titan_x.db.base import Base
from titan_x.db.mixins import PrimaryKeyMixin, TimestampMixin


class NotificationHistory(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "notification_history"
    __table_args__ = (
        Index("ix_notification_history_user_status", "user_id", "status"),
        Index("ix_notification_history_created_at", "created_at"),
    )

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    notification_type: Mapped[str] = mapped_column(String(32), nullable=False)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    reference_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reference_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    delivery_logs: Mapped[list["DeliveryLog"]] = relationship(
        back_populates="notification", cascade="all, delete-orphan",
    )


class DeliveryLog(PrimaryKeyMixin, Base):
    __tablename__ = "notification_delivery_logs"
    __table_args__ = (
        Index("ix_delivery_log_notification", "notification_history_id"),
        Index("ix_delivery_log_status", "status"),
    )

    notification_history_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("notification_history.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    channel_name: Mapped[str] = mapped_column(String(32), nullable=False)
    recipient: Mapped[str] = mapped_column(String(256), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    notification: Mapped["NotificationHistory"] = relationship(back_populates="delivery_logs")


class NotificationRetry(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "notification_retry_queue"
    __table_args__ = (
        Index("ix_retry_queue_next_retry", "next_retry_at"),
        Index("ix_retry_queue_status", "status"),
    )

    notification_history_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("notification_history.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    channel_name: Mapped[str] = mapped_column(String(32), nullable=False)
    recipient: Mapped[str] = mapped_column(String(256), nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_retry_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
