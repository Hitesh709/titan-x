from datetime import datetime, timezone

from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from titan_x.db.base import Base
from titan_x.db.mixins import PrimaryKeyMixin, TimestampMixin


class FeatureStoreEntity(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "feature_store_entities"
    __table_args__ = (
        UniqueConstraint("name", name="uq_fse_name"),
        Index("ix_fse_status", "status"),
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class FeatureStoreDef(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "feature_store_defs"
    __table_args__ = (
        UniqueConstraint("entity_id", "name", name="uq_fsd_entity_name"),
        Index("ix_fsd_entity_id", "entity_id"),
        Index("ix_fsd_feature_type", "feature_type"),
        Index("ix_fsd_status", "status"),
        Index("ix_fsd_online", "is_online"),
    )

    entity_id: Mapped[int] = mapped_column(ForeignKey("feature_store_entities.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    feature_type: Mapped[str] = mapped_column(String(30), default="numerical")
    source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_expression: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")
    is_online: Mapped[bool] = mapped_column(Boolean, default=True)
    is_offline: Mapped[bool] = mapped_column(Boolean, default=True)
    immutable: Mapped[bool] = mapped_column(Boolean, default=False)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class FeatureVersion(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "feature_store_versions"
    __table_args__ = (
        UniqueConstraint("feature_id", "version", name="uq_fsv_feature_version"),
        Index("ix_fsv_feature_id", "feature_id"),
        Index("ix_fsv_status", "status"),
    )

    feature_id: Mapped[int] = mapped_column(ForeignKey("feature_store_defs.id"), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(20), nullable=False)
    definition_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    change_log: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class FeatureStoreValue(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "feature_store_values"
    __table_args__ = (
        UniqueConstraint("feature_id", "entity_key", name="uq_fsv_val_feature_key"),
        Index("ix_fsv_val_feature_id", "feature_id"),
        Index("ix_fsv_val_entity_key", "entity_key"),
        Index("ix_fsv_val_expires_at", "expires_at"),
    )

    feature_id: Mapped[int] = mapped_column(ForeignKey("feature_store_defs.id"), nullable=False, index=True)
    entity_key: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    value_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    ttl_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        return now > self.expires_at


class FeatureOfflineStore(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "feature_offline_store"
    __table_args__ = (
        Index("ix_fos_feature_id", "feature_id"),
        Index("ix_fos_entity_key", "entity_key"),
        Index("ix_fos_batch_id", "batch_id"),
        Index("ix_fos_as_of_date", "as_of_date"),
        Index("ix_fos_feature_as_of", "feature_id", "as_of_date"),
    )

    feature_id: Mapped[int] = mapped_column(ForeignKey("feature_store_defs.id"), nullable=False, index=True)
    entity_key: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    value_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    batch_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    as_of_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class FeatureLineage(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "feature_store_lineage"
    __table_args__ = (
        UniqueConstraint("feature_id", "source_name", name="uq_fsl_feature_source"),
        Index("ix_fsl_feature_id", "feature_id"),
        Index("ix_fsl_source_type", "source_type"),
    )

    feature_id: Mapped[int] = mapped_column(ForeignKey("feature_store_defs.id"), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(30), nullable=False)
    source_name: Mapped[str] = mapped_column(String(200), nullable=False)
    source_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    transformation_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    dependencies_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class FeatureValidationRule(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "feature_store_validation_rules"
    __table_args__ = (
        UniqueConstraint("feature_id", "name", name="uq_fsvr_feature_name"),
        Index("ix_fsvr_feature_id", "feature_id"),
        Index("ix_fsvr_rule_type", "rule_type"),
        Index("ix_fsvr_severity", "severity"),
        Index("ix_fsvr_status", "status"),
    )

    feature_id: Mapped[int | None] = mapped_column(ForeignKey("feature_store_defs.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    rule_type: Mapped[str] = mapped_column(String(30), nullable=False)
    config_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    severity: Mapped[str] = mapped_column(String(10), default="error")
    status: Mapped[str] = mapped_column(String(20), default="active")


class FeatureValidationResult(PrimaryKeyMixin, Base):
    __tablename__ = "feature_store_validation_results"
    __table_args__ = (
        Index("ix_fsvr2_rule_id", "rule_id"),
        Index("ix_fsvr2_feature_id", "feature_id"),
        Index("ix_fsvr2_batch_id", "batch_id"),
        Index("ix_fsvr2_status", "status"),
        Index("ix_fsvr2_validated_at", "validated_at"),
    )

    rule_id: Mapped[int] = mapped_column(ForeignKey("feature_store_validation_rules.id"), nullable=False, index=True)
    feature_id: Mapped[int] = mapped_column(ForeignKey("feature_store_defs.id"), nullable=False, index=True)
    batch_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    entity_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    actual_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    validated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )
