from datetime import date

from sqlalchemy import Date, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from titan_x.db.base import Base
from titan_x.db.mixins import PrimaryKeyMixin, TimestampMixin


class PerformanceSnapshot(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "performance_snapshots"
    __table_args__ = (
        Index("ix_ps_user_date", "user_id", "snapshot_date"),
        Index("ix_ps_user_symbol_date", "user_id", "symbol", "snapshot_date"),
    )

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    symbol: Mapped[str | None] = mapped_column(String(16), nullable=True)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    period_label: Mapped[str] = mapped_column(String(16), nullable=False)

    total_trades: Mapped[int] = mapped_column(Integer, default=0)
    winning_trades: Mapped[int] = mapped_column(Integer, default=0)
    losing_trades: Mapped[int] = mapped_column(Integer, default=0)
    win_rate: Mapped[float] = mapped_column(Float, default=0.0)
    accuracy: Mapped[float | None] = mapped_column(Float, nullable=True)

    total_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    total_pnl_pct: Mapped[float] = mapped_column(Float, default=0.0)
    avg_return: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_win: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    best_trade: Mapped[float | None] = mapped_column(Float, nullable=True)
    worst_trade: Mapped[float | None] = mapped_column(Float, nullable=True)

    profit_factor: Mapped[float | None] = mapped_column(Float, nullable=True)

    max_drawdown: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_drawdown_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_drawdown_pct: Mapped[float | None] = mapped_column(Float, nullable=True)

    sharpe_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    sortino_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    calmar_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)

    annualized_return_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_holding_days: Mapped[float | None] = mapped_column(Float, nullable=True)

    risk_free_rate: Mapped[float] = mapped_column(Float, default=0.02)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
