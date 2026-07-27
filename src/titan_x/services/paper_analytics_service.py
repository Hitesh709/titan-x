from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from math import sqrt
from statistics import stdev
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.db.repository import BaseRepository
from titan_x.models.paper_trading import PaperAccount, PaperPosition, SimulatedOrder

logger = structlog.get_logger(__name__)


class PaperAnalyticsService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._account_repo = BaseRepository(session, PaperAccount)
        self._position_repo = BaseRepository(session, PaperPosition)
        self._simulated_repo = BaseRepository(session, SimulatedOrder)

    async def compute_analytics(
        self, user_id: int, risk_free_rate: float = 0.05,
    ) -> dict[str, Any]:
        account = await self._get_account(user_id)
        if account is None:
            return {}

        closed_sims = await self._get_closed_simulated_orders(user_id)
        total_closed = len(closed_sims)
        pos_value, unrealized = await self._get_positions_value(account.id)

        win_rate = self._compute_win_rate(closed_sims, total_closed)
        profit_factor = self._compute_profit_factor(closed_sims)
        expectancy = self._compute_expectancy(closed_sims, total_closed)

        equity_curve = self._build_equity_curve(account.initial_capital, closed_sims, unrealized)
        returns = self._compute_period_returns(equity_curve)

        sharpe_ratio = self._compute_sharpe(returns, risk_free_rate)
        sortino_ratio = self._compute_sortino(returns, risk_free_rate)
        max_dd, max_dd_pct = self._compute_max_drawdown(equity_curve)
        cagr = self._compute_cagr(account.initial_capital, account.cash_balance + pos_value, closed_sims)

        return {
            "cagr": cagr,
            "win_rate": round(win_rate, 4),
            "profit_factor": round(profit_factor, 4) if profit_factor is not None else None,
            "sharpe_ratio": round(sharpe_ratio, 4) if sharpe_ratio is not None else None,
            "sortino_ratio": round(sortino_ratio, 4) if sortino_ratio is not None else None,
            "max_drawdown": round(max_dd_pct, 4) if max_dd_pct is not None else None,
            "max_drawdown_amount": round(float(max_dd), 2) if max_dd is not None else None,
            "expectancy": round(expectancy, 4) if expectancy is not None else None,
            "total_trades": total_closed,
            "winning_trades": sum(1 for s in closed_sims if s.outcome == "win"),
            "losing_trades": sum(1 for s in closed_sims if s.outcome == "loss"),
            "breakeven_trades": sum(1 for s in closed_sims if s.outcome == "breakeven"),
        }

    async def _get_account(self, user_id: int) -> PaperAccount | None:
        result = await self._session.execute(
            select(PaperAccount).where(PaperAccount.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def _get_closed_simulated_orders(self, user_id: int) -> Sequence[SimulatedOrder]:
        result = await self._session.execute(
            select(SimulatedOrder)
            .where(SimulatedOrder.user_id == user_id, SimulatedOrder.status == "closed")
            .order_by(SimulatedOrder.exit_date)
        )
        return result.scalars().all()

    async def _get_positions_value(self, account_id: int) -> tuple[Decimal, Decimal]:
        positions = (await self._session.execute(
            select(PaperPosition).where(PaperPosition.account_id == account_id)
        )).scalars().all()
        total_value = Decimal("0")
        unrealized = Decimal("0")
        for p in positions:
            if p.current_price and p.quantity:
                mkt_val = p.current_price * p.quantity
                total_value += mkt_val
                unrealized += mkt_val - p.cost_basis
        return total_value, unrealized

    def _compute_win_rate(self, closed_sims: Sequence[SimulatedOrder], total: int) -> float:
        if total == 0:
            return 0.0
        wins = sum(1 for s in closed_sims if s.outcome == "win")
        return wins / total

    def _compute_profit_factor(self, closed_sims: Sequence[SimulatedOrder]) -> float | None:
        gross_profit = sum(s.net_pnl for s in closed_sims if s.net_pnl and s.net_pnl > 0)
        gross_loss = abs(sum(s.net_pnl for s in closed_sims if s.net_pnl and s.net_pnl < 0))
        if gross_loss == 0:
            return float("inf") if gross_profit > 0 else None
        return float(gross_profit / gross_loss)

    def _compute_expectancy(self, closed_sims: Sequence[SimulatedOrder], total: int) -> float | None:
        if total == 0:
            return None
        total_net = sum(s.net_pnl for s in closed_sims if s.net_pnl is not None)
        return float(total_net) / total

    def _build_equity_curve(
        self, initial_capital: Decimal,
        closed_sims: Sequence[SimulatedOrder],
        unrealized_pnl: Decimal,
    ) -> list[Decimal]:
        curve = [initial_capital]
        running = initial_capital
        for sim in closed_sims:
            if sim.net_pnl is not None:
                running += sim.net_pnl
                curve.append(running)
        if unrealized_pnl != 0:
            curve.append(running + unrealized_pnl)
        return curve

    def _compute_period_returns(self, equity_curve: list[Decimal]) -> list[float]:
        if len(equity_curve) < 2:
            return []
        return [
            float((equity_curve[i] - equity_curve[i - 1]) / equity_curve[i - 1])
            for i in range(1, len(equity_curve))
        ]

    def _compute_sharpe(
        self, returns: list[float], risk_free_rate: float,
    ) -> float | None:
        if len(returns) < 2:
            return None
        period_rf = risk_free_rate / 252
        excess = [r - period_rf for r in returns]
        mean_excess = sum(excess) / len(excess)
        sigma = stdev(excess)
        if sigma == 0:
            return None
        return mean_excess / sigma * sqrt(252)

    def _compute_sortino(
        self, returns: list[float], risk_free_rate: float,
    ) -> float | None:
        if len(returns) < 2:
            return None
        period_rf = risk_free_rate / 252
        excess = [r - period_rf for r in returns]
        mean_excess = sum(excess) / len(excess)
        downside = [r for r in excess if r < 0]
        if not downside:
            return float("inf") if mean_excess > 0 else None
        downside_var = sum(d * d for d in downside) / len(downside)
        downside_std = sqrt(downside_var)
        if downside_std == 0:
            return None
        return mean_excess / downside_std * sqrt(252)

    def _compute_max_drawdown(
        self, equity_curve: list[Decimal],
    ) -> tuple[Decimal | None, float | None]:
        if len(equity_curve) < 2:
            return None, None
        peak = equity_curve[0]
        max_dd = Decimal("0")
        max_dd_pct = 0.0
        for value in equity_curve[1:]:
            if value > peak:
                peak = value
            dd = peak - value
            dd_pct = float(dd / peak) if peak > 0 else 0
            if dd > max_dd:
                max_dd = dd
                max_dd_pct = dd_pct
        return max_dd, max_dd_pct

    def _compute_cagr(
        self, initial_capital: Decimal, current_portfolio_value: Decimal,
        closed_sims: Sequence[SimulatedOrder],
    ) -> float | None:
        if not closed_sims or initial_capital == 0 or current_portfolio_value <= 0:
            return None
        first_exit = closed_sims[0].exit_date
        if first_exit is None:
            return None
        end_date = datetime.now()
        years = (end_date - first_exit).total_seconds() / (365.25 * 86400)
        if years <= 0:
            return None
        ratio = float(current_portfolio_value / initial_capital)
        if ratio <= 0:
            return None
        return round(ratio ** (1 / years) - 1, 6)
