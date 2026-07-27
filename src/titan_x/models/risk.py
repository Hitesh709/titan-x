from datetime import date

from sqlalchemy import BigInteger, Date, Float, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from titan_x.db.base import Base
from titan_x.db.mixins import PrimaryKeyMixin, TimestampMixin


class RiskMetrics(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "risk_metrics"
    __table_args__ = (
        UniqueConstraint("symbol", "as_of_date", name="uq_risk_metrics_symbol_date"),
        Index("ix_risk_metrics_symbol", "symbol"),
        Index("ix_risk_metrics_date", "as_of_date"),
    )

    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)

    max_drawdown_1m: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_drawdown_3m: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_drawdown_6m: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_drawdown_1y: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_drawdown_ytd: Mapped[float | None] = mapped_column(Float, nullable=True)

    volatility_20d: Mapped[float | None] = mapped_column(Float, nullable=True)
    volatility_60d: Mapped[float | None] = mapped_column(Float, nullable=True)
    volatility_252d: Mapped[float | None] = mapped_column(Float, nullable=True)

    avg_daily_volume_20d: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    avg_dollar_volume_20d: Mapped[float | None] = mapped_column(Float, nullable=True)
    liquidity_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    gap_frequency_20d: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_gap_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_gap_pct: Mapped[float | None] = mapped_column(Float, nullable=True)

    event_risk_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    news_count_30d: Mapped[int | None] = mapped_column(Integer, nullable=True)

    composite_risk_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_rating: Mapped[str | None] = mapped_column(String(16), nullable=True)

    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class PortfolioRisk(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "portfolio_risk"
    __table_args__ = (
        UniqueConstraint("portfolio_id", "as_of_date", name="uq_portfolio_risk_id_date"),
        Index("ix_portfolio_risk_id", "portfolio_id"),
    )

    portfolio_id: Mapped[str] = mapped_column(String(64), nullable=False)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    num_positions: Mapped[int] = mapped_column(Integer, nullable=False)
    total_value: Mapped[float | None] = mapped_column(Float, nullable=True)

    weighted_volatility: Mapped[float | None] = mapped_column(Float, nullable=True)
    portfolio_var_95: Mapped[float | None] = mapped_column(Float, nullable=True)
    portfolio_var_99: Mapped[float | None] = mapped_column(Float, nullable=True)
    expected_shortfall_95: Mapped[float | None] = mapped_column(Float, nullable=True)
    diversification_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    concentration_risk: Mapped[float | None] = mapped_column(Float, nullable=True)
    weighted_drawdown: Mapped[float | None] = mapped_column(Float, nullable=True)
    weighted_gap_risk: Mapped[float | None] = mapped_column(Float, nullable=True)

    composite_risk_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_rating: Mapped[str | None] = mapped_column(String(16), nullable=True)

    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
