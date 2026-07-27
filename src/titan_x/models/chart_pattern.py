from datetime import date

from sqlalchemy import Boolean, Date, Float, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from titan_x.db.base import Base
from titan_x.db.mixins import PrimaryKeyMixin, TimestampMixin


class ChartPattern(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "chart_patterns"
    __table_args__ = (
        Index("ix_chart_patterns_symbol", "symbol"),
        Index("ix_chart_patterns_type", "pattern_type"),
        Index("ix_chart_patterns_symbol_date", "symbol", "end_date"),
    )

    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    pattern_type: Mapped[str] = mapped_column(String(32), nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    entry_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    stop_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    pattern_data_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class SupportResistance(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "support_resistance"
    __table_args__ = (
        Index("ix_sr_symbol", "symbol"),
        Index("ix_sr_symbol_type", "symbol", "level_type"),
    )

    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    level_type: Mapped[str] = mapped_column(String(16), nullable=False)
    price_level: Mapped[float] = mapped_column(Float, nullable=False)
    strength_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    touch_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    first_detected: Mapped[date] = mapped_column(Date, nullable=False)
    last_tested: Mapped[date] = mapped_column(Date, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
