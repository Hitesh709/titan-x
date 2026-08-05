from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from titan_x.db.base import Base
from titan_x.db.mixins import PrimaryKeyMixin, TimestampMixin


class Recommendation(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "recommendations"
    __table_args__ = (
        Index("ix_rec_symbol", "symbol"),
        Index("ix_rec_direction", "direction"),
        Index("ix_rec_status", "status"),
        Index("ix_rec_type", "recommendation_type"),
        Index("ix_rec_timeframe", "timeframe"),
        Index("ix_rec_score", "score"),
        Index("ix_rec_generated_at", "generated_at"),
        Index("ix_rec_symbol_status", "symbol", "status"),
        Index("ix_rec_decision", "decision"),
        Index("ix_rec_outcome", "outcome"),
        Index("ix_rec_model_version_id", "model_version_id"),
    )

    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    signal: Mapped[str | None] = mapped_column(String(20), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_target: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    timeframe: Mapped[str | None] = mapped_column(String(20), nullable=True)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommendation_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_level: Mapped[str | None] = mapped_column(String(10), nullable=True)
    predicted_return_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    inputs_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_version_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    model_version_label: Mapped[str | None] = mapped_column(String(50), nullable=True)

    decision: Mapped[str] = mapped_column(String(20), default="pending")
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    outcome: Mapped[str] = mapped_column(String(20), default="pending")
    actual_outcome_pnl: Mapped[float | None] = mapped_column(Float, nullable=True)
    outcome_details: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
