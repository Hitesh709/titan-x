from datetime import date

from sqlalchemy import BigInteger, Date, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from titan_x.db.base import Base
from titan_x.db.mixins import PrimaryKeyMixin, TimestampMixin


class FinancialStatement(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "financial_statements"
    __table_args__ = (
        UniqueConstraint(
            "symbol", "fiscal_year", "fiscal_period", "period_type", "statement_type",
            name="uq_fin_stmt_symbol_year_period_type",
        ),
    )

    symbol: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False)
    fiscal_period: Mapped[int] = mapped_column(Integer, nullable=False)
    period_type: Mapped[str] = mapped_column(String(16), nullable=False)
    statement_type: Mapped[str] = mapped_column(String(32), nullable=False)
    filing_date: Mapped[date] = mapped_column(Date, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="USD", nullable=False)
    source: Mapped[str | None] = mapped_column(String(64), nullable=True)

    line_items: Mapped[list["FinancialLineItem"]] = relationship(
        back_populates="statement", cascade="all, delete-orphan",
        order_by="FinancialLineItem.order",
    )


class FinancialLineItem(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "financial_line_items"
    __table_args__ = (
        UniqueConstraint("statement_id", "concept", name="uq_fin_line_item_stmt_concept"),
    )

    statement_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("financial_statements.id", ondelete="CASCADE"), nullable=False,
    )
    concept: Mapped[str] = mapped_column(String(128), nullable=False)
    label: Mapped[str | None] = mapped_column(String(256), nullable=True)
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    order: Mapped[int | None] = mapped_column(Integer, nullable=True)

    statement: Mapped["FinancialStatement"] = relationship(back_populates="line_items")
