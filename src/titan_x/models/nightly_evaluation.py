from datetime import date

from sqlalchemy import Boolean, Date, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from titan_x.db.base import Base
from titan_x.db.mixins import PrimaryKeyMixin, TimestampMixin


class NightlyEvaluation(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "nightly_evaluations"
    __table_args__ = (
        Index("ix_ne_eval_date", "evaluation_date"),
        Index("ix_ne_status", "status"),
    )

    evaluation_date: Mapped[date] = mapped_column(Date, nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="running")

    total_predictions: Mapped[int] = mapped_column(Integer, default=0)
    correct_predictions: Mapped[int] = mapped_column(Integer, default=0)
    incorrect_predictions: Mapped[int] = mapped_column(Integer, default=0)
    accuracy: Mapped[float | None] = mapped_column(Float, nullable=True)

    mae: Mapped[float | None] = mapped_column(Float, nullable=True)
    rmse: Mapped[float | None] = mapped_column(Float, nullable=True)
    bias_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    bias_direction: Mapped[str | None] = mapped_column(String(16), nullable=True)

    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    failure_threshold_pct: Mapped[float] = mapped_column(Float, default=10.0)

    weight_adjustments_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    errors_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class PredictionError(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "prediction_errors"
    __table_args__ = (
        Index("ix_pe_evaluation_id", "evaluation_id"),
        Index("ix_pe_symbol", "symbol"),
        Index("ix_pe_as_of_date", "as_of_date"),
        Index("ix_pe_is_failure", "is_failure"),
    )

    evaluation_id: Mapped[int] = mapped_column(ForeignKey("nightly_evaluations.id"), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    horizon: Mapped[int] = mapped_column(Integer, nullable=False)

    signal: Mapped[str | None] = mapped_column(String(16), nullable=True)
    predicted_return_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    actual_return_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    abs_error_pct: Mapped[float | None] = mapped_column(Float, nullable=True)

    predicted_direction: Mapped[str | None] = mapped_column(String(16), nullable=True)
    actual_direction: Mapped[str | None] = mapped_column(String(16), nullable=True)
    was_correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    is_failure: Mapped[bool] = mapped_column(Boolean, default=False)

    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
