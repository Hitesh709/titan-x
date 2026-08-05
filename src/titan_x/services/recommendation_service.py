from datetime import datetime, timezone
from typing import Any

from sqlalchemy import asc, case, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.models.recommendation import Recommendation

SIGNAL_ORDER = {"strong_buy": 1, "buy": 2, "hold": 3, "sell": 4, "strong_sell": 5}
RISK_ORDER = {"Low": 1, "Medium": 2, "High": 3}


def _order_expression(sort_by: str, sort_desc: bool):
    """Build the ORDER BY expression for the given sort key.

    Supports plain columns plus a few custom, semantically-ordered keys:
    ``signal`` (strong_buy -> strong_sell) and ``risk_level`` (Low -> High).
    """
    if sort_by == "signal":
        # Fall back to the coarse direction when the granular signal is missing.
        signal_expr = func.coalesce(
            Recommendation.signal,
            case({"BUY": "buy", "SELL": "sell", "HOLD": "hold"}, value=Recommendation.direction, else_="hold"),
        )
        expr = case(SIGNAL_ORDER, value=signal_expr, else_=6)
    elif sort_by == "risk_level":
        expr = case(RISK_ORDER, value=Recommendation.risk_level, else_=4)
    else:
        col = getattr(Recommendation, sort_by, Recommendation.generated_at)
        return desc(col) if sort_desc else asc(col)

    return (desc(expr) if sort_desc else asc(expr)).nulls_last()


class RecommendationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_recommendation(
        self,
        symbol: str,
        direction: str,
        signal: str | None = None,
        confidence: float | None = None,
        price_target: float | None = None,
        current_price: float | None = None,
        timeframe: str | None = None,
        reasoning: str | None = None,
        recommendation_type: str | None = None,
        score: float | None = None,
        risk_level: str | None = None,
        predicted_return_pct: float | None = None,
        source: str | None = None,
        metadata_json: str | None = None,
        status: str = "active",
        expires_at: datetime | None = None,
        inputs_json: str | None = None,
        model_version_id: int | None = None,
        model_version_label: str | None = None,
    ) -> Recommendation:
        rec = Recommendation(
            symbol=symbol.upper(),
            direction=direction,
            signal=signal,
            confidence=confidence,
            price_target=price_target,
            current_price=current_price,
            timeframe=timeframe,
            reasoning=reasoning,
            recommendation_type=recommendation_type,
            score=score,
            risk_level=risk_level,
            predicted_return_pct=predicted_return_pct,
            source=source,
            metadata_json=metadata_json,
            status=status,
            generated_at=datetime.now(timezone.utc).replace(tzinfo=None),
            expires_at=expires_at,
            inputs_json=inputs_json,
            model_version_id=model_version_id,
            model_version_label=model_version_label,
        )
        self.session.add(rec)
        await self.session.flush()
        await self.session.refresh(rec)
        return rec

    async def get_recommendation(self, rec_id: int) -> Recommendation | None:
        return await self.session.get(Recommendation, rec_id)

    async def list_recommendations(
        self,
        symbol: str | None = None,
        direction: str | None = None,
        status: str | None = None,
        recommendation_type: str | None = None,
        timeframe: str | None = None,
        min_confidence: float | None = None,
        min_score: float | None = None,
        source: str | None = None,
        risk_level: str | None = None,
        decision: str | None = None,
        outcome: str | None = None,
        sort_by: str = "generated_at",
        sort_desc: bool = True,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Recommendation]:
        q = select(Recommendation)
        if symbol is not None:
            q = q.where(Recommendation.symbol == symbol.upper())
        if direction is not None:
            q = q.where(Recommendation.direction == direction)
        if status is not None:
            q = q.where(Recommendation.status == status)
        if recommendation_type is not None:
            q = q.where(Recommendation.recommendation_type == recommendation_type)
        if timeframe is not None:
            q = q.where(Recommendation.timeframe == timeframe)
        if min_confidence is not None:
            q = q.where(Recommendation.confidence >= min_confidence)
        if min_score is not None:
            q = q.where(Recommendation.score >= min_score)
        if source is not None:
            q = q.where(Recommendation.source == source)
        if risk_level is not None:
            q = q.where(Recommendation.risk_level == risk_level)
        if decision is not None:
            q = q.where(Recommendation.decision == decision)
        if outcome is not None:
            q = q.where(Recommendation.outcome == outcome)

        q = q.order_by(_order_expression(sort_by, sort_desc))
        q = q.offset(offset).limit(limit)
        r = await self.session.execute(q)
        return list(r.scalars().all())

    async def get_top_recommendations(
        self,
        limit: int = 10,
        status: str = "active",
        min_score: float | None = None,
    ) -> list[Recommendation]:
        q = select(Recommendation).where(Recommendation.status == status)
        if min_score is not None:
            q = q.where(Recommendation.score >= min_score)
        q = q.order_by(desc(Recommendation.score)).limit(limit)
        r = await self.session.execute(q)
        return list(r.scalars().all())

    async def get_recommendation_history(
        self,
        symbol: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Recommendation]:
        r = await self.session.execute(
            select(Recommendation)
            .where(Recommendation.symbol == symbol.upper())
            .order_by(desc(Recommendation.generated_at))
            .offset(offset)
            .limit(limit)
        )
        return list(r.scalars().all())

    async def get_recommendations_by_symbol(
        self,
        symbol: str,
        status: str | None = "active",
        limit: int = 20,
        offset: int = 0,
    ) -> list[Recommendation]:
        q = select(Recommendation).where(Recommendation.symbol == symbol.upper())
        if status is not None:
            q = q.where(Recommendation.status == status)
        q = q.order_by(desc(Recommendation.score)).offset(offset).limit(limit)
        r = await self.session.execute(q)
        return list(r.scalars().all())

    async def count_recommendations(
        self,
        symbol: str | None = None,
        direction: str | None = None,
        status: str | None = None,
    ) -> int:
        from sqlalchemy import func as sa_func

        q = select(sa_func.count(Recommendation.id))
        if symbol is not None:
            q = q.where(Recommendation.symbol == symbol.upper())
        if direction is not None:
            q = q.where(Recommendation.direction == direction)
        if status is not None:
            q = q.where(Recommendation.status == status)
        r = await self.session.execute(q)
        return r.scalar_one()

    async def update_status(self, rec_id: int, status: str) -> Recommendation | None:
        rec = await self.get_recommendation(rec_id)
        if not rec:
            return None
        rec.status = status
        await self.session.flush()
        await self.session.refresh(rec)
        return rec

    async def set_decision(
        self,
        rec_id: int,
        decision: str,
        decision_reason: str | None = None,
    ) -> Recommendation | None:
        rec = await self.get_recommendation(rec_id)
        if not rec:
            return None
        rec.decision = decision
        if decision_reason is not None:
            rec.decision_reason = decision_reason
        rec.decided_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await self.session.flush()
        await self.session.refresh(rec)
        return rec

    async def set_outcome(
        self,
        rec_id: int,
        outcome: str,
        actual_outcome_pnl: float | None = None,
        outcome_details: str | None = None,
    ) -> Recommendation | None:
        rec = await self.get_recommendation(rec_id)
        if not rec:
            return None
        rec.outcome = outcome
        if actual_outcome_pnl is not None:
            rec.actual_outcome_pnl = actual_outcome_pnl
        if outcome_details is not None:
            rec.outcome_details = outcome_details
        rec.resolved_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await self.session.flush()
        await self.session.refresh(rec)
        return rec
