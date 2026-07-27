from datetime import date

from sqlalchemy import Date, Float, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from titan_x.db.base import Base
from titan_x.db.mixins import PrimaryKeyMixin, TimestampMixin


class ExplainabilityAnalysis(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "explainability_analyses"
    __table_args__ = (
        UniqueConstraint("symbol", "as_of_date", name="uq_explain_symbol_date"),
        Index("ix_explain_symbol", "symbol"),
        Index("ix_explain_date", "as_of_date"),
        Index("ix_explain_overall_signal", "overall_signal"),
    )

    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)

    why_buy_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    why_not_buy_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    strengths_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    weaknesses_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    risk_factors_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    historical_evidence_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    overall_signal: Mapped[str | None] = mapped_column(String(16), nullable=True)
    overall_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    overall_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
