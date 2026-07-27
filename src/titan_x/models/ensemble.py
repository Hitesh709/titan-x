from datetime import date

from sqlalchemy import Date, Float, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from titan_x.db.base import Base
from titan_x.db.mixins import PrimaryKeyMixin, TimestampMixin


class EnsemblePrediction(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ensemble_predictions"
    __table_args__ = (
        UniqueConstraint("symbol", "as_of_date", name="uq_ensemble_symbol_date"),
        Index("ix_ensemble_symbol", "symbol"),
        Index("ix_ensemble_date", "as_of_date"),
        Index("ix_ensemble_signal", "ensemble_signal"),
    )

    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)

    technical_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    technical_signal: Mapped[str | None] = mapped_column(String(16), nullable=True)
    technical_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    fundamental_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    fundamental_signal: Mapped[str | None] = mapped_column(String(16), nullable=True)
    fundamental_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    news_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    news_signal: Mapped[str | None] = mapped_column(String(16), nullable=True)
    news_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    macro_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    macro_signal: Mapped[str | None] = mapped_column(String(16), nullable=True)
    macro_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    risk_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_signal: Mapped[str | None] = mapped_column(String(16), nullable=True)
    risk_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    pattern_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    pattern_signal: Mapped[str | None] = mapped_column(String(16), nullable=True)
    pattern_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    ensemble_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    ensemble_signal: Mapped[str | None] = mapped_column(String(16), nullable=True)
    ensemble_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    agreement_level: Mapped[str | None] = mapped_column(String(16), nullable=True)
    vote_breakdown_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    weights_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
