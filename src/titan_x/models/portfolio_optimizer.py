from datetime import date

from sqlalchemy import Boolean, Date, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from titan_x.db.base import Base
from titan_x.db.mixins import PrimaryKeyMixin, TimestampMixin


class PortfolioOptimization(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "portfolio_optimizations"
    __table_args__ = (
        Index("ix_po_portfolio", "portfolio_id"),
        Index("ix_po_date", "optimization_date"),
    )

    portfolio_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False,
    )
    optimization_date: Mapped[date] = mapped_column(Date, nullable=False)
    strategy: Mapped[str] = mapped_column(String(32), nullable=False)
    expected_return: Mapped[float | None] = mapped_column(Float, nullable=True)
    expected_volatility: Mapped[float | None] = mapped_column(Float, nullable=True)
    sharpe_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    diversification_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    sector_balance_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_holdings: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_valid: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    constraints_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    report_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class OptimizationAllocation(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "optimization_allocations"
    __table_args__ = (
        UniqueConstraint("optimization_id", "symbol", name="uq_oa_opt_sym"),
        Index("ix_oa_opt_id", "optimization_id"),
    )

    optimization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("portfolio_optimizations.id", ondelete="CASCADE"), nullable=False,
    )
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    sector: Mapped[str | None] = mapped_column(String(128), nullable=True)
    allocation_pct: Mapped[float] = mapped_column(Float, nullable=False)
    expected_return: Mapped[float | None] = mapped_column(Float, nullable=True)
    expected_risk: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight: Mapped[float] = mapped_column(Float, nullable=False)
    rank: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
