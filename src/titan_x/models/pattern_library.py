from datetime import date

from sqlalchemy import Boolean, Date, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from titan_x.db.base import Base
from titan_x.db.mixins import PrimaryKeyMixin, TimestampMixin


PATTERN_CATEGORIES = ["candlestick", "chart", "volume", "breakout", "gap", "trend"]


class PatternDefinition(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "pattern_definitions"
    __table_args__ = (
        UniqueConstraint("name", name="uq_pat_def_name"),
        Index("ix_pat_def_category", "category"),
        Index("ix_pat_def_ai_id", "ai_pattern_id"),
    )

    name: Mapped[str] = mapped_column(String(64), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_pattern_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    detection_params_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class PatternInstance(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "pattern_instances"
    __table_args__ = (
        Index("ix_pi_def_id", "definition_id"),
        Index("ix_pi_symbol", "symbol"),
        Index("ix_pi_category", "category"),
        Index("ix_pi_date", "end_date"),
        Index("ix_pi_sym_def", "symbol", "definition_id"),
    )

    definition_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("pattern_definitions.id", ondelete="CASCADE"), nullable=False,
    )
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
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
