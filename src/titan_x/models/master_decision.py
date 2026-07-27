from datetime import date

from sqlalchemy import Boolean, Date, Float, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from titan_x.db.base import Base
from titan_x.db.mixins import PrimaryKeyMixin, TimestampMixin


class MasterDecision(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "master_decisions"
    __table_args__ = (
        UniqueConstraint("symbol", "as_of_date", name="uq_master_decision_sym_date"),
        Index("ix_md_symbol", "symbol"),
        Index("ix_md_date", "as_of_date"),
        Index("ix_md_score", "final_ai_score"),
        Index("ix_md_recommendation", "recommendation"),
    )

    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)

    final_ai_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_level: Mapped[str | None] = mapped_column(String(16), nullable=True)
    recommendation: Mapped[str | None] = mapped_column(String(16), nullable=True)

    is_weak: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    rejection_reason: Mapped[str | None] = mapped_column(String(256), nullable=True)

    financial_analysis_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    corporate_governance_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    institutional_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    valuation_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    momentum_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    liquidity_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    technical_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    macro_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    global_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    pattern_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    regime_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    prediction_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    engine_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    evidence_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    decision_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
