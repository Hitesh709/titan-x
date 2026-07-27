from datetime import date, datetime

from sqlalchemy import BigInteger, Date, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from titan_x.db.base import Base
from titan_x.db.mixins import PrimaryKeyMixin, TimestampMixin


class DailyPrice(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "daily_prices"
    __table_args__ = (
        UniqueConstraint("symbol", "trade_date", name="uq_daily_price_symbol_date"),
    )

    symbol: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    trade_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[int] = mapped_column(BigInteger, nullable=False)


class CorporateAction(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "corporate_actions"
    __table_args__ = (
        UniqueConstraint("symbol", "action_date", "action_type", name="uq_corp_action_symbol_date_type"),
    )

    symbol: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    action_date: Mapped[date] = mapped_column(Date, nullable=False)
    action_type: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    ratio_numerator: Mapped[float | None] = mapped_column(Float, nullable=True)
    ratio_denominator: Mapped[float | None] = mapped_column(Float, nullable=True)
    dividend_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    adjustment_factor: Mapped[float | None] = mapped_column(Float, nullable=True)
    new_symbol: Mapped[str | None] = mapped_column(String(16), nullable=True)
    old_symbol: Mapped[str | None] = mapped_column(String(16), nullable=True)
    rights_premium: Mapped[float | None] = mapped_column(Float, nullable=True)
    rights_issue_price: Mapped[float | None] = mapped_column(Float, nullable=True)


class AdjustedPrice(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "adjusted_prices"
    __table_args__ = (
        UniqueConstraint("symbol", "trade_date", name="uq_adjusted_price_symbol_date"),
    )

    symbol: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[int] = mapped_column(BigInteger, nullable=False)
    adjustment_factor: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
