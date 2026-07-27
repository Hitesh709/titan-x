from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from titan_x.db.base import Base
from titan_x.db.mixins import PrimaryKeyMixin, TimestampMixin


class Strategy(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "strategies"
    __table_args__ = (
        Index("ix_strategy_user", "user_id"),
    )

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    entry_criteria_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    exit_criteria_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    risk_rules_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    position_rules_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    filters_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    cloned_from_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("strategies.id", ondelete="SET NULL"), nullable=True)
    schedule_cron: Mapped[str | None] = mapped_column(String(64), nullable=True)
    schedule_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_results_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    optimization_runs: Mapped[list["OptimizationRun"]] = relationship(back_populates="strategy", cascade="all, delete-orphan")


class OptimizationRun(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "optimization_runs"
    __table_args__ = (
        Index("ix_opt_strategy", "strategy_id"),
    )

    strategy_id: Mapped[int] = mapped_column(Integer, ForeignKey("strategies.id", ondelete="CASCADE"), nullable=False)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    initial_capital: Mapped[float] = mapped_column(Float, nullable=False)
    parameter_ranges_json: Mapped[str] = mapped_column(Text, nullable=False)
    metric: Mapped[str] = mapped_column(String(32), nullable=False)
    direction: Mapped[str] = mapped_column(String(8), default="maximize", nullable=False)
    total_combinations: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completed_combinations: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    best_params_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    best_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    best_result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    strategy: Mapped["Strategy"] = relationship(back_populates="optimization_runs")


class StrategyExecution(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "strategy_executions"
    __table_args__ = (
        Index("ix_strat_exec_strategy", "strategy_id"),
        Index("ix_strat_exec_batch", "batch_id"),
        Index("ix_strat_exec_user", "user_id"),
    )

    strategy_id: Mapped[int] = mapped_column(Integer, ForeignKey("strategies.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    execution_type: Mapped[str] = mapped_column(String(16), nullable=False)
    batch_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    as_of_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="running", nullable=False)
    total_results: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    results_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    filters_applied_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    execution_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)


class StrategyShare(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "strategy_shares"
    __table_args__ = (
        UniqueConstraint("strategy_id", "shared_with_user_id", name="uq_strategy_share"),
    )

    strategy_id: Mapped[int] = mapped_column(Integer, ForeignKey("strategies.id", ondelete="CASCADE"), nullable=False, index=True)
    shared_by_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    shared_with_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    permission: Mapped[str] = mapped_column(String(16), default="view", nullable=False)
