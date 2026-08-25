from datetime import date

from sqlalchemy import BigInteger, Boolean, Date, Numeric, String, Text, synonym
from sqlalchemy.orm import Mapped, mapped_column, relationship

from titan_x.db.base import Base
from titan_x.db.mixins import PrimaryKeyMixin, TimestampMixin


class Company(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "companies"

    symbol: Mapped[str] = mapped_column(String(16), unique=True, index=True, nullable=False)
    company_name: Mapped[str] = mapped_column(String(256), nullable=False)
    # Compatibility alias used by recommendation/search layers.
    name = synonym("company_name")
    isin: Mapped[str] = mapped_column(String(12), unique=True, index=True, nullable=False)
    sector: Mapped[str | None] = mapped_column(String(128), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(128), nullable=True)
    exchange: Mapped[str] = mapped_column(String(8), nullable=False)
    market_cap: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    listing_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    website: Mapped[str | None] = mapped_column(String(256), nullable=True)

    promoter_transactions: Mapped[list["PromoterTransaction"]] = relationship(back_populates="company", foreign_keys="PromoterTransaction.company_id")
    insider_trades: Mapped[list["InsiderTrade"]] = relationship(back_populates="company", foreign_keys="InsiderTrade.company_id")
    shareholding_patterns: Mapped[list["ShareholdingPattern"]] = relationship(back_populates="company", foreign_keys="ShareholdingPattern.company_id")
    corporate_analyses: Mapped[list["CorporateAnalysis"]] = relationship(back_populates="company", foreign_keys="CorporateAnalysis.company_id")
    fii_holdings: Mapped[list["FIIHolding"]] = relationship(back_populates="company", foreign_keys="FIIHolding.company_id")
    dii_holdings: Mapped[list["DIIHolding"]] = relationship(back_populates="company", foreign_keys="DIIHolding.company_id")
    mf_holdings: Mapped[list["MutualFundHolding"]] = relationship(back_populates="company", foreign_keys="MutualFundHolding.company_id")
    etf_holdings: Mapped[list["ETFHolding"]] = relationship(back_populates="company", foreign_keys="ETFHolding.company_id")
    promoter_transactions: Mapped[list["PromoterTransaction"]] = relationship(back_populates="company", foreign_keys="PromoterTransaction.company_id")
    insider_trades: Mapped[list["InsiderTrade"]] = relationship(back_populates="company", foreign_keys="InsiderTrade.company_id")
    shareholding_patterns: Mapped[list["ShareholdingPattern"]] = relationship(back_populates="company", foreign_keys="ShareholdingPattern.company_id")
    corporate_analyses: Mapped[list["CorporateAnalysis"]] = relationship(back_populates="company", foreign_keys="CorporateAnalysis.company_id")
    fii_holdings: Mapped[list["FIIHolding"]] = relationship(back_populates="company", foreign_keys="FIIHolding.company_id")
    dii_holdings: Mapped[list["DIIHolding"]] = relationship(back_populates="company", foreign_keys="DIIHolding.company_id")
    mf_holdings: Mapped[list["MutualFundHolding"]] = relationship(back_populates="company", foreign_keys="MutualFundHolding.company_id")
    etf_holdings: Mapped[list["ETFHolding"]] = relationship(back_populates="company", foreign_keys="ETFHolding.company_id")
    institutional_analyses: Mapped[list["InstitutionalAnalysis"]] = relationship(back_populates="company", foreign_keys="InstitutionalAnalysis.company_id")
