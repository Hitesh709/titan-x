from datetime import date

from sqlalchemy import Date, Float, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from titan_x.db.base import Base
from titan_x.db.mixins import PrimaryKeyMixin, TimestampMixin


class MarketRegime(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "market_regimes"
    __table_args__ = (
        UniqueConstraint("symbol", "as_of_date", name="uq_regime_symbol_date"),
        Index("ix_regime_symbol", "symbol"),
        Index("ix_regime_date", "as_of_date"),
    )

    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)

    trend_regime: Mapped[str | None] = mapped_column(String(16), nullable=True)
    volatility_regime: Mapped[str | None] = mapped_column(String(16), nullable=True)
    sentiment_regime: Mapped[str | None] = mapped_column(String(16), nullable=True)

    trend_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    volatility_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    sentiment_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    momentum_20d: Mapped[float | None] = mapped_column(Float, nullable=True)
    momentum_50d: Mapped[float | None] = mapped_column(Float, nullable=True)
    sma_50: Mapped[float | None] = mapped_column(Float, nullable=True)
    sma_200: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_vs_sma_200_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    volatility_20d: Mapped[float | None] = mapped_column(Float, nullable=True)
    volatility_60d_avg: Mapped[float | None] = mapped_column(Float, nullable=True)
    adv_decl_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    new_highs_vs_lows: Mapped[float | None] = mapped_column(Float, nullable=True)

    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    details_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class RegimeSignal(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "regime_signals"
    __table_args__ = (
        UniqueConstraint("symbol", "as_of_date", name="uq_signal_symbol_date"),
        Index("ix_signal_symbol", "symbol"),
        Index("ix_signal_date", "as_of_date"),
    )

    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    regime_id: Mapped[int] = mapped_column(ForeignKey("market_regimes.id"), nullable=False)

    signal: Mapped[str] = mapped_column(String(20), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)

    regime_summary: Mapped[str | None] = mapped_column(String(128), nullable=True)
    supporting_factors: Mapped[str | None] = mapped_column(Text, nullable=True)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
