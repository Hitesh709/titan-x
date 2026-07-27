import json
from collections.abc import Sequence
from datetime import date, timedelta
from typing import Any

import structlog
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.db.repository import BaseRepository
from titan_x.models.decision import TradingDecision

logger = structlog.get_logger(__name__)

OPPORTUNITY_WEIGHTS = {
    "pattern_score": 0.25,
    "similarity_score": 0.20,
    "technical_score": 0.20,
    "sector_score": 0.15,
    "sentiment_score": 0.10,
    "breadth_score": 0.10,
}

CONFIDENCE_WEIGHTS = {
    "signal_consistency": 0.30,
    "risk_inversion": 0.25,
    "data_quality": 0.20,
    "pattern_clarity": 0.15,
    "historical_reliability": 0.10,
}


class DecisionEngine:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = BaseRepository(session, TradingDecision)

    def combine_scores(self, scores: dict[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = {"input_scores": scores}
        opportunity = self._compute_opportunity(scores)
        confidence = self._compute_confidence(scores, opportunity)
        recommendation, code = self._get_recommendation(opportunity, confidence)
        explanation = self._generate_explanation(scores, opportunity, confidence, recommendation)

        result.update({
            "opportunity_score": round(opportunity, 2),
            "confidence_score": round(confidence, 2),
            "recommendation": recommendation,
            "recommendation_code": code,
            "explanation": explanation,
            "pattern_score": scores.get("pattern_score"),
            "similarity_score": scores.get("similarity_score"),
            "technical_score": scores.get("technical_score"),
            "sector_score": scores.get("sector_score"),
            "sentiment_score": scores.get("sentiment_score"),
            "breadth_score": scores.get("breadth_score"),
            "risk_score": scores.get("risk_score"),
            "fundamental_score": scores.get("fundamental_score"),
        })
        return result

    def _compute_opportunity(self, scores: dict[str, Any]) -> float:
        op = 50.0
        weighted_sum = 0.0
        total_weight = 0.0

        for key, weight in OPPORTUNITY_WEIGHTS.items():
            val = scores.get(key)
            if val is not None:
                if key == "sentiment_score":
                    norm = (val + 100) / 2
                else:
                    norm = max(0, min(100, val))
                weighted_sum += norm * weight
                total_weight += weight

        if total_weight > 0:
            op = weighted_sum / total_weight

        risk = scores.get("risk_score")
        if risk is not None:
            risk_penalty = max(0, risk - 50) * 0.3
            op -= risk_penalty

        similarity_returns = scores.get("similarity_forward_return")
        if similarity_returns is not None:
            ret_bonus = max(-10, min(20, similarity_returns))
            op += ret_bonus

        sector = scores.get("sector_rotation")
        if sector == "leading":
            op += 5
        elif sector == "lagging":
            op -= 5

        return max(0, min(100, op))

    def _compute_confidence(self, scores: dict[str, Any], opportunity: float) -> float:
        cf = 50.0

        available = [k for k in OPPORTUNITY_WEIGHTS if scores.get(k) is not None]
        consistency = len(available) / max(len(OPPORTUNITY_WEIGHTS), 1) * 100
        cf += consistency * CONFIDENCE_WEIGHTS["signal_consistency"]

        risk = scores.get("risk_score")
        if risk is not None:
            risk_inv = max(0, 100 - risk)
            cf += risk_inv * CONFIDENCE_WEIGHTS["risk_inversion"]

        data_quality = 50.0
        liq = scores.get("liquidity_score")
        if liq is not None:
            data_quality = liq
        vol = scores.get("avg_daily_volume_20d")
        if vol is not None:
            if vol > 1_000_000:
                data_quality = max(data_quality, 70)
            elif vol > 100_000:
                data_quality = max(data_quality, 50)
        news = scores.get("news_count_30d")
        if news is not None:
            if news > 5:
                data_quality = max(data_quality, 60)
        cf += data_quality * CONFIDENCE_WEIGHTS["data_quality"]

        pattern = scores.get("pattern_score")
        if pattern is not None:
            cf += pattern * CONFIDENCE_WEIGHTS["pattern_clarity"]

        sim = scores.get("similarity_score")
        if sim is not None:
            cf += sim * CONFIDENCE_WEIGHTS["historical_reliability"]

        return max(0, min(100, cf))

    def _get_recommendation(self, opportunity: float, confidence: float) -> tuple[str, int]:
        if opportunity >= 70 and confidence >= 60:
            return ("strong_buy", 2)
        elif opportunity >= 55 and confidence >= 40:
            return ("buy", 1)
        elif opportunity >= 40 and confidence >= 30:
            return ("hold", 0)
        elif opportunity >= 25 or confidence >= 20:
            return ("sell", -1)
        else:
            return ("strong_sell", -2)

    def _generate_explanation(
        self, scores: dict[str, Any],
        opportunity: float, confidence: float,
        recommendation: str,
    ) -> str:
        parts: list[str] = []
        parts.append(f"RECOMMENDATION: {recommendation.upper()} (Opportunity: {opportunity:.0f}/100, Confidence: {confidence:.0f}/100)")
        factors: list[str] = []

        pattern = scores.get("pattern_score")
        if pattern is not None:
            ptype = scores.get("pattern_type", "chart")
            if pattern >= 60:
                factors.append(f"Strong {ptype} pattern detected ({pattern:.0f}% confidence)")
            elif pattern >= 40:
                factors.append(f"Moderate {ptype} pattern ({pattern:.0f}% confidence)")
            else:
                factors.append(f"Weak {ptype} pattern signal ({pattern:.0f}%)")

        sim = scores.get("similarity_score")
        sim_ret = scores.get("similarity_forward_return")
        if sim is not None and sim >= 50:
            ret_str = f" (+{sim_ret:.1f}% avg)" if sim_ret and sim_ret > 0 else ""
            factors.append(f"Historical similarity supports setup (score: {sim:.0f}{ret_str})")

        tech = scores.get("technical_score")
        if tech is not None:
            if tech >= 60:
                factors.append(f"Technical indicators bullish ({tech:.0f}/100)")
            elif tech <= 40:
                factors.append(f"Technical indicators bearish ({tech:.0f}/100)")

        risk = scores.get("risk_score")
        if risk is not None:
            rating = scores.get("risk_rating", "unknown")
            if risk >= 60:
                factors.append(f"High risk ({rating}, {risk:.0f}/100)")
            elif risk <= 30:
                factors.append(f"Low risk ({rating}, {risk:.0f}/100)")
            else:
                factors.append(f"Moderate risk ({rating}, {risk:.0f}/100)")

        sent = scores.get("sentiment_score")
        if sent is not None:
            if sent > 20:
                factors.append(f"Positive news sentiment ({sent:.0f})")
            elif sent < -20:
                factors.append(f"Negative news sentiment ({sent:.0f})")

        sector = scores.get("sector_rotation")
        if sector:
            factors.append(f"Sector rotation: {sector}")

        breadth = scores.get("breadth_score")
        if breadth is not None:
            if breadth >= 60:
                factors.append("Market breadth bullish")
            elif breadth <= 40:
                factors.append("Market breadth bearish")

        fund = scores.get("fundamental_score")
        if fund is not None:
            if fund >= 60:
                factors.append(f"Strong fundamentals ({fund:.0f}/100)")
            elif fund <= 40:
                factors.append(f"Weak fundamentals ({fund:.0f}/100)")

        if factors:
            parts.append("KEY FACTORS: " + "; ".join(factors))
        else:
            parts.append("KEY FACTORS: Insufficient data for detailed analysis")

        recommendation_guides = {
            "strong_buy": "ACTION: Strong conviction long entry. Consider full position size.",
            "buy": "ACTION: Long entry warranted. Consider half to full position size.",
            "hold": "ACTION: No action recommended. Monitor for signal confirmation or deterioration.",
            "sell": "ACTION: Consider reducing or exiting position. Risk/reward unfavorable.",
            "strong_sell": "ACTION: Exit position immediately. Strong negative signals detected.",
        }
        parts.append(recommendation_guides.get(recommendation, ""))

        return "\n\n".join(parts)

    async def generate_decision(
        self, symbol: str, scores: dict[str, Any],
        as_of_date: date | None = None, store: bool = False,
        decision_type: str = "daily",
    ) -> dict[str, Any]:
        if as_of_date is None:
            as_of_date = date.today()

        result = self.combine_scores(scores)
        result["symbol"] = symbol
        result["as_of_date"] = as_of_date.isoformat()
        result["decision_type"] = decision_type

        if store:
            existing = await self._session.execute(
                select(TradingDecision).where(
                    TradingDecision.symbol == symbol,
                    TradingDecision.as_of_date == as_of_date,
                )
            )
            if existing.scalar_one_or_none() is not None:
                raise ValueError(f"Decision already exists for {symbol} on {as_of_date}")

            rec = await self._repo.create(
                symbol=symbol, as_of_date=as_of_date,
                decision_type=decision_type,
                opportunity_score=result["opportunity_score"],
                confidence_score=result["confidence_score"],
                recommendation=result["recommendation"],
                recommendation_code=result["recommendation_code"],
                explanation=result["explanation"],
                pattern_score=result.get("pattern_score"),
                similarity_score=result.get("similarity_score"),
                technical_score=result.get("technical_score"),
                sector_score=result.get("sector_score"),
                sentiment_score=result.get("sentiment_score"),
                breadth_score=result.get("breadth_score"),
                risk_score=result.get("risk_score"),
                fundamental_score=result.get("fundamental_score"),
                input_scores_json=json.dumps(scores),
            )
            result["id"] = rec.id

        return result

    async def get_decision(
        self, symbol: str, as_of_date: date | None = None,
    ) -> TradingDecision | None:
        stmt = select(TradingDecision).where(TradingDecision.symbol == symbol)
        if as_of_date:
            stmt = stmt.where(TradingDecision.as_of_date == as_of_date)
        stmt = stmt.order_by(TradingDecision.as_of_date.desc()).limit(1)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_decision_history(
        self, symbol: str | None = None,
        recommendation: str | None = None,
        min_opportunity: float | None = None,
        start_date: date | None = None, end_date: date | None = None,
        skip: int = 0, limit: int = 100,
    ) -> tuple[Sequence[TradingDecision], int]:
        stmt = select(TradingDecision)
        if symbol:
            stmt = stmt.where(TradingDecision.symbol == symbol)
        if recommendation:
            stmt = stmt.where(TradingDecision.recommendation == recommendation)
        if min_opportunity is not None:
            stmt = stmt.where(TradingDecision.opportunity_score >= min_opportunity)
        if start_date:
            stmt = stmt.where(TradingDecision.as_of_date >= start_date)
        if end_date:
            stmt = stmt.where(TradingDecision.as_of_date <= end_date)

        count_result = await self._session.execute(stmt)
        total = len(count_result.scalars().all())
        stmt = stmt.order_by(TradingDecision.as_of_date.desc()).offset(skip).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all()), total

    async def delete_decision(self, decision_id: int) -> bool:
        return await self._repo.delete(decision_id)

    async def get_latest_by_recommendation(
        self, recommendation: str, limit: int = 20,
    ) -> Sequence[TradingDecision]:
        result = await self._session.execute(
            select(TradingDecision)
            .where(TradingDecision.recommendation == recommendation)
            .order_by(TradingDecision.as_of_date.desc())
            .limit(limit)
        )
        return result.scalars().all()
