from datetime import date

from sqlalchemy import BigInteger, Date, Float, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from titan_x.db.base import Base
from titan_x.db.mixins import PrimaryKeyMixin, TimestampMixin


class MarketBreadth(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "market_breadth"
    __table_args__ = (
        UniqueConstraint("trade_date", name="uq_market_breadth_date"),
        Index("ix_market_breadth_trade_date", "trade_date"),
    )

    trade_date: Mapped[date] = mapped_column(Date, nullable=False)

    advancing: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    declining: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    unchanged: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    total_stocks: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    advancing_volume: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    declining_volume: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    unchanged_volume: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    total_volume: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    new_highs: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    new_lows: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    advance_decline_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    advance_decline_line: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume_breadth_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    breadth_oscillator: Mapped[float | None] = mapped_column(Float, nullable=True)
    index_strength_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
