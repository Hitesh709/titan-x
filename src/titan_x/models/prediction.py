from datetime import date

from sqlalchemy import Date, Float, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from titan_x.db.base import Base
from titan_x.db.mixins import PrimaryKeyMixin, TimestampMixin


class Prediction(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "predictions"
    __table_args__ = (
        UniqueConstraint("symbol", "as_of_date", name="uq_prediction_symbol_date"),
        Index("ix_prediction_symbol", "symbol"),
        Index("ix_prediction_date", "as_of_date"),
        Index("ix_prediction_overall_signal", "overall_signal"),
    )

    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)

    probability_5d: Mapped[float | None] = mapped_column(Float, nullable=True)
    expected_return_5d: Mapped[float | None] = mapped_column(Float, nullable=True)
    expected_drawdown_5d: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence_5d: Mapped[float | None] = mapped_column(Float, nullable=True)
    signal_5d: Mapped[str | None] = mapped_column(String(16), nullable=True)

    probability_10d: Mapped[float | None] = mapped_column(Float, nullable=True)
    expected_return_10d: Mapped[float | None] = mapped_column(Float, nullable=True)
    expected_drawdown_10d: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence_10d: Mapped[float | None] = mapped_column(Float, nullable=True)
    signal_10d: Mapped[str | None] = mapped_column(String(16), nullable=True)

    probability_15d: Mapped[float | None] = mapped_column(Float, nullable=True)
    expected_return_15d: Mapped[float | None] = mapped_column(Float, nullable=True)
    expected_drawdown_15d: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence_15d: Mapped[float | None] = mapped_column(Float, nullable=True)
    signal_15d: Mapped[str | None] = mapped_column(String(16), nullable=True)

    probability_20d: Mapped[float | None] = mapped_column(Float, nullable=True)
    expected_return_20d: Mapped[float | None] = mapped_column(Float, nullable=True)
    expected_drawdown_20d: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence_20d: Mapped[float | None] = mapped_column(Float, nullable=True)
    signal_20d: Mapped[str | None] = mapped_column(String(16), nullable=True)

    probability_30d: Mapped[float | None] = mapped_column(Float, nullable=True)
    expected_return_30d: Mapped[float | None] = mapped_column(Float, nullable=True)
    expected_drawdown_30d: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence_30d: Mapped[float | None] = mapped_column(Float, nullable=True)
    signal_30d: Mapped[str | None] = mapped_column(String(16), nullable=True)

    holding_period: Mapped[int | None] = mapped_column(Integer, nullable=True)
    overall_signal: Mapped[str | None] = mapped_column(String(16), nullable=True)
    overall_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    overall_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    horizon_summary_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_sources_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
