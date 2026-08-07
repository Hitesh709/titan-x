from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.models.performance_snapshot import PerformanceSnapshot
from titan_x.models.trade_journal import TradeJournal
from titan_x.services.performance_analyzer import PerformanceAnalyzer


class PerformanceMeasurementService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.analyzer = PerformanceAnalyzer()

    async def take_snapshot(
        self, user_id: int,
        snapshot_date: date | None = None,
        symbol: str | None = None,
        period_label: str = "all",
        initial_capital: float = 100_000.0,
        risk_free_rate: float = 0.02,
    ) -> PerformanceSnapshot:
        if snapshot_date is None:
            snapshot_date = date.today()

        trades = await self._get_closed_trades(user_id, symbol=symbol)
        if not trades:
            return await self._store_empty_snapshot(user_id, snapshot_date, symbol, period_label)

        total_trades = len(trades)
        winners = [t for t in trades if t.pnl_amount is not None and t.pnl_amount > 0]
        losers = [t for t in trades if t.pnl_amount is not None and t.pnl_amount <= 0]
        winning_trades = len(winners)
        losing_trades = len(losers)
        win_rate = round(winning_trades / total_trades * 100, 2) if total_trades else 0.0

        total_pnl = round(sum(t.pnl_amount or 0 for t in trades), 2)
        total_pnl_pct = round(sum(t.pnl_pct or 0 for t in trades), 2)
        avg_return = round(total_pnl / total_trades, 2) if total_trades else None
        avg_win = round(sum(t.pnl_amount or 0 for t in winners) / winning_trades, 2) if winning_trades else None
        avg_loss = round(sum(t.pnl_amount or 0 for t in losers) / losing_trades, 2) if losing_trades else None
        best_trade = max((t.pnl_amount or 0) for t in trades) if trades else None
        worst_trade = min((t.pnl_amount or 0) for t in trades) if trades else None

        gross_profit = sum(t.pnl_amount or 0 for t in winners) if winners else 0.0
        gross_loss = abs(sum(t.pnl_amount or 0 for t in losers)) if losers else 0.0
        profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else None

        holding_days_list = []
        for t in trades:
            if t.entry_date and t.exit_date:
                diff = (t.exit_date - t.entry_date).total_seconds()
                holding_days_list.append(diff / 86400)
        avg_holding_days = round(sum(holding_days_list) / len(holding_days_list), 1) if holding_days_list else None

        equity_curve = self._build_equity_curve(trades, initial_capital)
        dd = self.analyzer.calculate_drawdown(equity_curve)
        daily_returns = self.analyzer.calculate_daily_returns(equity_curve)
        sharpe = self.analyzer.calculate_sharpe(daily_returns, risk_free_rate)
        sortino = self.analyzer.calculate_sortino(daily_returns, risk_free_rate)

        start_date = min(t.entry_date.date() for t in trades if t.entry_date)
        end_date = max(t.exit_date.date() for t in trades if t.exit_date)
        annualized_return = self.analyzer.calculate_annualized_return(
            initial_capital,
            initial_capital + total_pnl,
            start_date,
            end_date,
        )
        calmar = self.analyzer.calculate_calmar(annualized_return, dd.get("max_drawdown_pct", 0))

        accuracy = round(winning_trades / total_trades * 100, 2) if total_trades else None

        snapshot = PerformanceSnapshot(
            user_id=user_id,
            symbol=symbol.upper() if symbol else None,
            snapshot_date=snapshot_date,
            period_label=period_label,
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            accuracy=accuracy,
            total_pnl=total_pnl,
            total_pnl_pct=total_pnl_pct,
            avg_return=avg_return,
            avg_win=avg_win,
            avg_loss=avg_loss,
            best_trade=best_trade,
            worst_trade=worst_trade,
            profit_factor=profit_factor,
            max_drawdown=dd.get("max_drawdown"),
            max_drawdown_pct=dd.get("max_drawdown_pct"),
            avg_drawdown_pct=dd.get("avg_drawdown_pct"),
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            calmar_ratio=calmar,
            annualized_return_pct=annualized_return,
            avg_holding_days=avg_holding_days,
            risk_free_rate=risk_free_rate,
        )
        self.session.add(snapshot)
        await self.session.flush()
        await self.session.refresh(snapshot)
        return snapshot

    async def get_snapshot(self, snapshot_id: int) -> PerformanceSnapshot | None:
        r = await self.session.execute(
            select(PerformanceSnapshot).where(PerformanceSnapshot.id == snapshot_id)
        )
        return r.scalar_one_or_none()

    async def get_snapshots(
        self, user_id: int, symbol: str | None = None,
        period_label: str | None = None,
        limit: int = 50, offset: int = 0,
    ) -> list[PerformanceSnapshot]:
        q = select(PerformanceSnapshot).where(PerformanceSnapshot.user_id == user_id)
        if symbol:
            q = q.where(PerformanceSnapshot.symbol == symbol.upper())
        if period_label:
            q = q.where(PerformanceSnapshot.period_label == period_label)
        q = q.order_by(desc(PerformanceSnapshot.snapshot_date)).offset(offset).limit(limit)
        r = await self.session.execute(q)
        return list(r.scalars().all())

    async def count_snapshots(self, user_id: int, symbol: str | None = None, period_label: str | None = None) -> int:
        q = select(func.count()).select_from(PerformanceSnapshot).where(PerformanceSnapshot.user_id == user_id)
        if symbol:
            q = q.where(PerformanceSnapshot.symbol == symbol.upper())
        if period_label:
            q = q.where(PerformanceSnapshot.period_label == period_label)
        return (await self.session.execute(q)).scalar() or 0

    async def get_latest(
        self, user_id: int, symbol: str | None = None,
        period_label: str | None = None,
    ) -> PerformanceSnapshot | None:
        q = select(PerformanceSnapshot).where(PerformanceSnapshot.user_id == user_id)
        if symbol:
            q = q.where(PerformanceSnapshot.symbol == symbol.upper())
        if period_label:
            q = q.where(PerformanceSnapshot.period_label == period_label)
        q = q.order_by(desc(PerformanceSnapshot.snapshot_date)).limit(1)
        r = await self.session.execute(q)
        return r.scalar_one_or_none()

    async def get_trend(
        self, user_id: int, symbol: str | None = None,
        limit: int = 30,
    ) -> list[dict[str, Any]]:
        q = select(PerformanceSnapshot).where(PerformanceSnapshot.user_id == user_id)
        if symbol:
            q = q.where(PerformanceSnapshot.symbol == symbol.upper())
        q = q.order_by(desc(PerformanceSnapshot.snapshot_date)).limit(limit)
        r = await self.session.execute(q)
        snapshots = list(r.scalars().all())
        return [self._snapshot_dict(s) for s in reversed(snapshots)]

    async def _get_closed_trades(
        self, user_id: int, symbol: str | None = None,
    ) -> list[TradeJournal]:
        q = select(TradeJournal).where(
            TradeJournal.user_id == user_id,
            TradeJournal.is_closed == True,
        )
        if symbol:
            q = q.where(TradeJournal.symbol == symbol.upper())
        q = q.order_by(TradeJournal.exit_date)
        r = await self.session.execute(q)
        return list(r.scalars().all())

    def _build_equity_curve(
        self, trades: list[TradeJournal], initial_capital: float,
    ) -> list[dict[str, Any]]:
        curve: list[dict[str, Any]] = [{"date": date.min, "equity": initial_capital}]
        equity = initial_capital
        for t in trades:
            if t.exit_date and t.pnl_amount is not None:
                equity += t.pnl_amount
                curve.append({
                    "date": t.exit_date.date(),
                    "equity": equity,
                })
        if len(curve) == 1:
            return [{"date": date.today(), "equity": initial_capital}]
        return curve

    async def _store_empty_snapshot(
        self, user_id: int, snapshot_date: date,
        symbol: str | None, period_label: str,
    ) -> PerformanceSnapshot:
        snapshot = PerformanceSnapshot(
            user_id=user_id,
            symbol=symbol.upper() if symbol else None,
            snapshot_date=snapshot_date,
            period_label=period_label,
        )
        self.session.add(snapshot)
        await self.session.flush()
        await self.session.refresh(snapshot)
        return snapshot

    def _snapshot_dict(self, s: PerformanceSnapshot) -> dict[str, Any]:
        return {
            "id": s.id,
            "snapshot_date": s.snapshot_date.isoformat(),
            "period_label": s.period_label,
            "symbol": s.symbol,
            "total_trades": s.total_trades,
            "winning_trades": s.winning_trades,
            "losing_trades": s.losing_trades,
            "win_rate": s.win_rate,
            "accuracy": s.accuracy,
            "total_pnl": s.total_pnl,
            "total_pnl_pct": s.total_pnl_pct,
            "avg_return": s.avg_return,
            "avg_win": s.avg_win,
            "avg_loss": s.avg_loss,
            "best_trade": s.best_trade,
            "worst_trade": s.worst_trade,
            "profit_factor": s.profit_factor,
            "max_drawdown": s.max_drawdown,
            "max_drawdown_pct": s.max_drawdown_pct,
            "avg_drawdown_pct": s.avg_drawdown_pct,
            "sharpe_ratio": s.sharpe_ratio,
            "sortino_ratio": s.sortino_ratio,
            "calmar_ratio": s.calmar_ratio,
            "annualized_return_pct": s.annualized_return_pct,
            "avg_holding_days": s.avg_holding_days,
            "risk_free_rate": s.risk_free_rate,
        }
