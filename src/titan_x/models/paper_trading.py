from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from titan_x.db.base import Base
from titan_x.db.mixins import PrimaryKeyMixin, TimestampMixin


class PaperAccount(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "paper_accounts"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    initial_capital: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=100000.00, nullable=False)
    cash_balance: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=100000.00, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)


class PaperOrder(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "paper_orders"

    account_id: Mapped[int] = mapped_column(ForeignKey("paper_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    side: Mapped[str] = mapped_column(String(10), nullable=False)
    order_type: Mapped[str] = mapped_column(String(20), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    filled_quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    stop_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    time_in_force: Mapped[str] = mapped_column(String(10), default="day", nullable=False)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    filled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    slippage: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)


class PaperPosition(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "paper_positions"
    __table_args__ = (UniqueConstraint("account_id", "symbol", name="uq_paper_position"),)

    account_id: Mapped[int] = mapped_column(ForeignKey("paper_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    average_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    cost_basis: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=0, nullable=False)
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=0, nullable=False)
    current_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)


class PaperTrade(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "paper_trades"

    order_id: Mapped[int] = mapped_column(ForeignKey("paper_orders.id", ondelete="CASCADE"), nullable=False, index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("paper_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    side: Mapped[str] = mapped_column(String(10), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    commission: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    realized_pnl: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    trade_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class SimulatedOrder(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "simulated_orders"

    account_id: Mapped[int] = mapped_column(ForeignKey("paper_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    direction: Mapped[str] = mapped_column(String(10), default="long", nullable=False)
    entry_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    exit_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    entry_fee: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    exit_fee: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    total_fees: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    slippage: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    gross_pnl: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    net_pnl: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    outcome: Mapped[str | None] = mapped_column(String(20), nullable=True)
    entry_order_id: Mapped[int | None] = mapped_column(ForeignKey("paper_orders.id", ondelete="SET NULL"), nullable=True)
    exit_order_id: Mapped[int | None] = mapped_column(ForeignKey("paper_orders.id", ondelete="SET NULL"), nullable=True)
    entry_trade_id: Mapped[int | None] = mapped_column(ForeignKey("paper_trades.id", ondelete="SET NULL"), nullable=True)
    exit_trade_id: Mapped[int | None] = mapped_column(ForeignKey("paper_trades.id", ondelete="SET NULL"), nullable=True)
    entry_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    exit_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(10), default="open", nullable=False)
