"""Market scan result model."""
from datetime import date

from sqlalchemy import Date, Float, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from titan_x.db.base import Base
from titan_x.db.mixins import PrimaryKeyMixin, TimestampMixin


class MarketScanResult(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "market_scan_results"
    __table_args__ = (
        UniqueConstraint("symbol", "scan_date", name="uq_msr_symbol_date"),
        Index("ix_msr_scan_date", "scan_date"),
        Index("ix_msr_composite", "scan_date", "composite_score"),
    )

    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    scan_date: Mapped[date] = mapped_column(Date, nullable=False)
    composite_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    breakout_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    breakdown_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    ema_cross_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    rsi_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    macd_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    adx_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    atr_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    volume_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    breakout_signal: Mapped[str | None] = mapped_column(String(16), nullable=True)
    breakdown_signal: Mapped[str | None] = mapped_column(String(16), nullable=True)
    ema_cross_signal: Mapped[str | None] = mapped_column(String(16), nullable=True)
    rsi_signal: Mapped[str | None] = mapped_column(String(16), nullable=True)
    macd_signal: Mapped[str | None] = mapped_column(String(16), nullable=True)
    adx_signal: Mapped[str | None] = mapped_column(String(16), nullable=True)
    atr_signal: Mapped[str | None] = mapped_column(String(16), nullable=True)
    volume_signal: Mapped[str | None] = mapped_column(String(16), nullable=True)

    signals_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
