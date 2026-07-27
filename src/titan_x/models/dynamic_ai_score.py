from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from titan_x.db.base import Base
from titan_x.db.mixins import PrimaryKeyMixin, TimestampMixin


class DynamicWeight(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "dynamic_ai_weights"
    __table_args__ = (
        UniqueConstraint("source_name", name="uq_dw_source"),
        Index("ix_dw_source", "source_name"),
    )

    source_name: Mapped[str] = mapped_column(String(30), nullable=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=0.15)
    performance_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_predictions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    correct_predictions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    adjusted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    def accuracy(self) -> float:
        if self.total_predictions == 0:
            return 0.0
        return self.correct_predictions / self.total_predictions * 100


class DynamicAIScore(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "dynamic_ai_scores"
    __table_args__ = (
        UniqueConstraint("symbol", "as_of_date", name="uq_dai_symbol_date"),
        Index("ix_dai_symbol", "symbol"),
        Index("ix_dai_date", "as_of_date"),
        Index("ix_dai_signal", "combined_signal"),
        Index("ix_dai_score", "combined_score"),
    )

    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)

    technical_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    technical_signal: Mapped[str | None] = mapped_column(String(20), nullable=True)
    technical_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    fundamental_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    fundamental_signal: Mapped[str | None] = mapped_column(String(20), nullable=True)
    fundamental_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    news_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    news_signal: Mapped[str | None] = mapped_column(String(20), nullable=True)
    news_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    macro_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    macro_signal: Mapped[str | None] = mapped_column(String(20), nullable=True)
    macro_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    liquidity_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    liquidity_signal: Mapped[str | None] = mapped_column(String(20), nullable=True)
    liquidity_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    risk_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_signal: Mapped[str | None] = mapped_column(String(20), nullable=True)
    risk_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    market_regime_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    market_regime_signal: Mapped[str | None] = mapped_column(String(20), nullable=True)
    market_regime_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    combined_score: Mapped[float] = mapped_column(Float, nullable=False)
    combined_signal: Mapped[str] = mapped_column(String(20), nullable=False)
    combined_confidence: Mapped[float] = mapped_column(Float, nullable=False)

    weights_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_signals_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
