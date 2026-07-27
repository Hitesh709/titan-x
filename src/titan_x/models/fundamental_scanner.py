"""Fundamental scan result model."""
from datetime import date

from sqlalchemy import Date, Float, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from titan_x.db.base import Base
from titan_x.db.mixins import PrimaryKeyMixin, TimestampMixin


class FundamentalScanResult(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "fundamental_scan_results"
    __table_args__ = (
        UniqueConstraint("symbol", "scan_date", name="uq_fsr_symbol_date"),
        Index("ix_fsr_scan_date", "scan_date"),
        Index("ix_fsr_composite", "scan_date", "composite_score"),
    )

    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    scan_date: Mapped[date] = mapped_column(Date, nullable=False)
    composite_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    roe_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    roce_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    debt_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    revenue_growth_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    eps_growth_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    cash_flow_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    valuation_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    roe_signal: Mapped[str | None] = mapped_column(String(16), nullable=True)
    roce_signal: Mapped[str | None] = mapped_column(String(16), nullable=True)
    debt_signal: Mapped[str | None] = mapped_column(String(16), nullable=True)
    revenue_growth_signal: Mapped[str | None] = mapped_column(String(16), nullable=True)
    eps_growth_signal: Mapped[str | None] = mapped_column(String(16), nullable=True)
    cash_flow_signal: Mapped[str | None] = mapped_column(String(16), nullable=True)
    valuation_signal: Mapped[str | None] = mapped_column(String(16), nullable=True)

    signals_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
