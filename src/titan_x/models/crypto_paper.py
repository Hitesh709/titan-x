from datetime import datetime
from decimal import Decimal
from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from titan_x.db.base import Base
from titan_x.db.mixins import PrimaryKeyMixin, TimestampMixin

class CryptoPaperAccount(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__="crypto_paper_accounts"
    user_id: Mapped[int]=mapped_column(ForeignKey("users.id",ondelete="CASCADE"),unique=True,nullable=False,index=True)
    initial_capital: Mapped[Decimal]=mapped_column(Numeric(20,8),default=100000,nullable=False)
    cash_balance: Mapped[Decimal]=mapped_column(Numeric(20,8),default=100000,nullable=False)
    currency: Mapped[str]=mapped_column(String(8),default="USDT",nullable=False)
    is_active: Mapped[bool]=mapped_column(default=True,nullable=False)

class CryptoPaperPosition(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__="crypto_paper_positions"
    __table_args__=(UniqueConstraint("account_id","symbol",name="uq_crypto_paper_position"),)
    account_id: Mapped[int]=mapped_column(ForeignKey("crypto_paper_accounts.id",ondelete="CASCADE"),nullable=False,index=True)
    user_id: Mapped[int]=mapped_column(ForeignKey("users.id",ondelete="CASCADE"),nullable=False,index=True)
    symbol: Mapped[str]=mapped_column(String(20),nullable=False,index=True)
    quantity: Mapped[Decimal]=mapped_column(Numeric(28,12),default=0,nullable=False)
    average_price: Mapped[Decimal]=mapped_column(Numeric(28,12),default=0,nullable=False)
    current_price: Mapped[Decimal|None]=mapped_column(Numeric(28,12),nullable=True)
    realized_pnl: Mapped[Decimal]=mapped_column(Numeric(20,8),default=0,nullable=False)
    stop_price: Mapped[Decimal|None]=mapped_column(Numeric(28,12),nullable=True)
    take_price: Mapped[Decimal|None]=mapped_column(Numeric(28,12),nullable=True)

class CryptoPaperTrade(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__="crypto_paper_trades"
    account_id: Mapped[int]=mapped_column(ForeignKey("crypto_paper_accounts.id",ondelete="CASCADE"),nullable=False,index=True)
    user_id: Mapped[int]=mapped_column(ForeignKey("users.id",ondelete="CASCADE"),nullable=False,index=True)
    symbol: Mapped[str]=mapped_column(String(20),nullable=False,index=True)
    side: Mapped[str]=mapped_column(String(10),nullable=False)
    quantity: Mapped[Decimal]=mapped_column(Numeric(28,12),nullable=False)
    price: Mapped[Decimal]=mapped_column(Numeric(28,12),nullable=False)
    realized_pnl: Mapped[Decimal|None]=mapped_column(Numeric(20,8),nullable=True)
    reason: Mapped[str|None]=mapped_column(Text,nullable=True)
    trade_time: Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now(),nullable=False)
