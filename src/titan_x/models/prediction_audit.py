"""Immutable prediction provenance and outcome records.

These tables complement the existing Prediction/Recommendation models rather
than replacing them. They capture the exact information used to make a signal
and its realized outcomes at the project's supported short-term horizons.
"""
from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from titan_x.db.base import Base
from titan_x.db.mixins import PrimaryKeyMixin, TimestampMixin


PREDICTION_HORIZONS = (1, 3, 5, 10, 15, 20, 30)


class PredictionAudit(PrimaryKeyMixin, TimestampMixin, Base):
    """Point-in-time audit envelope for one generated prediction."""

    __tablename__ = "prediction_audits"
    __table_args__ = (
        UniqueConstraint("prediction_id", name="uq_prediction_audit_prediction"),
        Index("ix_prediction_audit_symbol_asof", "symbol", "as_of_date"),
        Index("ix_prediction_audit_generated", "generated_at"),
        Index("ix_prediction_audit_input_hash", "input_hash"),
    )

    prediction_id: Mapped[int] = mapped_column(
        ForeignKey("predictions.id", ondelete="CASCADE"), nullable=False,
    )
    recommendation_id: Mapped[int | None] = mapped_column(
        ForeignKey("recommendations.id", ondelete="SET NULL"), nullable=True,
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Immutable references to the exact data/model state used for inference.
    data_snapshot_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_source_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    feature_version_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_version_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    market_regime: Mapped[str | None] = mapped_column(String(32), nullable=True)
    input_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    explanation_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    audit_schema_version: Mapped[str] = mapped_column(
        String(16), default="1.0.0", nullable=False,
    )

    outcomes: Mapped[list["PredictionOutcome"]] = relationship(
        back_populates="audit", cascade="all, delete-orphan",
    )


class PredictionOutcome(PrimaryKeyMixin, TimestampMixin, Base):
    """Realized market outcome for a prediction at a fixed horizon."""

    __tablename__ = "prediction_outcomes"
    __table_args__ = (
        UniqueConstraint("audit_id", "horizon_days", name="uq_prediction_outcome_horizon"),
        Index("ix_prediction_outcome_horizon", "horizon_days"),
        Index("ix_prediction_outcome_resolved", "resolved_at"),
    )

    audit_id: Mapped[int] = mapped_column(
        ForeignKey("prediction_audits.id", ondelete="CASCADE"), nullable=False,
    )
    horizon_days: Mapped[int] = mapped_column(Integer, nullable=False)
    observation_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    entry_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    close_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    close_return_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_favorable_excursion_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_adverse_excursion_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_hit: Mapped[bool | None] = mapped_column(nullable=True)
    stop_hit: Mapped[bool | None] = mapped_column(nullable=True)
    direction_correct: Mapped[bool | None] = mapped_column(nullable=True)
    resolution_status: Mapped[str] = mapped_column(
        String(16), default="pending", nullable=False,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    outcome_metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    audit: Mapped["PredictionAudit"] = relationship(back_populates="outcomes")
