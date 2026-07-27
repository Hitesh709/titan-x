from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from titan_x.db.base import Base
from titan_x.db.mixins import PrimaryKeyMixin, TimestampMixin


class CorporateActionDetection(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "corporate_action_detections"
    __table_args__ = (
        Index("ix_cad_symbol_status", "symbol", "status"),
        Index("ix_cad_type_date", "detected_type", "detected_date"),
    )

    symbol: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    detected_type: Mapped[str] = mapped_column(String(32), nullable=False)
    detected_date: Mapped[date] = mapped_column(Date, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)

    estimated_numerator: Mapped[float | None] = mapped_column(Float, nullable=True)
    estimated_denominator: Mapped[float | None] = mapped_column(Float, nullable=True)
    estimated_dividend_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    estimated_premium: Mapped[float | None] = mapped_column(Float, nullable=True)
    estimated_issue_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_symbol: Mapped[str | None] = mapped_column(String(16), nullable=True)

    price_before: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_after: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume_spike_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    signal_details_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    confirmed_action_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("corporate_actions.id", ondelete="SET NULL"), nullable=True,
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
