from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from titan_x.db.base import Base
from titan_x.db.mixins import PrimaryKeyMixin, TimestampMixin


class PromoterTransaction(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "promoter_transactions"
    __table_args__ = (
        Index("ix_prom_trx_company", "company_id", "transaction_date"),
        Index("ix_prom_trx_type_date", "transaction_type", "transaction_date"),
    )

    company_id: Mapped[int] = mapped_column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    promoter_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    promoter_name: Mapped[str] = mapped_column(String(128), nullable=False)
    transaction_type: Mapped[str] = mapped_column(String(8), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    percentage_change: Mapped[float | None] = mapped_column(Float, nullable=True)
    mode: Mapped[str] = mapped_column(String(32), default="market", nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    company: Mapped["Company"] = relationship(back_populates="promoter_transactions")


class InsiderTrade(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "insider_trades"
    __table_args__ = (
        Index("ix_insider_company", "company_id", "transaction_date"),
        Index("ix_insider_type_date", "transaction_type", "transaction_date"),
    )

    company_id: Mapped[int] = mapped_column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    insider_name: Mapped[str] = mapped_column(String(128), nullable=False)
    designation: Mapped[str | None] = mapped_column(String(128), nullable=True)
    transaction_type: Mapped[str] = mapped_column(String(8), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    mode: Mapped[str] = mapped_column(String(32), default="market", nullable=False)
    is_derivative: Mapped[bool] = mapped_column(default=False, nullable=False)
    derivative_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    exercise_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    filing_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    company: Mapped["Company"] = relationship(back_populates="insider_trades")


class ShareholdingPattern(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "shareholding_patterns"
    __table_args__ = (
        Index("ix_sh_company_quarter", "company_id", "year", "quarter"),
        Index("ix_sh_category", "category", "year", "quarter"),
    )

    company_id: Mapped[int] = mapped_column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    filing_date: Mapped[date] = mapped_column(Date, nullable=False)
    quarter: Mapped[int] = mapped_column(Integer, nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    shares_held: Mapped[int | None] = mapped_column(Integer, nullable=True)
    percentage: Mapped[float] = mapped_column(Float, nullable=False)
    change_percentage: Mapped[float | None] = mapped_column(Float, nullable=True)

    company: Mapped["Company"] = relationship(back_populates="shareholding_patterns")


class CorporateAnalysis(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "corporate_analyses"
    __table_args__ = (
        Index("ix_corp_analysis_company", "company_id", "generated_at"),
    )

    company_id: Mapped[int] = mapped_column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    analysis_date: Mapped[date] = mapped_column(Date, nullable=False)
    promoter_buying_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    promoter_selling_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    insider_sentiment_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    shareholding_trend_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    weighted_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    signal: Mapped[str | None] = mapped_column(String(16), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    insights_json: Mapped[str] = mapped_column(Text, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    company: Mapped["Company"] = relationship(back_populates="corporate_analyses")
