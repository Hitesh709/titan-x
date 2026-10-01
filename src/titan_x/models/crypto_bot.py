from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column
from titan_x.db.base import Base
from titan_x.db.mixins import PrimaryKeyMixin, TimestampMixin

class CryptoPaperBotState(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__="crypto_paper_bot_states"
    user_id: Mapped[int]=mapped_column(ForeignKey("users.id",ondelete="CASCADE"),unique=True,nullable=False,index=True)
    symbol: Mapped[str]=mapped_column(String(20),default="BTCUSDT",nullable=False)
    enabled: Mapped[bool]=mapped_column(Boolean,default=False,nullable=False)
    risk_per_trade: Mapped[float]=mapped_column(Numeric(8,4),default=1,nullable=False)
    max_position_pct: Mapped[float]=mapped_column(Numeric(8,4),default=25,nullable=False)
    last_decision: Mapped[str|None]=mapped_column(String(10),nullable=True)
    last_reason: Mapped[str|None]=mapped_column(String(500),nullable=True)
    last_run_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
