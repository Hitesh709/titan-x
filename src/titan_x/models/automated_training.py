from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from titan_x.db.base import Base
from titan_x.db.mixins import PrimaryKeyMixin, TimestampMixin


class DatasetVersion(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "dataset_versions"
    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_ds_name_version"),
        Index("ix_ds_status", "status"),
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str | None] = mapped_column(String(512), nullable=True)
    schema_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class FeatureSet(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "feature_sets"
    __table_args__ = (
        UniqueConstraint("name", name="uq_fs_name"),
        Index("ix_fs_status", "status"),
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    features_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_column: Mapped[str | None] = mapped_column(String(100), nullable=True)
    feature_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class HyperparameterConfig(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "hyperparameter_configs"
    __table_args__ = (
        UniqueConstraint("name", name="uq_hp_name"),
        Index("ix_hp_status", "status"),
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    parameters_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class TrainingJob(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "training_jobs"
    __table_args__ = (
        Index("ix_tj_status", "status"),
        Index("ix_tj_schedule", "schedule"),
        Index("ix_tj_priority", "priority"),
        Index("ix_tj_entry_id", "model_registry_entry_id"),
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    model_registry_entry_id: Mapped[int | None] = mapped_column(ForeignKey("model_registry_entries.id"), nullable=True, index=True)
    dataset_version_id: Mapped[int | None] = mapped_column(ForeignKey("dataset_versions.id"), nullable=True)
    feature_set_id: Mapped[int | None] = mapped_column(ForeignKey("feature_sets.id"), nullable=True)
    hyperparameter_config_id: Mapped[int | None] = mapped_column(ForeignKey("hyperparameter_configs.id"), nullable=True)

    status: Mapped[str] = mapped_column(String(20), default="pending")
    schedule: Mapped[str | None] = mapped_column(String(64), nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=0)

    gpu_required: Mapped[bool] = mapped_column(Boolean, default=False)
    gpu_memory_required_mb: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_epochs: Mapped[int] = mapped_column(Integer, default=10)
    current_epoch: Mapped[int] = mapped_column(Integer, default=0)
    max_steps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    current_step: Mapped[int | None] = mapped_column(Integer, nullable=True)

    training_duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    loss_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    best_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    metric_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    best_metric: Mapped[float | None] = mapped_column(Float, nullable=True)

    artifact_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class TrainingJobCheckpoint(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "training_job_checkpoints"
    __table_args__ = (
        Index("ix_tjc_job_id", "job_id"),
        Index("ix_tjc_epoch", "job_id", "epoch"),
    )

    job_id: Mapped[int] = mapped_column(ForeignKey("training_jobs.id"), nullable=False, index=True)
    epoch: Mapped[int] = mapped_column(Integer, nullable=False)
    step: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metric_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    loss_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    artifact_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class TrainingJobLog(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "training_job_logs"
    __table_args__ = (
        Index("ix_tjl_job_id", "job_id"),
        Index("ix_tjl_level", "level"),
        Index("ix_tjl_job_epoch", "job_id", "epoch"),
    )

    job_id: Mapped[int] = mapped_column(ForeignKey("training_jobs.id"), nullable=False, index=True)
    level: Mapped[str] = mapped_column(String(10), default="info")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    epoch: Mapped[int | None] = mapped_column(Integer, nullable=True)
    step: Mapped[int | None] = mapped_column(Integer, nullable=True)
