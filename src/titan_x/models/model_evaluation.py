from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from titan_x.db.base import Base
from titan_x.db.mixins import PrimaryKeyMixin, TimestampMixin


class ModelEvaluation(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "model_evaluations"
    __table_args__ = (
        Index("ix_me_experiment_id", "experiment_id"),
        Index("ix_me_model_entry_id", "model_registry_entry_id"),
        Index("ix_me_status", "status"),
        Index("ix_me_evaluated_at", "evaluated_at"),
    )

    experiment_id: Mapped[int | None] = mapped_column(ForeignKey("experiments.id"), nullable=True, index=True)
    model_registry_entry_id: Mapped[int | None] = mapped_column(ForeignKey("model_registry_entries.id"), nullable=True, index=True)
    model_registry_version_id: Mapped[int | None] = mapped_column(ForeignKey("model_registry_versions.id"), nullable=True, index=True)
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    dataset_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    num_samples: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ModelEvaluationMetric(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "model_evaluation_metrics"
    __table_args__ = (
        Index("ix_mem_evaluation_id", "evaluation_id"),
        Index("ix_mem_metric_name", "metric_name"),
        Index("ix_mem_eval_metric", "evaluation_id", "metric_name"),
    )

    evaluation_id: Mapped[int] = mapped_column(ForeignKey("model_evaluations.id"), nullable=False, index=True)
    metric_name: Mapped[str] = mapped_column(String(50), nullable=False)
    metric_value: Mapped[float] = mapped_column(Float, nullable=False)
    config_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    details_json: Mapped[str | None] = mapped_column(Text, nullable=True)
