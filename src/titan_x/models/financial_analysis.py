from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from titan_x.db.base import Base
from titan_x.db.mixins import PrimaryKeyMixin, TimestampMixin


class QuarterlyResult(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "quarterly_results"
    __table_args__ = (UniqueConstraint("symbol", "fiscal_year", "quarter", name="uq_qr_symbol_year_q"),)

    symbol: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False)
    quarter: Mapped[int] = mapped_column(Integer, nullable=False)
    revenue: Mapped[float | None] = mapped_column(Float, nullable=True)
    cost_of_revenue: Mapped[float | None] = mapped_column(Float, nullable=True)
    gross_profit: Mapped[float | None] = mapped_column(Float, nullable=True)
    operating_expenses: Mapped[float | None] = mapped_column(Float, nullable=True)
    operating_income: Mapped[float | None] = mapped_column(Float, nullable=True)
    net_income: Mapped[float | None] = mapped_column(Float, nullable=True)
    eps_basic: Mapped[float | None] = mapped_column(Float, nullable=True)
    eps_diluted: Mapped[float | None] = mapped_column(Float, nullable=True)
    gross_margin: Mapped[float | None] = mapped_column(Float, nullable=True)
    operating_margin: Mapped[float | None] = mapped_column(Float, nullable=True)
    net_margin: Mapped[float | None] = mapped_column(Float, nullable=True)
    revenue_qoq_growth: Mapped[float | None] = mapped_column(Float, nullable=True)
    revenue_yoy_growth: Mapped[float | None] = mapped_column(Float, nullable=True)
    eps_qoq_growth: Mapped[float | None] = mapped_column(Float, nullable=True)
    eps_yoy_growth: Mapped[float | None] = mapped_column(Float, nullable=True)
    filing_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    source: Mapped[str | None] = mapped_column(String(64), nullable=True)


class AnnualResult(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "annual_results"
    __table_args__ = (UniqueConstraint("symbol", "fiscal_year", name="uq_ar_symbol_year"),)

    symbol: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False)
    revenue: Mapped[float | None] = mapped_column(Float, nullable=True)
    cost_of_revenue: Mapped[float | None] = mapped_column(Float, nullable=True)
    gross_profit: Mapped[float | None] = mapped_column(Float, nullable=True)
    operating_expenses: Mapped[float | None] = mapped_column(Float, nullable=True)
    operating_income: Mapped[float | None] = mapped_column(Float, nullable=True)
    net_income: Mapped[float | None] = mapped_column(Float, nullable=True)
    eps_basic: Mapped[float | None] = mapped_column(Float, nullable=True)
    eps_diluted: Mapped[float | None] = mapped_column(Float, nullable=True)
    gross_margin: Mapped[float | None] = mapped_column(Float, nullable=True)
    operating_margin: Mapped[float | None] = mapped_column(Float, nullable=True)
    net_margin: Mapped[float | None] = mapped_column(Float, nullable=True)
    revenue_yoy_growth: Mapped[float | None] = mapped_column(Float, nullable=True)
    eps_yoy_growth: Mapped[float | None] = mapped_column(Float, nullable=True)
    filing_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    source: Mapped[str | None] = mapped_column(String(64), nullable=True)


class Guidance(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "guidance"
    __table_args__ = (UniqueConstraint("symbol", "fiscal_year", "period_type", name="uq_guid_symbol_year_type"),)

    symbol: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False)
    period_type: Mapped[str] = mapped_column(String(16), nullable=False)
    revenue_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    revenue_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    eps_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    eps_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    operating_margin_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    operating_margin_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    guidance_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    issued_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")


class FinancialAnalysis(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "financial_analyses"
    __table_args__ = (UniqueConstraint("symbol", "analysis_date", name="uq_fa_symbol_date"),)

    symbol: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    analysis_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revenue_growth_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    margin_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    eps_growth_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    guidance_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    overall_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    signal: Mapped[str | None] = mapped_column(String(20), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    summary_text: Mapped[str | None] = mapped_column(Text, nullable=True)
