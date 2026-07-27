from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from titan_x.db.base import Base
from titan_x.db.mixins import PrimaryKeyMixin, TimestampMixin


class ValidationRun(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "validation_runs"
    __table_args__ = (
        Index("ix_vr_symbol", "symbol"),
        Index("ix_vr_status", "status"),
        Index("ix_vr_created", "created_at"),
    )

    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    date_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    date_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="running", nullable=False)
    total_records: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    anomalies_found: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    missing_values: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duplicate_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    price_anomalies: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    volume_anomalies: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    corp_action_mismatches: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    timestamp_mismatches: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    quality_rating: Mapped[str | None] = mapped_column(String(16), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class ValidationAnomaly(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "validation_anomalies"
    __table_args__ = (
        Index("ix_va_run", "run_id"),
        Index("ix_va_type", "anomaly_type"),
        Index("ix_va_severity", "severity"),
        Index("ix_va_symbol", "symbol"),
    )

    run_id: Mapped[int] = mapped_column(Integer, ForeignKey("validation_runs.id"), nullable=False)
    anomaly_type: Mapped[str] = mapped_column(String(32), nullable=False)
    severity: Mapped[str] = mapped_column(String(8), nullable=False)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    trade_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    field_name: Mapped[str | None] = mapped_column(String(32), nullable=True)
    expected_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    actual_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    details_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class DataQualityScore(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "data_quality_scores"
    __table_args__ = (
        UniqueConstraint("symbol", "score_date", name="uq_dqs_symbol_date"),
        Index("ix_dqs_symbol", "symbol"),
        Index("ix_dqs_score", "overall_score"),
    )

    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    score_date: Mapped[date] = mapped_column(Date, nullable=False)
    overall_score: Mapped[float] = mapped_column(Float, nullable=False)
    completeness_score: Mapped[float] = mapped_column(Float, nullable=False)
    uniqueness_score: Mapped[float] = mapped_column(Float, nullable=False)
    accuracy_score: Mapped[float] = mapped_column(Float, nullable=False)
    consistency_score: Mapped[float] = mapped_column(Float, nullable=False)
    timeliness_score: Mapped[float] = mapped_column(Float, nullable=False)
    total_checks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    checks_passed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    checks_failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rating: Mapped[str] = mapped_column(String(16), nullable=False)
    run_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("validation_runs.id"), nullable=True)
