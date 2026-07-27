from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from titan_x.db.base import Base
from titan_x.db.mixins import PrimaryKeyMixin, TimestampMixin


class FIIHolding(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "fii_holdings"
    __table_args__ = (
        Index("ix_fii_company_q", "company_id", "year", "quarter"),
        Index("ix_fii_name_q", "fii_name", "year", "quarter"),
    )

    company_id: Mapped[int] = mapped_column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    fii_name: Mapped[str] = mapped_column(String(256), nullable=False)
    category: Mapped[str] = mapped_column(String(16), default="FII", nullable=False)
    shares_held: Mapped[int | None] = mapped_column(Integer, nullable=True)
    percentage: Mapped[float] = mapped_column(Float, nullable=False)
    change_percentage: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_crores: Mapped[float | None] = mapped_column(Float, nullable=True)
    quarter: Mapped[int] = mapped_column(Integer, nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    filing_date: Mapped[date] = mapped_column(Date, nullable=False)

    company: Mapped["Company"] = relationship(back_populates="fii_holdings")


class DIIHolding(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "dii_holdings"
    __table_args__ = (
        Index("ix_dii_company_q", "company_id", "year", "quarter"),
        Index("ix_dii_name_q", "dii_name", "year", "quarter"),
    )

    company_id: Mapped[int] = mapped_column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    dii_name: Mapped[str] = mapped_column(String(256), nullable=False)
    category: Mapped[str] = mapped_column(String(32), default="DII", nullable=False)
    shares_held: Mapped[int | None] = mapped_column(Integer, nullable=True)
    percentage: Mapped[float] = mapped_column(Float, nullable=False)
    change_percentage: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_crores: Mapped[float | None] = mapped_column(Float, nullable=True)
    quarter: Mapped[int] = mapped_column(Integer, nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    filing_date: Mapped[date] = mapped_column(Date, nullable=False)

    company: Mapped["Company"] = relationship(back_populates="dii_holdings")


class MutualFundHolding(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "mutual_fund_holdings"
    __table_args__ = (
        Index("ix_mf_company_q", "company_id", "year", "quarter"),
        Index("ix_mf_scheme_q", "scheme_name", "year", "quarter"),
    )

    company_id: Mapped[int] = mapped_column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    amc: Mapped[str] = mapped_column(String(128), nullable=False)
    scheme_name: Mapped[str] = mapped_column(String(256), nullable=False)
    fund_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    shares_held: Mapped[int | None] = mapped_column(Integer, nullable=True)
    percentage: Mapped[float] = mapped_column(Float, nullable=False)
    change_percentage: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_crores: Mapped[float | None] = mapped_column(Float, nullable=True)
    quarter: Mapped[int] = mapped_column(Integer, nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    filing_date: Mapped[date] = mapped_column(Date, nullable=False)

    company: Mapped["Company"] = relationship(back_populates="mf_holdings")


class ETFHolding(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "etf_holdings"
    __table_args__ = (
        Index("ix_etf_company_q", "company_id", "year", "quarter"),
        Index("ix_etf_name_q", "etf_name", "year", "quarter"),
    )

    company_id: Mapped[int] = mapped_column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    etf_name: Mapped[str] = mapped_column(String(256), nullable=False)
    issuer: Mapped[str] = mapped_column(String(128), nullable=False)
    shares_held: Mapped[int | None] = mapped_column(Integer, nullable=True)
    percentage: Mapped[float] = mapped_column(Float, nullable=False)
    change_percentage: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_crores: Mapped[float | None] = mapped_column(Float, nullable=True)
    quarter: Mapped[int] = mapped_column(Integer, nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    filing_date: Mapped[date] = mapped_column(Date, nullable=False)

    company: Mapped["Company"] = relationship(back_populates="etf_holdings")


class InstitutionalAnalysis(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "institutional_analyses"
    __table_args__ = (
        Index("ix_inst_analysis_company", "company_id", "generated_at"),
    )

    company_id: Mapped[int] = mapped_column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    analysis_date: Mapped[date] = mapped_column(Date, nullable=False)
    fii_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    dii_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    mf_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    etf_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    institutional_trend_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    fii_dii_divergence: Mapped[float | None] = mapped_column(Float, nullable=True)
    composite_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    signal: Mapped[str | None] = mapped_column(String(16), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    insights_json: Mapped[str] = mapped_column(Text, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    company: Mapped["Company"] = relationship(back_populates="institutional_analyses")
