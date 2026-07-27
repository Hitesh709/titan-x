from datetime import date

from sqlalchemy import Boolean, Date, Float, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from titan_x.db.base import Base
from titan_x.db.mixins import PrimaryKeyMixin, TimestampMixin


class StockRanking(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "stock_rankings"
    __table_args__ = (
        UniqueConstraint("symbol", "as_of_date", name="uq_ranking_sym_date"),
        Index("ix_ranking_score", "composite_score"),
        Index("ix_ranking_tier", "tier"),
        Index("ix_ranking_symbol", "symbol"),
    )

    as_of_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    company_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    sector: Mapped[str | None] = mapped_column(String(128), nullable=True)

    composite_score: Mapped[float] = mapped_column(Float, nullable=False)
    financial_health_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    valuation_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    momentum_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    liquidity_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_adjusted_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    corporate_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    institutional_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    tier: Mapped[str] = mapped_column(String(16), nullable=False)
    is_best_opportunity: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    explanation_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
