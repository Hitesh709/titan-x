from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, Float, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from titan_x.db.base import Base
from titan_x.db.mixins import PrimaryKeyMixin, TimestampMixin


class EventDetection(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "event_detections"
    __table_args__ = (
        Index("ix_evt_symbol", "symbol"),
        Index("ix_evt_type", "event_type"),
        Index("ix_evt_date", "detected_at"),
        Index("ix_evt_sym_date", "symbol", "detected_at"),
    )

    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    event_type: Mapped[str] = mapped_column(String(16), nullable=False)
    event_label: Mapped[str] = mapped_column(String(64), nullable=False)
    impact_score: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    event_date: Mapped[date] = mapped_column(Date, nullable=False)
    related_symbols: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_resolved: Mapped[bool] = mapped_column(default=False, nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    article_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("news_articles.id", ondelete="SET NULL"), nullable=True,
    )


class EventImpactHistory(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "event_impact_history"
    __table_args__ = (
        Index("ix_eih_symbol", "symbol"),
        Index("ix_eih_date", "impact_date"),
        Index("ix_eih_type", "event_type"),
    )

    symbol: Mapped[str] = mapped_column(String(16), nullable=False, default="MARKET")
    impact_date: Mapped[date] = mapped_column(Date, nullable=False)
    event_type: Mapped[str] = mapped_column(String(16), default="all", nullable=False)
    total_positive: Mapped[int] = mapped_column(default=0, nullable=False)
    total_negative: Mapped[int] = mapped_column(default=0, nullable=False)
    total_neutral: Mapped[int] = mapped_column(default=0, nullable=False)
    avg_positive_impact: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_negative_impact: Mapped[float | None] = mapped_column(Float, nullable=True)
    net_impact_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    top_events_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
