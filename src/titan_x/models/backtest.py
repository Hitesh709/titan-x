from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from titan_x.db.base import Base
from titan_x.db.mixins import PrimaryKeyMixin, TimestampMixin


class Backtest(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "backtests"
    __table_args__ = (
        Index("ix_backtest_user_status", "user_id", "status"),
    )

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    initial_capital: Mapped[float] = mapped_column(Float, nullable=False)
    strategy_type: Mapped[str] = mapped_column(String(32), nullable=False)
    strategy_params_json: Mapped[str] = mapped_column(Text, nullable=False)
    config_json: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="draft", nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    trades: Mapped[list["BacktestTrade"]] = relationship(back_populates="backtest", cascade="all, delete-orphan")
    signals: Mapped[list["BacktestSignal"]] = relationship(back_populates="backtest", cascade="all, delete-orphan")
    equity_curve: Mapped[list["BacktestEquityPoint"]] = relationship(back_populates="backtest", cascade="all, delete-orphan")
    report: Mapped["BacktestReport | None"] = relationship(back_populates="backtest", uselist=False, cascade="all, delete-orphan")


class BacktestTrade(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "backtest_trades"
    __table_args__ = (
        Index("ix_bt_backtest", "backtest_id"),
    )

    backtest_id: Mapped[int] = mapped_column(Integer, ForeignKey("backtests.id", ondelete="CASCADE"), nullable=False)
    trade_number: Mapped[int] = mapped_column(Integer, nullable=False)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(String(8), default="open", nullable=False)
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    entry_signal: Mapped[str | None] = mapped_column(String(32), nullable=True)
    exit_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    exit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    exit_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    exit_signal: Mapped[str | None] = mapped_column(String(32), nullable=True)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    commission: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    slippage: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    pnl: Mapped[float | None] = mapped_column(Float, nullable=True)
    pnl_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    holding_days: Mapped[int | None] = mapped_column(Integer, nullable=True)

    backtest: Mapped["Backtest"] = relationship(back_populates="trades")


class BacktestSignal(PrimaryKeyMixin, Base):
    __tablename__ = "backtest_signals"
    __table_args__ = (
        Index("ix_bs_backtest", "backtest_id"),
    )

    backtest_id: Mapped[int] = mapped_column(Integer, ForeignKey("backtests.id", ondelete="CASCADE"), nullable=False)
    trade_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("backtest_trades.id", ondelete="SET NULL"), nullable=True)
    signal_date: Mapped[date] = mapped_column(Date, nullable=False)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    action: Mapped[str] = mapped_column(String(8), nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    signal_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    backtest: Mapped["Backtest"] = relationship(back_populates="signals")


class BacktestEquityPoint(PrimaryKeyMixin, Base):
    __tablename__ = "backtest_equity_curve"
    __table_args__ = (
        Index("ix_bec_backtest_date", "backtest_id", "date"),
    )

    backtest_id: Mapped[int] = mapped_column(Integer, ForeignKey("backtests.id", ondelete="CASCADE"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    equity: Mapped[float] = mapped_column(Float, nullable=False)
    cash: Mapped[float] = mapped_column(Float, nullable=False)
    holdings_value: Mapped[float] = mapped_column(Float, nullable=False)
    returns_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    drawdown_pct: Mapped[float | None] = mapped_column(Float, nullable=True)

    backtest: Mapped["Backtest"] = relationship(back_populates="equity_curve")


class BacktestReport(PrimaryKeyMixin, Base):
    __tablename__ = "backtest_reports"
    __table_args__ = (
        Index("ix_br_backtest", "backtest_id"),
    )

    backtest_id: Mapped[int] = mapped_column(Integer, ForeignKey("backtests.id", ondelete="CASCADE"), nullable=False, unique=True)
    total_return: Mapped[float] = mapped_column(Float, nullable=False)
    total_return_pct: Mapped[float] = mapped_column(Float, nullable=False)
    annualized_return_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_trades: Mapped[int] = mapped_column(Integer, nullable=False)
    winning_trades: Mapped[int] = mapped_column(Integer, nullable=False)
    losing_trades: Mapped[int] = mapped_column(Integer, nullable=False)
    win_rate: Mapped[float] = mapped_column(Float, nullable=False)
    profit_factor: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_drawdown: Mapped[float] = mapped_column(Float, nullable=False)
    max_drawdown_pct: Mapped[float] = mapped_column(Float, nullable=False)
    avg_drawdown: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_drawdown_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    sharpe_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    sortino_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    calmar_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_win: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_holding_days: Mapped[float | None] = mapped_column(Float, nullable=True)
    best_trade_pnl: Mapped[float | None] = mapped_column(Float, nullable=True)
    worst_trade_pnl: Mapped[float | None] = mapped_column(Float, nullable=True)
    starting_equity: Mapped[float] = mapped_column(Float, nullable=False)
    ending_equity: Mapped[float] = mapped_column(Float, nullable=False)
    total_commission: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    total_slippage: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    metrics_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    backtest: Mapped["Backtest"] = relationship(back_populates="report")
