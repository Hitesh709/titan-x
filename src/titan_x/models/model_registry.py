from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from titan_x.db.base import Base
from titan_x.db.mixins import PrimaryKeyMixin, TimestampMixin


class ModelRegistryEntry(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "model_registry_entries"
    __table_args__ = (
        UniqueConstraint("name", name="uq_mre_name"),
        Index("ix_mre_status", "status"),
        Index("ix_mre_model_type", "model_type"),
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    framework: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")
    tags_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class ModelRegistryVersion(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "model_registry_versions"
    __table_args__ = (
        UniqueConstraint("entry_id", "version", name="uq_mrv_entry_version"),
        Index("ix_mrv_entry_id", "entry_id"),
        Index("ix_mrv_status", "status"),
        Index("ix_mrv_is_active", "is_active"),
    )

    entry_id: Mapped[int] = mapped_column(ForeignKey("model_registry_entries.id"), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    source: Mapped[str | None] = mapped_column(String(512), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    changelog: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class ModelTrainingRun(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "model_training_runs"
    __table_args__ = (
        Index("ix_mtr_version_id", "version_id"),
        Index("ix_mtr_status", "status"),
    )

    version_id: Mapped[int] = mapped_column(ForeignKey("model_registry_versions.id"), nullable=False, index=True)
    run_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    dataset_info_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    hyperparameters_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    training_duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="completed")
    metrics_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    artifact_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class ModelMetric(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "model_metrics"
    __table_args__ = (
        Index("ix_mm_version_id", "version_id"),
        Index("ix_mm_metric_name", "metric_name"),
    )

    version_id: Mapped[int] = mapped_column(ForeignKey("model_registry_versions.id"), nullable=False, index=True)
    metric_name: Mapped[str] = mapped_column(String(64), nullable=False)
    metric_value: Mapped[float] = mapped_column(Float, nullable=False)
    metric_type: Mapped[str | None] = mapped_column(String(20), default="float")
    dataset_type: Mapped[str | None] = mapped_column(String(20), default="validation")


class ModelRegistryDeployment(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "model_registry_deployments"
    __table_args__ = (
        Index("ix_md_version_id", "version_id"),
        Index("ix_md_environment", "environment"),
        UniqueConstraint("version_id", "environment", name="uq_md_version_env"),
    )

    version_id: Mapped[int] = mapped_column(ForeignKey("model_registry_versions.id"), nullable=False, index=True)
    environment: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active")
    deployed_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    deployed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    rolled_back_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rollback_to_version_id: Mapped[int | None] = mapped_column(ForeignKey("model_registry_versions.id"), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
