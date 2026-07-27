from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from titan_x.db.base import Base
from titan_x.db.mixins import PrimaryKeyMixin, TimestampMixin


class DistributionProfile(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "distribution_profiles"
    __table_args__ = (
        Index("ix_dp_model_feature", "model_registry_entry_id", "feature_name"),
        Index("ix_dp_model", "model_registry_entry_id"),
    )

    model_registry_entry_id: Mapped[int | None] = mapped_column(ForeignKey("model_registry_entries.id"), nullable=True, index=True)
    feature_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    profile_type: Mapped[str] = mapped_column(String(20), default="baseline")
    dataset_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    num_samples: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mean: Mapped[float | None] = mapped_column(Float, nullable=True)
    std: Mapped[float | None] = mapped_column(Float, nullable=True)
    minimum: Mapped[float | None] = mapped_column(Float, nullable=True)
    maximum: Mapped[float | None] = mapped_column(Float, nullable=True)
    median: Mapped[float | None] = mapped_column(Float, nullable=True)
    p25: Mapped[float | None] = mapped_column(Float, nullable=True)
    p75: Mapped[float | None] = mapped_column(Float, nullable=True)
    histogram_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class DriftDetectionRun(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "drift_detection_runs"
    __table_args__ = (
        Index("ix_ddr_model_entry", "model_registry_entry_id"),
        Index("ix_ddr_status", "status"),
        Index("ix_ddr_drift_detected", "drift_detected"),
        Index("ix_ddr_ran_at", "ran_at"),
    )

    model_registry_entry_id: Mapped[int | None] = mapped_column(ForeignKey("model_registry_entries.id"), nullable=True, index=True)
    model_registry_version_id: Mapped[int | None] = mapped_column(ForeignKey("model_registry_versions.id"), nullable=True)
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="running")
    baseline_dataset: Mapped[str | None] = mapped_column(String(200), nullable=True)
    current_dataset: Mapped[str | None] = mapped_column(String(200), nullable=True)
    drift_detected: Mapped[bool] = mapped_column(Boolean, default=False)
    overall_drift_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    num_features_compared: Mapped[int | None] = mapped_column(Integer, nullable=True)
    num_drifted_features: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    ran_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class FeatureDriftResult(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "feature_drift_results"
    __table_args__ = (
        Index("ix_fdr_run_id", "run_id"),
        Index("ix_fdr_feature", "feature_name"),
        Index("ix_fdr_drifted", "drifted"),
        Index("ix_fdr_run_feature", "run_id", "feature_name"),
    )

    run_id: Mapped[int] = mapped_column(ForeignKey("drift_detection_runs.id"), nullable=False, index=True)
    feature_name: Mapped[str] = mapped_column(String(100), nullable=False)
    drift_type: Mapped[str] = mapped_column(String(30), default="psi")
    drift_score: Mapped[float] = mapped_column(Float, nullable=False)
    p_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    drifted: Mapped[bool] = mapped_column(Boolean, default=False)
    threshold: Mapped[float | None] = mapped_column(Float, nullable=True)

    baseline_mean: Mapped[float | None] = mapped_column(Float, nullable=True)
    baseline_std: Mapped[float | None] = mapped_column(Float, nullable=True)
    baseline_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    current_mean: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_std: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class ConceptDriftResult(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "concept_drift_results"
    __table_args__ = (
        Index("ix_cdr_run_id", "run_id"),
        Index("ix_cdr_metric", "metric_name"),
        Index("ix_cdr_drifted", "drifted"),
    )

    run_id: Mapped[int] = mapped_column(ForeignKey("drift_detection_runs.id"), nullable=False, index=True)
    metric_name: Mapped[str] = mapped_column(String(100), nullable=False)
    baseline_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    absolute_change: Mapped[float | None] = mapped_column(Float, nullable=True)
    percentage_change: Mapped[float | None] = mapped_column(Float, nullable=True)
    drifted: Mapped[bool] = mapped_column(Boolean, default=False)
    threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class DriftAlert(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "drift_alerts"
    __table_args__ = (
        Index("ix_da_run_id", "run_id"),
        Index("ix_da_type", "alert_type"),
        Index("ix_da_severity", "severity"),
        Index("ix_da_acknowledged", "acknowledged"),
        Index("ix_da_run_type", "run_id", "alert_type"),
    )

    run_id: Mapped[int] = mapped_column(ForeignKey("drift_detection_runs.id"), nullable=False, index=True)
    alert_type: Mapped[str] = mapped_column(String(30), nullable=False)
    feature_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    severity: Mapped[str] = mapped_column(String(20), default="medium")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    drift_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
