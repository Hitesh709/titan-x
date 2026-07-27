import json
from datetime import date, timedelta
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.models.company import Company
from titan_x.models.fundamental import FundamentalMetric
from titan_x.models.market_breadth import MarketBreadth
from titan_x.models.microstructure import MarketMicrostructure
from titan_x.models.news import NewsArticle
from titan_x.models.news_nlp import NewsNLPAnalysis
from titan_x.models.opportunity_rejection import OpportunityRejection
from titan_x.models.price import DailyPrice
from titan_x.models.regime import MarketRegime
from titan_x.models.risk import RiskMetrics
from titan_x.models.sector import SectorPerformance

REJECTION_THRESHOLD = 40
WEAK_THRESHOLD = 50


class OpportunityRejectionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def evaluate(
        self, symbol: str, direction: str = "bullish",
    ) -> OpportunityRejection:
        symbol = symbol.upper()
        today = date.today()

        scores: dict[str, Any] = {}

        scores["liquidity"] = await self._eval_liquidity(symbol, today)
        scores["risk"] = await self._eval_risk(symbol, today)
        scores["news"] = await self._eval_news(symbol, today)
        scores["financial"] = await self._eval_financial(symbol)
        scores["trend"] = await self._eval_trend(symbol, today)
        scores["market"] = await self._eval_market(today)

        liquidity_score = scores["liquidity"]["score"]
        risk_score = scores["risk"]["score"]
        news_score = scores["news"]["score"]
        financial_score = scores["financial"]["score"]
        trend_score = scores["trend"]["score"]
        market_score = scores["market"]["score"]

        dim_scores = [s for s in [liquidity_score, risk_score, news_score, financial_score, trend_score, market_score] if s is not None]
        composite = round(sum(dim_scores) / len(dim_scores), 1) if dim_scores else None

        rejected_dims = []
        reasons = []
        for dim, data in scores.items():
            if data["score"] is not None and data["score"] < REJECTION_THRESHOLD and data.get("reason"):
                rejected_dims.append(dim)
                reasons.append(data["reason"])
            if data["score"] is None and data.get("reason"):
                rejected_dims.append(dim)
                reasons.append(data["reason"])

        is_rejected = len(rejected_dims) > 0
        rejection_reason = "; ".join(reasons) if reasons else None

        result = OpportunityRejection(
            symbol=symbol,
            trade_date=today,
            direction=direction,
            liquidity_score=liquidity_score,
            risk_score=risk_score,
            news_score=news_score,
            financial_score=financial_score,
            trend_score=trend_score,
            market_score=market_score,
            liquidity_reason=scores["liquidity"].get("reason"),
            risk_reason=scores["risk"].get("reason"),
            news_reason=scores["news"].get("reason"),
            financial_reason=scores["financial"].get("reason"),
            trend_reason=scores["trend"].get("reason"),
            market_reason=scores["market"].get("reason"),
            composite_score=composite,
            is_rejected=is_rejected,
            rejection_reason=rejection_reason,
            metadata_json=json.dumps({"direction": direction, "rejected_dimensions": rejected_dims}),
        )
        self.session.add(result)
        await self.session.flush()
        await self.session.refresh(result)
        return result

    async def get_evaluation(self, evaluation_id: int) -> OpportunityRejection | None:
        r = await self.session.execute(
            select(OpportunityRejection).where(OpportunityRejection.id == evaluation_id)
        )
        return r.scalar_one_or_none()

    async def get_evaluations(
        self, symbol: str, limit: int = 20, offset: int = 0,
    ) -> list[OpportunityRejection]:
        r = await self.session.execute(
            select(OpportunityRejection).where(OpportunityRejection.symbol == symbol.upper())
            .order_by(desc(OpportunityRejection.trade_date))
            .offset(offset).limit(limit)
        )
        return list(r.scalars().all())

    # ---- dimension evaluators ----

    async def _eval_liquidity(
        self, symbol: str, as_of_date: date,
    ) -> dict[str, Any]:
        r = await self.session.execute(
            select(MarketMicrostructure).where(
                MarketMicrostructure.symbol == symbol,
            ).order_by(desc(MarketMicrostructure.as_of_date)).limit(1)
        )
        liq = r.scalar_one_or_none()
        if liq is None or liq.liquidity_score is None:
            return {"score": None, "reason": "No liquidity data available"}

        score = liq.liquidity_score
        if score < 30:
            reason = f"Liquidity too low ({score:.0f}/100) — rating: {liq.liquidity_rating}"
        elif score < WEAK_THRESHOLD:
            reason = f"Weak liquidity ({score:.0f}/100) — rating: {liq.liquidity_rating}"
        else:
            reason = None
        return {"score": score, "reason": reason}

    async def _eval_risk(
        self, symbol: str, as_of_date: date,
    ) -> dict[str, Any]:
        r = await self.session.execute(
            select(RiskMetrics).where(
                RiskMetrics.symbol == symbol,
            ).order_by(desc(RiskMetrics.as_of_date)).limit(1)
        )
        risk = r.scalar_one_or_none()
        if risk is None or risk.composite_risk_score is None:
            return {"score": None, "reason": "No risk data available"}

        raw = risk.composite_risk_score
        score = max(0, 100 - raw)
        if raw > 60:
            reason = f"Risk too high ({raw:.0f}/100) — rating: {risk.risk_rating}"
        elif raw > 40:
            reason = f"Elevated risk ({raw:.0f}/100) — rating: {risk.risk_rating}"
        else:
            reason = None
        return {"score": round(score, 1), "reason": reason}

    async def _eval_news(
        self, symbol: str, as_of_date: date,
    ) -> dict[str, Any]:
        lookback = as_of_date - timedelta(days=7)
        r = await self.session.execute(
            select(func.avg(NewsNLPAnalysis.sentiment_positive), func.count(NewsNLPAnalysis.id))
            .select_from(NewsArticle)
            .join(NewsNLPAnalysis, NewsArticle.id == NewsNLPAnalysis.article_id)
            .where(
                NewsArticle.symbol == symbol,
                NewsArticle.published_at >= lookback,
            )
        )
        row = r.one()
        avg_sentiment = row[0]
        article_count = row[1]

        if article_count == 0:
            return {"score": None, "reason": "No recent news coverage"}
        if avg_sentiment is None:
            return {"score": None, "reason": "No sentiment analysis available"}

        score = round(avg_sentiment * 100, 1)
        if score < 30:
            reason = f"Negative news sentiment ({score:.0f}/100) over {article_count} articles"
        elif score < WEAK_THRESHOLD and article_count < 3:
            reason = f"Limited news coverage ({article_count} articles) with weak sentiment"
        else:
            reason = None
        return {"score": score, "reason": reason}

    async def _eval_financial(
        self, symbol: str,
    ) -> dict[str, Any]:
        r = await self.session.execute(
            select(FundamentalMetric).where(
                FundamentalMetric.symbol == symbol,
                FundamentalMetric.period_type == "FY",
            ).order_by(desc(FundamentalMetric.fiscal_year)).limit(20)
        )
        metrics = list(r.scalars().all())

        if not metrics:
            return {"score": None, "reason": "No financial data available"}

        score_components = []
        reasons = []

        for m in metrics:
            if m.metric_name == "profit_margin" and m.value is not None:
                if m.value < 0:
                    score_components.append(20)
                    reasons.append("Negative profit margin")
                elif m.value < 5:
                    score_components.append(50)
                    reasons.append(f"Low profit margin ({m.value:.1f}%)")
                else:
                    score_components.append(80)

            if m.metric_name == "debt_to_equity" and m.value is not None:
                if m.value > 2.0:
                    score_components.append(20)
                    reasons.append(f"High debt-to-equity ({m.value:.1f})")
                elif m.value > 1.0:
                    score_components.append(50)
                    reasons.append(f"Moderate debt-to-equity ({m.value:.1f})")
                else:
                    score_components.append(80)

            if m.metric_name == "revenue_growth_yoy" and m.value is not None:
                if m.value < 0:
                    score_components.append(20)
                    reasons.append("Declining revenue")
                elif m.value < 5:
                    score_components.append(50)
                    reasons.append(f"Low revenue growth ({m.value:.1f}%)")
                else:
                    score_components.append(80)

        if not score_components:
            return {"score": None, "reason": None}

        score = round(sum(score_components) / len(score_components), 1)
        reason = "; ".join(reasons) if reasons and score < WEAK_THRESHOLD else None
        return {"score": score, "reason": reason}

    async def _eval_trend(
        self, symbol: str, as_of_date: date,
    ) -> dict[str, Any]:
        r = await self.session.execute(
            select(MarketRegime).where(
                MarketRegime.symbol == symbol,
            ).order_by(desc(MarketRegime.as_of_date)).limit(1)
        )
        regime = r.scalar_one_or_none()

        if regime is None:
            return {"score": None, "reason": "No trend data available"}

        reasons = []
        score = 50.0

        if regime.trend_regime == "bull":
            score += 25
        elif regime.trend_regime == "bear":
            score -= 20
            reasons.append(f"Bearish trend regime")

        if regime.momentum_20d is not None:
            if regime.momentum_20d > 0.05:
                score += 10
            elif regime.momentum_20d < -0.05:
                score -= 10
                reasons.append(f"Weak 20d momentum ({regime.momentum_20d:.1%})")

        if regime.trend_score is not None:
            if regime.trend_score < 40:
                reasons.append(f"Low trend score ({regime.trend_score:.0f}/100)")

        if regime.volatility_regime == "high_volatility":
            score -= 10
            reasons.append("High volatility regime")

        score = max(0, min(100, score))
        reason = "; ".join(reasons) if reasons and score < WEAK_THRESHOLD else None
        return {"score": round(score, 1), "reason": reason}

    async def _eval_market(
        self, as_of_date: date,
    ) -> dict[str, Any]:
        r = await self.session.execute(
            select(MarketBreadth).where(
                MarketBreadth.trade_date <= as_of_date,
            ).order_by(desc(MarketBreadth.trade_date)).limit(1)
        )
        breadth = r.scalar_one_or_none()

        reasons = []
        score = 50.0

        if breadth is None:
            return {"score": None, "reason": "No market breadth data available"}
        
            if breadth.advance_decline_ratio is not None:
                if breadth.advance_decline_ratio > 1.5:
                    score += 20
                elif breadth.advance_decline_ratio < 0.7:
                    score -= 15
                    reasons.append(f"Poor market breadth ({breadth.advance_decline_ratio:.2f})")

            if breadth.breadth_oscillator is not None:
                if breadth.breadth_oscillator > 0:
                    score += 10
                else:
                    score -= 10

            if breadth.index_strength_score is not None:
                if breadth.index_strength_score < 40:
                    reasons.append(f"Weak market index score ({breadth.index_strength_score:.0f}/100)")
        else:
            score = 50.0

        score = max(0, min(100, score))
        reason = "; ".join(reasons) if reasons and score < WEAK_THRESHOLD else None
        return {"score": round(score, 1), "reason": reason}
