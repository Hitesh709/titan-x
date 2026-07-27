from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from titan_x.db.base import Base
from titan_x.db.mixins import PrimaryKeyMixin, TimestampMixin


class TradeJournal(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "trade_journal"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    direction: Mapped[str] = mapped_column(String(8), nullable=False, default="long")
    entry_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    exit_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    exit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)

    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    emotion_before: Mapped[str | None] = mapped_column(String(64), nullable=True)
    emotion_during: Mapped[str | None] = mapped_column(String(64), nullable=True)
    emotion_after: Mapped[str | None] = mapped_column(String(64), nullable=True)
    exit_reason: Mapped[str | None] = mapped_column(String(128), nullable=True)
    exit_analysis: Mapped[str | None] = mapped_column(Text, nullable=True)
    pnl_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    pnl_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    lessons_learned: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[str | None] = mapped_column(String(256), nullable=True)
    setup_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    mistake: Mapped[str | None] = mapped_column(String(256), nullable=True)
    screenshot_url: Mapped[str | None] = mapped_column(String(512), nullable=True)

    is_closed: Mapped[bool] = mapped_column(default=False, nullable=False)
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
