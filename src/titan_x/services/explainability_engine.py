import json
from collections.abc import Sequence
from datetime import date, timedelta
from typing import Any

import structlog
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.db.repository import BaseRepository
from titan_x.models.chart_pattern import ChartPattern
from titan_x.models.decision import TradingDecision
from titan_x.models.ensemble import EnsemblePrediction
from titan_x.models.explainability import ExplainabilityAnalysis
from titan_x.models.fundamental import FundamentalMetric
from titan_x.models.historical_similarity import SimilarityAnalysis, SimilarityMatch
from titan_x.models.market_breadth import MarketBreadth
from titan_x.models.prediction import Prediction
from titan_x.models.risk import RiskMetrics
from titan_x.models.sector import SectorPerformance
from titan_x.models.technical import TechnicalIndicator

logger = structlog.get_logger(__name__)


class ExplanationFactor:
    def __init__(self, factor: str, score: float, impact: str, source: str, weight: str = "medium"):
        self.factor = factor
        self.score = score
        self.impact = impact
        self.source = source
        self.weight = weight

    def to_dict(self) -> dict[str, Any]:
        return {
            "factor": self.factor,
            "score": round(self.score, 1),
            "impact": self.impact,
            "source": self.source,
            "weight": self.weight,
        }


class ExplainabilityEngine:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = BaseRepository(session, ExplainabilityAnalysis)

    async def analyze(
        self, symbol: str, as_of_date: date | None = None, store: bool = True,
    ) -> dict[str, Any]:
        if as_of_date is None:
            as_of_date = date.today()

        company = await self._get_company(symbol)
        if company is None:
            return {"symbol": symbol, "error": f"Company {symbol} not found"}

        prediction = await self._get_latest_prediction(symbol)
        decision = await self._get_latest_decision(symbol)
        ensemble = await self._get_latest_ensemble(symbol)
        technical = await self._get_technical_data(symbol, as_of_date)
        patterns = await self._get_active_patterns(symbol)
        risk = await self._get_risk_metrics(symbol, as_of_date)
        fundamentals = await self._get_fundamentals(symbol)
        similarities = await self._get_similarities(symbol)
        sector_data = await self._get_sector_data(company.sector, as_of_date)
        breadth = await self._get_market_breadth(as_of_date)
        latest_price = await self._get_latest_price(symbol)

        why_buy = self._build_why_buy(
            prediction, decision, ensemble, technical, patterns,
            risk, fundamentals, similarities, sector_data, breadth, latest_price,
        )
        why_not_buy = self._build_why_not_buy(
            prediction, decision, ensemble, technical, patterns,
            risk, fundamentals, similarities, sector_data, breadth,
        )
        strengths = self._build_strengths(
            technical, fundamentals, patterns, sector_data, breadth, risk,
        )
        weaknesses = self._build_weaknesses(
            technical, fundamentals, patterns, sector_data, breadth, risk,
        )
        risk_factors = self._build_risk_factors(risk, technical)
        historical_evidence = self._build_historical_evidence(
            similarities, prediction, patterns, sector_data,
        )

        overall_score = self._compute_overall_score(why_buy, why_not_buy, strengths, weaknesses, risk_factors)
        overall_signal = self._score_to_signal(overall_score)
        overall_confidence = self._compute_overall_confidence(
            why_buy, why_not_buy, strengths, weaknesses, risk_factors,
        )

        why_buy.sort(key=lambda f: f.score, reverse=True)
        why_not_buy.sort(key=lambda f: f.score, reverse=True)
        strengths.sort(key=lambda f: f.score, reverse=True)
        weaknesses.sort(key=lambda f: f.score, reverse=True)
        risk_factors.sort(key=lambda f: f.score, reverse=True)
        historical_evidence.sort(key=lambda f: f.score, reverse=True)

        result: dict[str, Any] = {
            "symbol": symbol,
            "as_of_date": as_of_date,
            "why_buy": [f.to_dict() for f in why_buy],
            "why_not_buy": [f.to_dict() for f in why_not_buy],
            "strengths": [f.to_dict() for f in strengths],
            "weaknesses": [f.to_dict() for f in weaknesses],
            "risk_factors": [f.to_dict() for f in risk_factors],
            "historical_evidence": [f.to_dict() for f in historical_evidence],
            "overall_score": round(overall_score, 1),
            "overall_signal": overall_signal,
            "overall_confidence": round(overall_confidence, 1),
            "metadata_json": "{}",
        }

        if store:
            existing = await self._get_analysis(symbol, as_of_date)
            if existing:
                raise ValueError(f"Explainability analysis for {symbol} on {as_of_date} already exists")
            try:
                stored = await self._repo.create(
                    symbol=symbol,
                    as_of_date=as_of_date,
                    why_buy_json=json.dumps(result["why_buy"]),
                    why_not_buy_json=json.dumps(result["why_not_buy"]),
                    strengths_json=json.dumps(result["strengths"]),
                    weaknesses_json=json.dumps(result["weaknesses"]),
                    risk_factors_json=json.dumps(result["risk_factors"]),
                    historical_evidence_json=json.dumps(result["historical_evidence"]),
                    overall_signal=overall_signal,
                    overall_score=result["overall_score"],
                    overall_confidence=result["overall_confidence"],
                    metadata_json="{}",
                )
                result["id"] = stored.id
            except Exception:
                await self._session.rollback()
                raise

        return result

    def _build_why_buy(
        self, prediction: Prediction | None, decision: TradingDecision | None,
        ensemble: EnsemblePrediction | None, technical: dict[str, Any],
        patterns: Sequence[ChartPattern], risk: RiskMetrics | None,
        fundamentals: Sequence[FundamentalMetric],
        similarities: Sequence[SimilarityAnalysis],
        sector_data: dict[str, Any] | None, breadth: dict[str, Any] | None,
        latest_price: Any | None,
    ) -> list[ExplanationFactor]:
        factors: list[ExplanationFactor] = []

        if prediction is not None and prediction.overall_signal in ("strong_buy", "buy"):
            factors.append(ExplanationFactor(
                factor=f"Horizon prediction signals {prediction.overall_signal.replace('_', ' ')} with {prediction.overall_confidence:.0f}% confidence across 5 time horizons",
                score=prediction.overall_confidence or 50, impact="positive", source="prediction", weight="high",
            ))

        if decision is not None and decision.recommendation in ("strong_buy", "buy"):
            factors.append(ExplanationFactor(
                factor=f"Decision engine recommends {decision.recommendation.replace('_', ' ')} (opportunity: {decision.opportunity_score:.0f}, confidence: {decision.confidence_score:.0f})",
                score=decision.opportunity_score or 50, impact="positive", source="decision", weight="high",
            ))

        if ensemble is not None and ensemble.ensemble_signal in ("strong_buy", "buy"):
            factors.append(ExplanationFactor(
                factor=f"Ensemble AI votes {ensemble.ensemble_signal.replace('_', ' ')} (score: {ensemble.ensemble_score:.0f}, agreement: {ensemble.agreement_level})",
                score=ensemble.ensemble_score or 50, impact="positive", source="ensemble", weight="high",
            ))

        tech_bullish = self._get_technical_bullish(technical)
        factors.extend(tech_bullish)

        pattern_bullish = self._get_pattern_bullish(patterns)
        factors.extend(pattern_bullish)

        fund_bullish = self._get_fundamental_bullish(fundamentals)
        factors.extend(fund_bullish)

        if similarities:
            sa = similarities[0]
            if sa.avg_return_5d is not None and sa.avg_return_5d > 0:
                factors.append(ExplanationFactor(
                    factor=f"Historical similar periods show {sa.avg_return_5d:+.1f}% average forward return over 5 days (similarity: {sa.avg_similarity:.0f}%)",
                    score=min(100, sa.avg_similarity or 50), impact="positive", source="similarity", weight="medium",
                ))

        if sector_data:
            ms = sector_data.get("momentum_score", 0)
            if ms is not None and ms > 0:
                factors.append(ExplanationFactor(
                    factor=f"Sector momentum positive at {ms:+.1f} points",
                    score=min(100, max(0, ms * 5 + 50)), impact="positive", source="sector", weight="medium",
                ))

        if breadth:
            iss = breadth.get("index_strength_score", 50)
            if iss is not None and iss > 55:
                factors.append(ExplanationFactor(
                    factor=f"Market breadth supportive with index strength score of {iss:.0f}",
                    score=iss, impact="positive", source="breadth", weight="low",
                ))

        if risk is not None and risk.composite_risk_score is not None and risk.composite_risk_score < 35:
            factors.append(ExplanationFactor(
                factor=f"Overall risk score low at {risk.composite_risk_score:.0f}, suggesting favorable risk environment",
                score=100 - risk.composite_risk_score, impact="positive", source="risk", weight="medium",
            ))

        if latest_price is not None:
            price = getattr(latest_price, "close", None) or getattr(latest_price, "value", 0)
            factors.append(ExplanationFactor(
                factor=f"Current price at {price:.2f} provides reference point for entry analysis",
                score=50, impact="positive", source="price", weight="low",
            ))

        return factors

    def _build_why_not_buy(
        self, prediction: Prediction | None, decision: TradingDecision | None,
        ensemble: EnsemblePrediction | None, technical: dict[str, Any],
        patterns: Sequence[ChartPattern], risk: RiskMetrics | None,
        fundamentals: Sequence[FundamentalMetric],
        similarities: Sequence[SimilarityAnalysis],
        sector_data: dict[str, Any] | None, breadth: dict[str, Any] | None,
    ) -> list[ExplanationFactor]:
        factors: list[ExplanationFactor] = []

        if prediction is not None and prediction.overall_signal in ("strong_sell", "sell"):
            factors.append(ExplanationFactor(
                factor=f"Horizon prediction signals {prediction.overall_signal.replace('_', ' ')}",
                score=prediction.overall_confidence or 50, impact="negative", source="prediction", weight="high",
            ))

        if decision is not None and decision.recommendation in ("strong_sell", "sell"):
            factors.append(ExplanationFactor(
                factor=f"Decision engine recommends {decision.recommendation.replace('_', ' ')} (opportunity: {decision.opportunity_score:.0f})",
                score=100 - (decision.opportunity_score or 50), impact="negative", source="decision", weight="high",
            ))

        if ensemble is not None and ensemble.ensemble_signal in ("strong_sell", "sell"):
            factors.append(ExplanationFactor(
                factor=f"Ensemble AI votes {ensemble.ensemble_signal.replace('_', ' ')} (score: {ensemble.ensemble_score:.0f})",
                score=100 - (ensemble.ensemble_score or 50), impact="negative", source="ensemble", weight="high",
            ))

        tech_bearish = self._get_technical_bearish(technical)
        factors.extend(tech_bearish)

        pattern_bearish = self._get_pattern_bearish(patterns)
        factors.extend(pattern_bearish)

        fund_bearish = self._get_fundamental_bearish(fundamentals)
        factors.extend(fund_bearish)

        if similarities:
            sa = similarities[0]
            if sa.avg_return_5d is not None and sa.avg_return_5d < 0:
                factors.append(ExplanationFactor(
                    factor=f"Historical similar periods show {sa.avg_return_5d:+.1f}% average forward return over 5 days",
                    score=min(100, abs(sa.avg_return_5d) * 10), impact="negative", source="similarity", weight="medium",
                ))

        if sector_data:
            ms = sector_data.get("momentum_score", 0)
            if ms is not None and ms < 0:
                factors.append(ExplanationFactor(
                    factor=f"Sector momentum negative at {ms:+.1f} points",
                    score=min(100, max(0, abs(ms) * 5 + 50)), impact="negative", source="sector", weight="medium",
                ))

        if breadth:
            iss = breadth.get("index_strength_score", 50)
            if iss is not None and iss < 45:
                factors.append(ExplanationFactor(
                    factor=f"Weak market breadth with index strength score of {iss:.0f}",
                    score=100 - iss, impact="negative", source="breadth", weight="low",
                ))

        if risk is not None and risk.composite_risk_score is not None and risk.composite_risk_score > 65:
            factors.append(ExplanationFactor(
                factor=f"Elevated risk score of {risk.composite_risk_score:.0f} suggests caution",
                score=risk.composite_risk_score, impact="negative", source="risk", weight="medium",
            ))

        return factors

    def _build_strengths(
        self, technical: dict[str, Any], fundamentals: Sequence[FundamentalMetric],
        patterns: Sequence[ChartPattern], sector_data: dict[str, Any] | None,
        breadth: dict[str, Any] | None, risk: RiskMetrics | None,
    ) -> list[ExplanationFactor]:
        factors: list[ExplanationFactor] = []

        for m in fundamentals:
            if m.metric_name == "QUALITY_SCORE" and m.value is not None and m.value >= 6:
                factors.append(ExplanationFactor(
                    factor=f"High quality score of {m.value:.1f}/10 indicates strong business fundamentals",
                    score=m.value * 10, impact="positive", source="fundamental", weight="high",
                ))
            elif m.metric_name == "ROE" and m.value is not None and m.value > 15:
                factors.append(ExplanationFactor(
                    factor=f"Strong ROE of {m.value:.1f}% demonstrates efficient capital use",
                    score=min(100, m.value * 3), impact="positive", source="fundamental", weight="medium",
                ))
            elif m.metric_name == "PE_RATIO" and m.value is not None and 0 < m.value < 15:
                factors.append(ExplanationFactor(
                    factor=f"Attractive PE ratio of {m.value:.1f} suggests potential value",
                    score=max(0, 100 - m.value * 5), impact="positive", source="fundamental", weight="medium",
                ))
            elif m.metric_name == "DEBT_EQUITY" and m.value is not None and m.value < 0.5:
                factors.append(ExplanationFactor(
                    factor=f"Low debt-to-equity of {m.value:.2f} indicates conservative leverage",
                    score=100 - min(100, m.value * 100), impact="positive", source="fundamental", weight="medium",
                ))

        rsi = technical.get("rsi")
        if rsi is not None and rsi.value is not None and 40 <= rsi.value <= 60:
            factors.append(ExplanationFactor(
                factor=f"RSI at {rsi.value:.1f} indicates neutral, non-extreme positioning",
                score=70, impact="positive", source="technical", weight="low",
            ))

        ema_12 = technical.get("ema_12")
        sma_50 = technical.get("sma_50")
        if ema_12 is not None and sma_50 is not None and ema_12.value is not None and sma_50.value is not None:
            if ema_12.value > sma_50.value:
                factors.append(ExplanationFactor(
                    factor=f"EMA-12 ({ema_12.value:.2f}) above SMA-50 ({sma_50.value:.2f}), bullish alignment",
                    score=70, impact="positive", source="technical", weight="medium",
                ))

        for p in patterns:
            if p.is_active and p.direction == "bullish" and p.confidence_score is not None and p.confidence_score >= 60:
                factors.append(ExplanationFactor(
                    factor=f"{p.pattern_type.replace('_', ' ').title()} pattern detected with {p.confidence_score:.0f}% confidence, targeting {getattr(p, 'target_price', 0):.2f}" if hasattr(p, 'target_price') and p.target_price else f"{p.pattern_type.replace('_', ' ').title()} pattern detected with {p.confidence_score:.0f}% confidence",
                    score=p.confidence_score, impact="positive", source="pattern", weight="medium",
                ))

        if sector_data:
            rs = sector_data.get("relative_strength", 50)
            if rs is not None and rs > 55:
                factors.append(ExplanationFactor(
                    factor=f"Sector relative strength at {rs:.1f} indicates outperformance vs peers",
                    score=min(100, rs), impact="positive", source="sector", weight="medium",
                ))

        if breadth:
            adr = breadth.get("adv_decl_ratio", 1.0)
            if adr is not None and adr > 1.3:
                factors.append(ExplanationFactor(
                    factor=f"Positive advance-decline ratio of {adr:.2f} shows broad market participation",
                    score=min(100, adr * 50), impact="positive", source="breadth", weight="low",
                ))

        if risk is not None and risk.liquidity_score is not None and risk.liquidity_score >= 70:
            factors.append(ExplanationFactor(
                factor=f"High liquidity score of {risk.liquidity_score:.0f} ensures efficient trade execution",
                score=risk.liquidity_score, impact="positive", source="risk", weight="low",
            ))

        return factors

    def _build_weaknesses(
        self, technical: dict[str, Any], fundamentals: Sequence[FundamentalMetric],
        patterns: Sequence[ChartPattern], sector_data: dict[str, Any] | None,
        breadth: dict[str, Any] | None, risk: RiskMetrics | None,
    ) -> list[ExplanationFactor]:
        factors: list[ExplanationFactor] = []

        for m in fundamentals:
            if m.metric_name == "QUALITY_SCORE" and m.value is not None and m.value < 4:
                factors.append(ExplanationFactor(
                    factor=f"Low quality score of {m.value:.1f}/10 raises fundamental concerns",
                    score=100 - m.value * 10, impact="negative", source="fundamental", weight="high",
                ))
            elif m.metric_name == "PE_RATIO" and m.value is not None and m.value > 30:
                factors.append(ExplanationFactor(
                    factor=f"Elevated PE ratio of {m.value:.1f} suggests premium valuation",
                    score=min(100, m.value * 2), impact="negative", source="fundamental", weight="medium",
                ))
            elif m.metric_name == "DEBT_EQUITY" and m.value is not None and m.value > 2:
                factors.append(ExplanationFactor(
                    factor=f"High debt-to-equity of {m.value:.2f} indicates significant leverage",
                    score=min(100, m.value * 20), impact="negative", source="fundamental", weight="medium",
                ))
            elif m.metric_name == "ROE" and m.value is not None and m.value < 5:
                factors.append(ExplanationFactor(
                    factor=f"Low ROE of {m.value:.1f}% suggests weak profitability generation",
                    score=100 - m.value * 10, impact="negative", source="fundamental", weight="medium",
                ))

        rsi = technical.get("rsi")
        if rsi is not None and rsi.value is not None and rsi.value > 70:
            factors.append(ExplanationFactor(
                factor=f"RSI at {rsi.value:.1f} indicates overbought conditions",
                score=min(100, rsi.value), impact="negative", source="technical", weight="medium",
            ))
        elif rsi is not None and rsi.value is not None and rsi.value < 30:
            factors.append(ExplanationFactor(
                factor=f"RSI at {rsi.value:.1f} indicates oversold conditions (potential further downside)",
                score=100 - rsi.value, impact="negative", source="technical", weight="medium",
            ))

        ema_12 = technical.get("ema_12")
        sma_50 = technical.get("sma_50")
        if ema_12 is not None and sma_50 is not None and ema_12.value is not None and sma_50.value is not None:
            if ema_12.value < sma_50.value:
                factors.append(ExplanationFactor(
                    factor=f"EMA-12 ({ema_12.value:.2f}) below SMA-50 ({sma_50.value:.2f}), bearish alignment",
                    score=70, impact="negative", source="technical", weight="medium",
                ))

        for p in patterns:
            if p.is_active and p.direction == "bearish" and p.confidence_score is not None and p.confidence_score >= 60:
                factors.append(ExplanationFactor(
                    factor=f"{p.pattern_type.replace('_', ' ').title()} pattern with {p.confidence_score:.0f}% confidence suggests downside risk",
                    score=p.confidence_score, impact="negative", source="pattern", weight="medium",
                ))

        if sector_data:
            rs = sector_data.get("relative_strength", 50)
            if rs is not None and rs < 45:
                factors.append(ExplanationFactor(
                    factor=f"Sector relative strength at {rs:.1f} indicates underperformance vs peers",
                    score=100 - rs, impact="negative", source="sector", weight="medium",
                ))

        if breadth:
            adr = breadth.get("adv_decl_ratio", 1.0)
            if adr is not None and adr < 0.7:
                factors.append(ExplanationFactor(
                    factor=f"Low advance-decline ratio of {adr:.2f} signals weak market participation",
                    score=100 - min(100, adr * 100), impact="negative", source="breadth", weight="low",
                ))

        if risk is not None and risk.liquidity_score is not None and risk.liquidity_score < 40:
            factors.append(ExplanationFactor(
                factor=f"Low liquidity score of {risk.liquidity_score:.0f} may impact trade execution",
                score=100 - risk.liquidity_score, impact="negative", source="risk", weight="low",
            ))

        return factors

    def _build_risk_factors(
        self, risk: RiskMetrics | None, technical: dict[str, Any],
    ) -> list[ExplanationFactor]:
        factors: list[ExplanationFactor] = []

        if risk is None:
            factors.append(ExplanationFactor(
                factor="Limited risk data available - proceed with standard position sizing",
                score=30, impact="negative", source="risk", weight="medium",
            ))
            return factors

        if risk.risk_rating:
            rating_map = {"very_low": 10, "low": 25, "medium": 50, "high": 75, "extreme": 95}
            score = rating_map.get(risk.risk_rating, 50)
            factors.append(ExplanationFactor(
                factor=f"Overall risk rating: {risk.risk_rating.replace('_', ' ').title()}",
                score=score, impact="negative", source="risk", weight="high",
            ))

        if risk.volatility_252d is not None:
            score = min(100, risk.volatility_252d * 2)
            label = "moderate" if risk.volatility_252d < 25 else "elevated" if risk.volatility_252d < 40 else "high"
            factors.append(ExplanationFactor(
                factor=f"Annualized volatility at {risk.volatility_252d:.1f}% ({label})",
                score=score, impact="negative", source="risk", weight="high",
            ))

        if risk.volatility_60d is not None:
            score = min(100, risk.volatility_60d * 2)
            vol_diff = abs((risk.volatility_60d or 0) - (risk.volatility_252d or risk.volatility_60d or 0))
            if vol_diff > 10:
                factors.append(ExplanationFactor(
                    factor=f"Volatility regime shift detected: 60d vol ({risk.volatility_60d:.1f}%) vs 252d vol ({risk.volatility_252d:.1f}%)",
                    score=min(100, vol_diff * 3), impact="negative", source="risk", weight="medium",
                ))

        if risk.max_drawdown_1y is not None:
            score = min(100, risk.max_drawdown_1y * 2)
            factors.append(ExplanationFactor(
                factor=f"Maximum historical drawdown over 1 year: {risk.max_drawdown_1y:.1f}%",
                score=score, impact="negative", source="risk", weight="high",
            ))

        if risk.max_drawdown_3m is not None:
            recent_dd = risk.max_drawdown_3m
            if recent_dd > 15:
                factors.append(ExplanationFactor(
                    factor=f"Recent 3-month max drawdown of {recent_dd:.1f}% indicates near-term stress",
                    score=min(100, recent_dd * 3), impact="negative", source="risk", weight="medium",
                ))

        if risk.event_risk_score is not None:
            score = risk.event_risk_score
            label = "low" if score < 20 else "moderate" if score < 40 else "elevated"
            factors.append(ExplanationFactor(
                factor=f"News-based event risk is {label} (score: {score:.0f})",
                score=score, impact="negative", source="risk", weight="medium",
            ))

        if risk.gap_frequency_20d is not None:
            score = min(100, risk.gap_frequency_20d * 5)
            if risk.gap_frequency_20d > 0.15:
                factors.append(ExplanationFactor(
                    factor=f"Frequent gap openings: {risk.gap_frequency_20d*100:.0f}% of days in last 20",
                    score=score, impact="negative", source="risk", weight="low",
                ))

        if risk.liquidity_score is not None and risk.liquidity_score < 50:
            factors.append(ExplanationFactor(
                factor=f"Below-average liquidity (score: {risk.liquidity_score:.0f}) may increase slippage",
                score=100 - risk.liquidity_score, impact="negative", source="risk", weight="medium",
            ))

        return factors

    def _build_historical_evidence(
        self, similarities: Sequence[SimilarityAnalysis],
        prediction: Prediction | None, patterns: Sequence[ChartPattern],
        sector_data: dict[str, Any] | None,
    ) -> list[ExplanationFactor]:
        factors: list[ExplanationFactor] = []

        if similarities:
            sa = similarities[0]
            factors.append(ExplanationFactor(
                factor=f"Similarity analysis found matches with {sa.avg_similarity:.0f}% average similarity across {sa.max_matches} candidates",
                score=sa.avg_similarity or 50, impact="positive", source="similarity", weight="high",
            ))

            horizons = [("5d", sa.avg_return_5d), ("10d", sa.avg_return_10d),
                        ("20d", sa.avg_return_20d), ("60d", sa.avg_return_60d)]
            for label, ret in horizons:
                if ret is not None:
                    factors.append(ExplanationFactor(
                        factor=f"Historical forward return over {label}: {ret:+.2f}%",
                        score=min(100, max(0, 50 + ret * 5)), impact="positive" if ret > 0 else "negative",
                        source="similarity", weight="medium",
                    ))

            if sa.optimal_holding_period is not None:
                factors.append(ExplanationFactor(
                    factor=f"Optimal holding period identified as {sa.optimal_holding_period} days based on historical patterns",
                    score=70, impact="positive", source="similarity", weight="low",
                ))

        if prediction is not None:
            for h in [5, 10, 15, 20, 30]:
                prob = getattr(prediction, f"probability_{h}d", None)
                ret = getattr(prediction, f"expected_return_{h}d", None)
                if prob is not None and ret is not None:
                    factors.append(ExplanationFactor(
                        factor=f"{h}-day prediction: {prob:.0f}% probability of {ret:+.2f}% return",
                        score=prob, impact="positive" if ret > 0 else "negative",
                        source="prediction", weight="medium",
                    ))

        active_patterns = [p for p in patterns if p.is_active and p.confidence_score is not None]
        if active_patterns:
            avg_conf = sum(p.confidence_score for p in active_patterns) / len(active_patterns)
            bullish_count = sum(1 for p in active_patterns if p.direction == "bullish")
            bearish_count = sum(1 for p in active_patterns if p.direction == "bearish")
            factors.append(ExplanationFactor(
                factor=f"{len(active_patterns)} active chart patterns detected ({bullish_count} bullish, {bearish_count} bearish), avg confidence: {avg_conf:.0f}%",
                score=avg_conf, impact="positive" if bullish_count > bearish_count else "negative",
                source="pattern", weight="medium",
            ))

        if sector_data:
            ms = sector_data.get("momentum_score", 0)
            rs = sector_data.get("relative_strength", 50)
            factors.append(ExplanationFactor(
                factor=f"Sector momentum: {ms:+.1f}, relative strength: {rs:.1f}",
                score=min(100, max(0, (ms * 5 + 50 + rs) / 2)), impact="positive" if ms > 0 else "negative",
                source="sector", weight="low",
            ))

        return factors

    def _get_technical_bullish(self, technical: dict[str, Any]) -> list[ExplanationFactor]:
        factors: list[ExplanationFactor] = []

        rsi = technical.get("rsi")
        if rsi is not None and rsi.value is not None and 30 <= rsi.value <= 45:
            factors.append(ExplanationFactor(
                factor=f"RSI at {rsi.value:.1f} recovering from oversold territory",
                score=65, impact="positive", source="technical", weight="medium",
            ))

        sma_20 = technical.get("sma_20")
        sma_50 = technical.get("sma_50")
        if sma_20 is not None and sma_50 is not None and sma_20.value is not None and sma_50.value is not None:
            if sma_20.value > sma_50.value:
                factors.append(ExplanationFactor(
                    factor=f"SMA-20 ({sma_20.value:.2f}) above SMA-50 ({sma_50.value:.2f}) — bullish crossover",
                    score=75, impact="positive", source="technical", weight="medium",
                ))

        macd = technical.get("macd")
        if macd is not None and macd.value is not None and macd.value_secondary is not None:
            if macd.value > macd.value_secondary:
                factors.append(ExplanationFactor(
                    factor=f"MACD line ({macd.value:.2f}) above signal ({macd.value_secondary:.2f}) — bullish momentum",
                    score=70, impact="positive", source="technical", weight="medium",
                ))

        return factors

    def _get_technical_bearish(self, technical: dict[str, Any]) -> list[ExplanationFactor]:
        factors: list[ExplanationFactor] = []

        rsi = technical.get("rsi")
        if rsi is not None and rsi.value is not None and rsi.value > 70:
            factors.append(ExplanationFactor(
                factor=f"RSI at {rsi.value:.1f} in overbought territory",
                score=min(100, rsi.value), impact="negative", source="technical", weight="medium",
            ))

        sma_20 = technical.get("sma_20")
        sma_50 = technical.get("sma_50")
        if sma_20 is not None and sma_50 is not None and sma_20.value is not None and sma_50.value is not None:
            if sma_20.value < sma_50.value:
                factors.append(ExplanationFactor(
                    factor=f"SMA-20 ({sma_20.value:.2f}) below SMA-50 ({sma_50.value:.2f}) — bearish crossover",
                    score=75, impact="negative", source="technical", weight="medium",
                ))

        macd = technical.get("macd")
        if macd is not None and macd.value is not None and macd.value_secondary is not None:
            if macd.value < macd.value_secondary:
                factors.append(ExplanationFactor(
                    factor=f"MACD ({macd.value:.2f}) below signal ({macd.value_secondary:.2f}) — bearish momentum",
                    score=70, impact="negative", source="technical", weight="medium",
                ))

        return factors

    def _get_pattern_bullish(self, patterns: Sequence[ChartPattern]) -> list[ExplanationFactor]:
        factors: list[ExplanationFactor] = []
        for p in patterns:
            if p.is_active and p.direction == "bullish" and p.confidence_score is not None:
                target = getattr(p, "target_price", None)
                target_str = f", targeting {target:.2f}" if target else ""
                factors.append(ExplanationFactor(
                    factor=f"Bullish {p.pattern_type.replace('_', ' ')} pattern with {p.confidence_score:.0f}% confidence{target_str}",
                    score=p.confidence_score, impact="positive", source="pattern", weight="medium",
                ))
        return factors

    def _get_pattern_bearish(self, patterns: Sequence[ChartPattern]) -> list[ExplanationFactor]:
        factors: list[ExplanationFactor] = []
        for p in patterns:
            if p.is_active and p.direction == "bearish" and p.confidence_score is not None:
                factors.append(ExplanationFactor(
                    factor=f"Bearish {p.pattern_type.replace('_', ' ')} pattern with {p.confidence_score:.0f}% confidence",
                    score=p.confidence_score, impact="negative", source="pattern", weight="medium",
                ))
        return factors

    def _get_fundamental_bullish(self, fundamentals: Sequence[FundamentalMetric]) -> list[ExplanationFactor]:
        factors: list[ExplanationFactor] = []
        for m in fundamentals:
            if m.metric_name == "PE_RATIO" and m.value is not None and 0 < m.value < 15:
                factors.append(ExplanationFactor(
                    factor=f"Value opportunity: PE ratio of {m.value:.1f}x below typical market range",
                    score=80, impact="positive", source="fundamental", weight="medium",
                ))
            elif m.metric_name == "REVENUE_GROWTH" and m.value is not None and m.value > 10:
                factors.append(ExplanationFactor(
                    factor=f"Strong revenue growth of {m.value:.1f}% year-over-year",
                    score=min(100, m.value * 3), impact="positive", source="fundamental", weight="medium",
                ))
            elif m.metric_name == "EPS_GROWTH" and m.value is not None and m.value > 10:
                factors.append(ExplanationFactor(
                    factor=f"Healthy earnings growth of {m.value:.1f}% year-over-year",
                    score=min(100, m.value * 3), impact="positive", source="fundamental", weight="medium",
                ))
        return factors

    def _get_fundamental_bearish(self, fundamentals: Sequence[FundamentalMetric]) -> list[ExplanationFactor]:
        factors: list[ExplanationFactor] = []
        for m in fundamentals:
            if m.metric_name == "PE_RATIO" and m.value is not None and m.value > 30:
                factors.append(ExplanationFactor(
                    factor=f"Expensive valuation: PE ratio of {m.value:.1f}x",
                    score=min(100, m.value * 2), impact="negative", source="fundamental", weight="medium",
                ))
            elif m.metric_name == "REVENUE_GROWTH" and m.value is not None and m.value < -5:
                factors.append(ExplanationFactor(
                    factor=f"Revenue declining {m.value:.1f}% year-over-year",
                    score=min(100, abs(m.value) * 5), impact="negative", source="fundamental", weight="medium",
                ))
            elif m.metric_name == "EPS_GROWTH" and m.value is not None and m.value < -5:
                factors.append(ExplanationFactor(
                    factor=f"Earnings declining {m.value:.1f}% year-over-year",
                    score=min(100, abs(m.value) * 5), impact="negative", source="fundamental", weight="medium",
                ))
        return factors

    def _compute_overall_score(
        self, why_buy: list[ExplanationFactor], why_not_buy: list[ExplanationFactor],
        strengths: list[ExplanationFactor], weaknesses: list[ExplanationFactor],
        risk_factors: list[ExplanationFactor],
    ) -> float:
        pos_score = sum(f.score * self._weight_multiplier(f.weight) for f in why_buy if f.impact == "positive")
        pos_score += sum(f.score * self._weight_multiplier(f.weight) for f in strengths if f.impact == "positive")
        neg_score = sum(f.score * self._weight_multiplier(f.weight) for f in why_not_buy if f.impact == "negative")
        neg_score += sum(f.score * self._weight_multiplier(f.weight) for f in weaknesses if f.impact == "negative")
        risk_score = sum(f.score * self._weight_multiplier(f.weight) for f in risk_factors if f.impact == "negative")

        pos_weight = sum(self._weight_multiplier(f.weight) for f in why_buy if f.impact == "positive")
        pos_weight += sum(self._weight_multiplier(f.weight) for f in strengths if f.impact == "positive")
        neg_weight = sum(self._weight_multiplier(f.weight) for f in why_not_buy if f.impact == "negative")
        neg_weight += sum(self._weight_multiplier(f.weight) for f in weaknesses if f.impact == "negative")
        risk_weight = sum(self._weight_multiplier(f.weight) for f in risk_factors if f.impact == "negative")

        pos_avg = pos_score / pos_weight if pos_weight > 0 else 50
        neg_avg = neg_score / neg_weight if neg_weight > 0 else 50
        risk_avg = risk_score / risk_weight if risk_weight > 0 else 50

        raw = pos_avg * 0.5 - neg_avg * 0.3 - risk_avg * 0.2 + 50
        return max(0, min(100, raw))

    def _weight_multiplier(self, weight: str) -> float:
        return {"high": 3.0, "medium": 1.5, "low": 1.0}.get(weight, 1.0)

    def _score_to_signal(self, score: float) -> str:
        if score >= 70:
            return "strong_buy"
        elif score >= 55:
            return "buy"
        elif score >= 40:
            return "hold"
        elif score >= 25:
            return "sell"
        return "strong_sell"

    def _compute_overall_confidence(
        self, why_buy: list[ExplanationFactor], why_not_buy: list[ExplanationFactor],
        strengths: list[ExplanationFactor], weaknesses: list[ExplanationFactor],
        risk_factors: list[ExplanationFactor],
    ) -> float:
        total_factors = len(why_buy) + len(why_not_buy) + len(strengths) + len(weaknesses) + len(risk_factors)
        if total_factors == 0:
            return 20.0

        high_wt = sum(1 for f in why_buy + why_not_buy + strengths + weaknesses + risk_factors if f.weight == "high")
        base = min(95, 30 + total_factors * 5 + high_wt * 3)
        return max(10, base)

    async def get_analysis(
        self, symbol: str, as_of_date: date | None = None,
    ) -> ExplainabilityAnalysis | None:
        query = select(ExplainabilityAnalysis).where(ExplainabilityAnalysis.symbol == symbol)
        if as_of_date:
            query = query.where(ExplainabilityAnalysis.as_of_date == as_of_date)
        query = query.order_by(desc(ExplainabilityAnalysis.as_of_date)).limit(1)
        result = await self._session.execute(query)
        return result.scalar_one_or_none()

    async def _get_analysis(self, symbol: str, as_of_date: date) -> ExplainabilityAnalysis | None:
        result = await self._session.execute(
            select(ExplainabilityAnalysis).where(
                ExplainabilityAnalysis.symbol == symbol,
                ExplainabilityAnalysis.as_of_date == as_of_date,
            )
        )
        return result.scalar_one_or_none()

    async def get_analysis_history(
        self, symbol: str | None = None, signal: str | None = None,
        min_confidence: float | None = None,
        start_date: date | None = None, end_date: date | None = None,
        skip: int = 0, limit: int = 100,
    ) -> tuple[Sequence[ExplainabilityAnalysis], int]:
        query = select(ExplainabilityAnalysis)
        count_query = select(func.count()).select_from(ExplainabilityAnalysis)

        if symbol:
            query = query.where(ExplainabilityAnalysis.symbol == symbol)
            count_query = count_query.where(ExplainabilityAnalysis.symbol == symbol)
        if signal:
            query = query.where(ExplainabilityAnalysis.overall_signal == signal)
            count_query = count_query.where(ExplainabilityAnalysis.overall_signal == signal)
        if min_confidence is not None:
            query = query.where(ExplainabilityAnalysis.overall_confidence >= min_confidence)
            count_query = count_query.where(ExplainabilityAnalysis.overall_confidence >= min_confidence)
        if start_date:
            query = query.where(ExplainabilityAnalysis.as_of_date >= start_date)
            count_query = count_query.where(ExplainabilityAnalysis.as_of_date >= start_date)
        if end_date:
            query = query.where(ExplainabilityAnalysis.as_of_date <= end_date)
            count_query = count_query.where(ExplainabilityAnalysis.as_of_date <= end_date)

        total_result = await self._session.execute(count_query)
        total = total_result.scalar() or 0

        query = query.order_by(desc(ExplainabilityAnalysis.as_of_date)).offset(skip).limit(limit)
        result = await self._session.execute(query)
        return result.scalars().all(), total

    async def delete_analysis(self, analysis_id: int) -> bool:
        return await self._repo.delete(analysis_id)

    async def _get_company(self, symbol: str) -> Any | None:
        from titan_x.models.company import Company
        result = await self._session.execute(
            select(Company).where(Company.symbol == symbol.upper())
        )
        return result.scalar_one_or_none()

    async def _get_latest_prediction(self, symbol: str) -> Prediction | None:
        result = await self._session.execute(
            select(Prediction).where(Prediction.symbol == symbol)
            .order_by(desc(Prediction.as_of_date)).limit(1)
        )
        return result.scalar_one_or_none()

    async def _get_latest_decision(self, symbol: str) -> TradingDecision | None:
        result = await self._session.execute(
            select(TradingDecision).where(TradingDecision.symbol == symbol)
            .order_by(desc(TradingDecision.as_of_date)).limit(1)
        )
        return result.scalar_one_or_none()

    async def _get_latest_ensemble(self, symbol: str) -> EnsemblePrediction | None:
        result = await self._session.execute(
            select(EnsemblePrediction).where(EnsemblePrediction.symbol == symbol)
            .order_by(desc(EnsemblePrediction.as_of_date)).limit(1)
        )
        return result.scalar_one_or_none()

    async def _get_technical_data(self, symbol: str, as_of_date: date) -> dict[str, Any]:
        lookback = as_of_date - timedelta(days=5)
        result = await self._session.execute(
            select(TechnicalIndicator).where(
                TechnicalIndicator.symbol == symbol,
                TechnicalIndicator.trade_date >= lookback,
                TechnicalIndicator.trade_date <= as_of_date,
                TechnicalIndicator.indicator.in_(["rsi", "sma_20", "sma_50", "ema_12", "macd"]),
            ).order_by(TechnicalIndicator.indicator, desc(TechnicalIndicator.trade_date))
        )
        rows = result.scalars().all()
        data: dict[str, Any] = {}
        for r in rows:
            if r.indicator not in data:
                data[r.indicator] = r
        return data

    async def _get_active_patterns(self, symbol: str) -> Sequence[ChartPattern]:
        result = await self._session.execute(
            select(ChartPattern).where(
                ChartPattern.symbol == symbol,
                ChartPattern.is_active == True,  # noqa: E712
            ).order_by(desc(ChartPattern.confidence_score)).limit(10)
        )
        return result.scalars().all()

    async def _get_risk_metrics(self, symbol: str, as_of_date: date) -> RiskMetrics | None:
        result = await self._session.execute(
            select(RiskMetrics).where(
                RiskMetrics.symbol == symbol,
                RiskMetrics.as_of_date <= as_of_date,
            ).order_by(desc(RiskMetrics.as_of_date)).limit(1)
        )
        return result.scalar_one_or_none()

    async def _get_fundamentals(self, symbol: str) -> Sequence[FundamentalMetric]:
        result = await self._session.execute(
            select(FundamentalMetric).where(
                FundamentalMetric.symbol == symbol,
                FundamentalMetric.period_type == "annual",
            ).order_by(desc(FundamentalMetric.fiscal_year)).limit(15)
        )
        return result.scalars().all()

    async def _get_similarities(self, symbol: str) -> Sequence[SimilarityAnalysis]:
        result = await self._session.execute(
            select(SimilarityAnalysis).where(SimilarityAnalysis.symbol == symbol)
            .order_by(desc(SimilarityAnalysis.created_at)).limit(1)
        )
        return result.scalars().all()

    async def _get_sector_data(self, sector: str | None, as_of_date: date) -> dict[str, Any] | None:
        if not sector:
            return None
        result = await self._session.execute(
            select(SectorPerformance).where(
                SectorPerformance.sector == sector,
                SectorPerformance.as_of_date <= as_of_date,
            ).order_by(desc(SectorPerformance.as_of_date)).limit(5)
        )
        rows = result.scalars().all()
        if not rows:
            return None
        momentum = sum(r.momentum_score or 0 for r in rows) / len(rows)
        strength = sum(r.relative_strength or 50 for r in rows) / len(rows)
        return {"momentum_score": momentum, "relative_strength": strength}

    async def _get_market_breadth(self, as_of_date: date) -> dict[str, Any] | None:
        result = await self._session.execute(
            select(MarketBreadth).where(MarketBreadth.trade_date <= as_of_date)
            .order_by(desc(MarketBreadth.trade_date)).limit(1)
        )
        breadth = result.scalar_one_or_none()
        if breadth is None:
            return None
        adv_decl = breadth.advancing / breadth.declining if breadth.declining > 0 else 1.0
        return {"index_strength_score": breadth.index_strength_score or 50, "adv_decl_ratio": adv_decl}

    async def _get_latest_price(self, symbol: str) -> Any | None:
        from titan_x.models.price import DailyPrice
        result = await self._session.execute(
            select(DailyPrice).where(DailyPrice.symbol == symbol)
            .order_by(desc(DailyPrice.trade_date)).limit(1)
        )
        return result.scalar_one_or_none()
