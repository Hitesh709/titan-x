from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from titan_x.db.base import Base
from titan_x.db.mixins import PrimaryKeyMixin, TimestampMixin


class AIModelRegistry(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ai_model_registry"
    __table_args__ = (UniqueConstraint("name", "version", name="uq_model_version"),)

    name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_type: Mapped[str] = mapped_column(String(50), nullable=False)
    model_metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    metrics_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    deployments: Mapped[list["ModelDeployment"]] = relationship(back_populates="model", cascade="all, delete-orphan")


class ModelDeployment(PrimaryKeyMixin, Base):
    __tablename__ = "model_deployments"
    __table_args__ = (UniqueConstraint("model_id", "environment", name="uq_model_env"),)

    model_id: Mapped[int] = mapped_column(ForeignKey("ai_model_registry.id"), nullable=False, index=True)
    environment: Mapped[str] = mapped_column(String(20), nullable=False)
    deployed_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")
    deployed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    model: Mapped["AIModelRegistry"] = relationship(back_populates="deployments")
