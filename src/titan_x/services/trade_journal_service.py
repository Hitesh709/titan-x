import math
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import and_, desc, func as sa_func, select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.core.time import utcnow
from titan_x.models.order import Position
from titan_x.models.trade_journal import TradeJournal


class TradeJournalService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_entry(
        self, user_id: int, symbol: str, direction: str,
        entry_date: datetime, entry_price: float, quantity: int,
        reason: str | None = None,
        emotion_before: str | None = None,
        setup_type: str | None = None,
        tags: str | None = None,
    ) -> TradeJournal:
        entry = TradeJournal(
            user_id=user_id,
            symbol=symbol.upper(),
            direction=direction,
            entry_date=entry_date,
            entry_price=entry_price,
            quantity=quantity,
            reason=reason,
            emotion_before=emotion_before,
            setup_type=setup_type,
            tags=tags,
        )
        self.session.add(entry)
        await self.session.flush()
        await self.session.refresh(entry)
        return entry

    async def close_entry(
        self, journal_id: int,
        exit_date: datetime, exit_price: float,
        exit_reason: str | None = None,
        exit_analysis: str | None = None,
        emotion_during: str | None = None,
        emotion_after: str | None = None,
        lessons_learned: str | None = None,
        mistake: str | None = None,
        rating: int | None = None,
    ) -> TradeJournal | None:
        entry = await self.get_entry(journal_id)
        if not entry:
            return None

        entry.exit_date = exit_date
        entry.exit_price = exit_price
        entry.exit_reason = exit_reason
        entry.exit_analysis = exit_analysis
        entry.emotion_during = emotion_during
        entry.emotion_after = emotion_after
        entry.lessons_learned = lessons_learned
        entry.mistake = mistake
        entry.rating = rating
        entry.is_closed = True

        # Calculate PnL
        if entry.direction == "long":
            entry.pnl_amount = round((exit_price - entry.entry_price) * entry.quantity, 2)
            entry.pnl_pct = round((exit_price - entry.entry_price) / entry.entry_price * 100, 2)
        else:
            entry.pnl_amount = round((entry.entry_price - exit_price) * entry.quantity, 2)
            entry.pnl_pct = round((entry.entry_price - exit_price) / entry.entry_price * 100, 2)

        await self.session.flush()
        await self.session.refresh(entry)
        return entry

    async def update_entry(
        self, journal_id: int, **kwargs: Any,
    ) -> TradeJournal | None:
        entry = await self.get_entry(journal_id)
        if not entry:
            return None
        for key, val in kwargs.items():
            if hasattr(entry, key):
                setattr(entry, key, val)
        await self.session.flush()
        await self.session.refresh(entry)
        return entry

    async def get_entry(self, journal_id: int) -> TradeJournal | None:
        r = await self.session.execute(
            select(TradeJournal).where(TradeJournal.id == journal_id)
        )
        return r.scalar_one_or_none()

    async def get_entries(
        self, user_id: int, symbol: str | None = None,
        is_closed: bool | None = None,
        limit: int = 50, offset: int = 0,
    ) -> list[TradeJournal]:
        q = select(TradeJournal).where(TradeJournal.user_id == user_id)
        if symbol:
            q = q.where(TradeJournal.symbol == symbol.upper())
        if is_closed is not None:
            q = q.where(TradeJournal.is_closed == is_closed)
        q = q.order_by(desc(TradeJournal.entry_date)).offset(offset).limit(limit)
        r = await self.session.execute(q)
        return list(r.scalars().all())

    async def get_performance(
        self, user_id: int, symbol: str | None = None,
        days: int | None = None,
    ) -> dict[str, Any]:
        q = select(TradeJournal).where(
            TradeJournal.user_id == user_id,
            TradeJournal.is_closed == True,
        )
        if symbol:
            q = q.where(TradeJournal.symbol == symbol.upper())
        if days:
            cutoff = utcnow() - timedelta(days=days)
            q = q.where(TradeJournal.exit_date >= cutoff)

        r = await self.session.execute(q)
        trades = list(r.scalars().all())

        total = len(trades)
        if total == 0:
            return {
                "total_trades": 0,
                "win_rate": 0,
                "total_pnl": 0,
                "avg_pnl": 0,
                "avg_win": 0,
                "avg_loss": 0,
                "max_win": 0,
                "max_loss": 0,
                "profit_factor": 0,
                "avg_holding_days": 0,
                "best_setup": None,
                "most_common_mistake": None,
            }

        wins = [t for t in trades if t.pnl_amount is not None and t.pnl_amount > 0]
        losses = [t for t in trades if t.pnl_amount is not None and t.pnl_amount <= 0]

        win_rate = round(len(wins) / total * 100, 2)

        total_pnl = round(sum(t.pnl_amount or 0 for t in trades), 2)
        avg_pnl = round(total_pnl / total, 2) if total else 0

        total_win = sum(t.pnl_amount or 0 for t in wins)
        total_loss = abs(sum(t.pnl_amount or 0 for t in losses))
        avg_win = round(total_win / len(wins), 2) if wins else 0
        avg_loss = round(total_loss / len(losses), 2) if losses else 0

        max_win = max((t.pnl_amount or 0) for t in wins) if wins else 0
        max_loss = min((t.pnl_amount or 0) for t in losses) if losses else 0

        profit_factor = round(total_win / total_loss, 2) if total_loss > 0 else float("inf")

        # Avg holding days
        holding_days_list = []
        for t in trades:
            if t.entry_date and t.exit_date:
                diff = (t.exit_date - t.entry_date).total_seconds()
                holding_days_list.append(diff / 86400)
        avg_holding = round(sum(holding_days_list) / len(holding_days_list), 1) if holding_days_list else 0

        # Best setup type
        setup_counts: dict[str, int] = {}
        setup_pnl: dict[str, float] = {}
        for t in trades:
            s = t.setup_type or "unknown"
            setup_counts[s] = setup_counts.get(s, 0) + 1
            setup_pnl[s] = setup_pnl.get(s, 0) + (t.pnl_amount or 0)
        best_setup = max(setup_pnl, key=setup_pnl.get) if setup_pnl else None

        # Most common mistake
        mistake_counts: dict[str, int] = {}
        for t in trades:
            if t.mistake:
                mistake_counts[t.mistake] = mistake_counts.get(t.mistake, 0) + 1
        most_common_mistake = max(mistake_counts, key=mistake_counts.get) if mistake_counts else None

        # Emotion analysis
        emotion_counts: dict[str, int] = {}
        for t in trades:
            if t.emotion_before:
                emotion_counts[t.emotion_before] = emotion_counts.get(t.emotion_before, 0) + 1

        return {
            "total_trades": total,
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": win_rate,
            "total_pnl": total_pnl,
            "avg_pnl": avg_pnl,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "max_win": max_win,
            "max_loss": max_loss,
            "profit_factor": profit_factor,
            "avg_holding_days": avg_holding,
            "best_setup": best_setup,
            "most_common_mistake": most_common_mistake,
            "top_emotions": sorted(emotion_counts.items(), key=lambda x: -x[1])[:5],
        }
