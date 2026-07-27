from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from titan_x.db.base import Base
from titan_x.db.mixins import PrimaryKeyMixin, TimestampMixin


class Experiment(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "experiments"
    __table_args__ = (
        UniqueConstraint("experiment_id", name="uq_exp_experiment_id"),
        Index("ix_exp_status", "status"),
        Index("ix_exp_name", "name"),
        Index("ix_exp_best_metric", "best_metric_value"),
    )

    experiment_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="running")

    best_metric_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    best_metric_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    best_metric_direction: Mapped[str | None] = mapped_column(String(10), nullable=True)

    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class ExperimentParameter(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "experiment_parameters"
    __table_args__ = (
        UniqueConstraint("experiment_id", "key", name="uq_ep_exp_key"),
        Index("ix_ep_experiment_id", "experiment_id"),
        Index("ix_ep_key", "key"),
    )

    experiment_id: Mapped[int] = mapped_column(ForeignKey("experiments.id"), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    param_type: Mapped[str | None] = mapped_column(String(20), nullable=True)


class ExperimentMetric(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "experiment_metrics"
    __table_args__ = (
        Index("ix_em_experiment_id", "experiment_id"),
        Index("ix_em_key", "key"),
        Index("ix_em_step", "experiment_id", "key", "step"),
    )

    experiment_id: Mapped[int] = mapped_column(ForeignKey("experiments.id"), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    step: Mapped[int | None] = mapped_column(Integer, nullable=True)
    epoch: Mapped[int | None] = mapped_column(Integer, nullable=True)


class ExperimentArtifact(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "experiment_artifacts"
    __table_args__ = (
        UniqueConstraint("experiment_id", "name", name="uq_ea_exp_name"),
        Index("ix_ea_experiment_id", "experiment_id"),
        Index("ix_ea_artifact_type", "artifact_type"),
    )

    experiment_id: Mapped[int] = mapped_column(ForeignKey("experiments.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    artifact_type: Mapped[str] = mapped_column(String(30), default="file")
    file_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    uri: Mapped[str | None] = mapped_column(String(512), nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class ExperimentChart(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "experiment_charts"
    __table_args__ = (
        UniqueConstraint("experiment_id", "name", name="uq_ec_exp_name"),
        Index("ix_ec_experiment_id", "experiment_id"),
    )

    experiment_id: Mapped[int] = mapped_column(ForeignKey("experiments.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    chart_type: Mapped[str] = mapped_column(String(30), default="line")
    chart_config_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class ExperimentTag(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "experiment_tags"
    __table_args__ = (
        UniqueConstraint("experiment_id", "key", name="uq_et_exp_key"),
        Index("ix_et_experiment_id", "experiment_id"),
        Index("ix_et_key_value", "key", "value"),
    )

    experiment_id: Mapped[int] = mapped_column(ForeignKey("experiments.id"), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[str] = mapped_column(String(200), nullable=False)
