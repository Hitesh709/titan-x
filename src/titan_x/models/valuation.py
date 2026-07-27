from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from titan_x.db.base import Base
from titan_x.db.mixins import PrimaryKeyMixin, TimestampMixin


class DCFValuation(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "dcf_valuations"
    __table_args__ = (UniqueConstraint("symbol", "valuation_date", name="uq_dcf_sym_date"),)

    symbol: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    valuation_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    current_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    free_cash_flow: Mapped[float | None] = mapped_column(Float, nullable=True)
    growth_rate_5y: Mapped[float | None] = mapped_column(Float, nullable=True)
    terminal_growth_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    wacc: Mapped[float | None] = mapped_column(Float, nullable=True)
    projection_years: Mapped[int] = mapped_column(Integer, default=5)
    shares_outstanding: Mapped[float | None] = mapped_column(Float, nullable=True)
    net_debt: Mapped[float | None] = mapped_column(Float, nullable=True)
    cash_and_equivalents: Mapped[float | None] = mapped_column(Float, nullable=True)
    present_value_fcf: Mapped[float | None] = mapped_column(Float, nullable=True)
    terminal_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    present_value_tv: Mapped[float | None] = mapped_column(Float, nullable=True)
    enterprise_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    equity_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    intrinsic_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    upside_pct: Mapped[float | None] = mapped_column(Float, nullable=True)


class RelativeValuation(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "relative_valuations"
    __table_args__ = (UniqueConstraint("symbol", "valuation_date", name="uq_rel_sym_date"),)

    symbol: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    valuation_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    current_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    eps: Mapped[float | None] = mapped_column(Float, nullable=True)
    book_value_per_share: Mapped[float | None] = mapped_column(Float, nullable=True)
    revenue_per_share: Mapped[float | None] = mapped_column(Float, nullable=True)
    ebitda: Mapped[float | None] = mapped_column(Float, nullable=True)
    pe_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    pb_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    ps_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    ev_ebitda: Mapped[float | None] = mapped_column(Float, nullable=True)
    industry_avg_pe: Mapped[float | None] = mapped_column(Float, nullable=True)
    industry_avg_pb: Mapped[float | None] = mapped_column(Float, nullable=True)
    industry_avg_ps: Mapped[float | None] = mapped_column(Float, nullable=True)
    industry_avg_ev_ebitda: Mapped[float | None] = mapped_column(Float, nullable=True)
    pe_fair_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    pb_fair_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    ps_fair_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    ev_ebitda_fair_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    composite_fair_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    upside_pct: Mapped[float | None] = mapped_column(Float, nullable=True)


class SectorValuation(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "sector_valuations"
    __table_args__ = (UniqueConstraint("symbol", "valuation_date", name="uq_sector_sym_date"),)

    symbol: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    valuation_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sector: Mapped[str | None] = mapped_column(String(128), nullable=True)
    peer_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    peer_avg_pe: Mapped[float | None] = mapped_column(Float, nullable=True)
    peer_median_pe: Mapped[float | None] = mapped_column(Float, nullable=True)
    peer_avg_pb: Mapped[float | None] = mapped_column(Float, nullable=True)
    peer_avg_ps: Mapped[float | None] = mapped_column(Float, nullable=True)
    peer_avg_ev_ebitda: Mapped[float | None] = mapped_column(Float, nullable=True)
    pe_percentile: Mapped[float | None] = mapped_column(Float, nullable=True)
    pb_percentile: Mapped[float | None] = mapped_column(Float, nullable=True)
    sector_grade: Mapped[str | None] = mapped_column(String(10), nullable=True)
    sector_fair_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    upside_pct: Mapped[float | None] = mapped_column(Float, nullable=True)


class ValuationReport(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "valuation_reports"
    __table_args__ = (UniqueConstraint("symbol", "report_date", name="uq_vr_sym_date"),)

    symbol: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    report_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    current_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    dcf_fair_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    relative_fair_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    sector_fair_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    composite_fair_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    margin_of_safety_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    dcf_upside: Mapped[float | None] = mapped_column(Float, nullable=True)
    relative_upside: Mapped[float | None] = mapped_column(Float, nullable=True)
    sector_upside: Mapped[float | None] = mapped_column(Float, nullable=True)
    recommendation: Mapped[str | None] = mapped_column(String(20), nullable=True)
    report_json: Mapped[str | None] = mapped_column(Text, nullable=True)
