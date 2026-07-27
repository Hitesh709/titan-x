from datetime import date

from sqlalchemy import Boolean, Date, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from titan_x.db.base import Base
from titan_x.db.mixins import PrimaryKeyMixin, TimestampMixin


class PriceTarget(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "price_targets"
    __table_args__ = (
        Index("ix_prt_symbol", "symbol"),
        Index("ix_prt_date", "trade_date"),
        Index("ix_prt_symbol_active", "symbol", "is_active"),
    )

    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False, default="bullish")
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    current_price: Mapped[float | None] = mapped_column(Float, nullable=True)

    target_1_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_1_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_1_probability: Mapped[float | None] = mapped_column(Float, nullable=True)

    target_2_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_2_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_2_probability: Mapped[float | None] = mapped_column(Float, nullable=True)

    target_3_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_3_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_3_probability: Mapped[float | None] = mapped_column(Float, nullable=True)

    expected_holding_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    method: Mapped[str] = mapped_column(String(32), nullable=False, default="composite")

    atr_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    nearest_resistance: Mapped[float | None] = mapped_column(Float, nullable=True)
    resistance_strength: Mapped[float | None] = mapped_column(Float, nullable=True)
    volatility_20d: Mapped[float | None] = mapped_column(Float, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
