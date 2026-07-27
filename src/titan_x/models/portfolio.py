from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from titan_x.db.base import Base
from titan_x.db.mixins import PrimaryKeyMixin, TimestampMixin


class Portfolio(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "portfolios"
    __table_args__ = (
        Index("ix_portfolio_name", "name"),
    )

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    holdings: Mapped[list["PortfolioHolding"]] = relationship(back_populates="portfolio", cascade="all, delete-orphan")
    transactions: Mapped[list["PortfolioTransaction"]] = relationship(back_populates="portfolio", cascade="all, delete-orphan")


class PortfolioHolding(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "portfolio_holdings"
    __table_args__ = (
        Index("ix_ph_portfolio_symbol", "portfolio_id", "symbol"),
        Index("ix_ph_portfolio", "portfolio_id"),
    )

    portfolio_id: Mapped[int] = mapped_column(Integer, ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    sector: Mapped[str | None] = mapped_column(String(64), nullable=True)
    quantity: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    average_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    cost_basis: Mapped[float | None] = mapped_column(Float, nullable=True)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)

    portfolio: Mapped["Portfolio"] = relationship(back_populates="holdings")


class PortfolioTransaction(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "portfolio_transactions"
    __table_args__ = (
        Index("ix_pt_portfolio", "portfolio_id"),
        Index("ix_pt_portfolio_symbol", "portfolio_id", "symbol"),
        Index("ix_pt_date", "transaction_date"),
    )

    portfolio_id: Mapped[int] = mapped_column(Integer, ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    transaction_type: Mapped[str] = mapped_column(String(4), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    total_amount: Mapped[float] = mapped_column(Float, nullable=False)
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False)
    realized_pnl: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    portfolio: Mapped["Portfolio"] = relationship(back_populates="transactions")
