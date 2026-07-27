from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from titan_x.db.base import Base
from titan_x.db.mixins import PrimaryKeyMixin, TimestampMixin


class DataSource(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "data_sources"
    __table_args__ = (
        UniqueConstraint("name", name="uq_data_source_name"),
        Index("ix_ds_enabled", "enabled"),
    )

    name: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_type: Mapped[str] = mapped_column(String(32), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    config_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rate_limit_per_second: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)


class SyncRun(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "sync_runs"
    __table_args__ = (
        Index("ix_sr_source", "source_id"),
        Index("ix_sr_type", "sync_type"),
        Index("ix_sr_status", "status"),
        Index("ix_sr_started", "started_at"),
    )

    source_id: Mapped[int] = mapped_column(Integer, ForeignKey("data_sources.id"), nullable=False)
    sync_type: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="running", nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    symbol: Mapped[str | None] = mapped_column(String(16), nullable=True)
    date_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    date_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    total_records: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    inserted: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    skipped: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    errors: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)


class SyncAuditLog(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "sync_audit_logs"
    __table_args__ = (
        Index("ix_sal_sync_run", "sync_run_id"),
        Index("ix_sal_event", "event_type"),
        Index("ix_sal_created", "created_at"),
    )

    sync_run_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("sync_runs.id"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    severity: Mapped[str] = mapped_column(String(8), default="info", nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)


class DataChecksum(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "data_checksums"
    __table_args__ = (
        UniqueConstraint("symbol", "trade_date", "data_type", name="uq_checksum_sym_date_type"),
        Index("ix_dc_symbol", "symbol"),
    )

    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    data_type: Mapped[str] = mapped_column(String(16), nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class CollectorQueueItem(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "collector_queue_items"
    __table_args__ = (
        Index("ix_cqi_status", "status"),
        Index("ix_cqi_type", "task_type"),
        Index("ix_cqi_source", "source_id"),
        Index("ix_cqi_priority", "priority"),
    )

    source_id: Mapped[int] = mapped_column(Integer, ForeignKey("data_sources.id"), nullable=False)
    task_type: Mapped[str] = mapped_column(String(32), nullable=False)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DataValidationResult(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "data_validation_results"
    __table_args__ = (
        Index("ix_dvr_symbol", "symbol"),
        Index("ix_dvr_source", "source_id"),
        Index("ix_dvr_status", "status"),
    )

    source_id: Mapped[int] = mapped_column(Integer, ForeignKey("data_sources.id"), nullable=False)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    checks_passed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    checks_failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    errors_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    open: Mapped[float | None] = mapped_column(Float, nullable=True)
    high: Mapped[float | None] = mapped_column(Float, nullable=True)
    low: Mapped[float | None] = mapped_column(Float, nullable=True)
    close: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
