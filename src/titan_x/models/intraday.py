from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from titan_x.db.base import Base
from titan_x.db.mixins import PrimaryKeyMixin, TimestampMixin


class IntradayPrice(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "intraday_prices"
    __table_args__ = (
        UniqueConstraint("symbol", "timestamp", "resolution", name="uq_intraday_symbol_ts_res"),
        Index("ix_intraday_symbol_res_ts", "symbol", "resolution", "timestamp"),
        Index("ix_intraday_symbol_ts", "symbol", "timestamp"),
    )

    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolution: Mapped[str] = mapped_column(String(8), nullable=False)
    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[int] = mapped_column(BigInteger, nullable=False)
