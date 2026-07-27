from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from titan_x.db.base import Base
from titan_x.db.mixins import PrimaryKeyMixin, TimestampMixin


class Order(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "orders"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    side: Mapped[str] = mapped_column(String(10), nullable=False)
    order_type: Mapped[str] = mapped_column(String(20), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    filled_quantity: Mapped[int] = mapped_column(Integer, default=0)
    price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    stop_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    time_in_force: Mapped[str] = mapped_column(String(10), default="day")
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    fills: Mapped[list["OrderFill"]] = relationship(back_populates="order", cascade="all, delete-orphan")
    user: Mapped["User"] = relationship(back_populates="orders")


class OrderFill(PrimaryKeyMixin, Base):
    __tablename__ = "order_fills"

    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    side: Mapped[str] = mapped_column(String(10), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    commission: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    fill_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    realized_pnl: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)

    order: Mapped["Order"] = relationship(back_populates="fills")


class Position(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "positions"
    __table_args__ = (UniqueConstraint("user_id", "symbol", name="uq_position_user_symbol"),)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    average_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    cost_basis: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=0)
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=0)
    unrealized_pnl: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=0)
    current_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)

    user: Mapped["User"] = relationship(back_populates="positions")
