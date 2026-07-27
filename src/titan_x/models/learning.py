from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from titan_x.db.base import Base
from titan_x.db.mixins import PrimaryKeyMixin, TimestampMixin


class LearningHistory(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "learning_history"
    __table_args__ = (
        Index("ix_lh_symbol_date", "symbol", "as_of_date"),
        Index("ix_lh_evaluated_at", "evaluated_at"),
    )

    prediction_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("predictions.id", ondelete="SET NULL"), nullable=True)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    horizon_days: Mapped[int] = mapped_column(Integer, nullable=False)
    predicted_return_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    actual_return_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    predicted_signal: Mapped[str | None] = mapped_column(String(16), nullable=True)
    actual_signal: Mapped[str | None] = mapped_column(String(16), nullable=True)
    predicted_direction: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actual_direction: Mapped[int | None] = mapped_column(Integer, nullable=True)
    was_correct: Mapped[bool | None] = mapped_column(default=None, nullable=True)
    absolute_error: Mapped[float | None] = mapped_column(Float, nullable=True)
    squared_error: Mapped[float | None] = mapped_column(Float, nullable=True)
    predicted_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    data_sources_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ModelWeight(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "model_weights"
    __table_args__ = (
        Index("ix_mw_source", "source_name"),
        Index("ix_mw_symbol_source", "symbol", "source_name"),
    )

    source_name: Mapped[str] = mapped_column(String(32), nullable=False)
    symbol: Mapped[str | None] = mapped_column(String(16), nullable=True)
    weight: Mapped[float] = mapped_column(Float, nullable=False)
    accuracy: Mapped[float | None] = mapped_column(Float, nullable=True)
    precision_bullish: Mapped[float | None] = mapped_column(Float, nullable=True)
    recall_bullish: Mapped[float | None] = mapped_column(Float, nullable=True)
    precision_bearish: Mapped[float | None] = mapped_column(Float, nullable=True)
    recall_bearish: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_predictions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    correct_predictions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    avg_return_when_correct: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_return_when_wrong: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_updated: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
