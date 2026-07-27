from datetime import date
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.models.decision import TradingDecision
from titan_x.models.ensemble import EnsemblePrediction
from titan_x.models.explainability import ExplainabilityAnalysis
from titan_x.models.historical_similarity import SimilarityAnalysis
from titan_x.models.prediction import Prediction
from titan_x.services.explainability_engine import ExplainabilityEngine

SIGNAL_STRENGTHS = {
    "strong_buy": 2, "buy": 1, "hold": 0, "sell": -1, "strong_sell": -2,
    "bullish": 1, "bearish": -1, "neutral": 0,
}


def _signal_to_strength(signal: str | None) -> int:
    if signal is None:
        return 0
    return SIGNAL_STRENGTHS.get(signal.lower(), 0)


class ExplainabilityDashboardService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self._engine = ExplainabilityEngine(session)

    async def get_dashboard(
        self, symbol: str, as_of_date: date | None = None,
    ) -> dict[str, Any]:
        analysis = await self._engine.analyze(symbol, as_of_date, store=False)
        if "error" in analysis:
            return analysis

        symbol_u = symbol.upper()

        prediction = await self._get_latest_prediction(symbol_u)
        decision = await self._get_latest_decision(symbol_u)
        ensemble = await self._get_latest_ensemble(symbol_u)
        stored = await self._get_stored_analysis(symbol_u, as_of_date)

        dashboard: dict[str, Any] = {
            "symbol": symbol_u,
            "as_of_date": analysis.get("as_of_date", as_of_date),
            "overall": {
                "score": analysis.get("overall_score"),
                "signal": analysis.get("overall_signal"),
                "confidence": analysis.get("overall_confidence"),
            },
            "feature_importance": self._compute_feature_importance(analysis),
            "model_agreement": self._compute_model_agreement(
                prediction, decision, ensemble, stored,
            ),
            "confidence_breakdown": self._compute_confidence_breakdown(
                prediction, decision, ensemble, stored, analysis,
            ),
            "risk_factors": analysis.get("risk_factors", []),
            "historical_analogues": await self._compute_historical_analogues(
                analysis, symbol_u,
            ),
        }
        return dashboard

    def _compute_feature_importance(
        self, analysis: dict[str, Any],
    ) -> list[dict[str, Any]]:
        all_factors: list[dict[str, Any]] = []
        for section in ("why_buy", "why_not_buy", "strengths", "weaknesses"):
            for f in analysis.get(section, []):
                all_factors.append({
                    "feature": f["factor"],
                    "importance_score": f["score"],
                    "direction": f["impact"],
                    "source": f["source"],
                    "weight": f["weight"],
                })
        all_factors.sort(key=lambda x: x["importance_score"], reverse=True)
        return all_factors

    def _compute_model_agreement(
        self,
        prediction: Prediction | None,
        decision: TradingDecision | None,
        ensemble: EnsemblePrediction | None,
        stored: ExplainabilityAnalysis | None,
    ) -> dict[str, Any]:
        signals: dict[str, Any] = {}

        if prediction is not None:
            signals["prediction"] = {
                "signal": prediction.overall_signal,
                "strength": _signal_to_strength(prediction.overall_signal),
                "confidence": prediction.overall_confidence,
            }
        if decision is not None:
            signals["decision"] = {
                "signal": decision.recommendation,
                "strength": _signal_to_strength(decision.recommendation),
                "confidence": getattr(decision, "confidence_score", None),
            }
        if ensemble is not None:
            signals["ensemble"] = {
                "signal": ensemble.ensemble_signal,
                "strength": _signal_to_strength(ensemble.ensemble_signal),
                "confidence": ensemble.ensemble_confidence,
                "agreement_level": ensemble.agreement_level,
            }
        if stored is not None:
            signals["overall_analysis"] = {
                "signal": stored.overall_signal,
                "strength": _signal_to_strength(stored.overall_signal),
                "confidence": stored.overall_confidence,
            }

        strengths = [s["strength"] for s in signals.values() if s.get("strength") is not None]
        if not strengths:
            return {"agreement_level": "unknown", "total_models": 0, "signals": signals}

        total = len(strengths)
        positive = sum(1 for s in strengths if s > 0)
        negative = sum(1 for s in strengths if s < 0)
        neutral = sum(1 for s in strengths if s == 0)
        max_count = max(positive, negative, neutral) if any([positive, negative, neutral]) else total

        agreement_pct = max_count / total if total > 0 else 0
        if agreement_pct >= 0.8:
            level = "high"
        elif agreement_pct >= 0.6:
            level = "medium"
        else:
            level = "low"

        dominant = "buy" if positive > negative else "sell" if negative > positive else "neutral"

        return {
            "agreement_level": level,
            "dominant_signal": dominant,
            "total_models": total,
            "agreeing_models": max_count,
            "signals": signals,
        }

    def _compute_confidence_breakdown(
        self,
        prediction: Prediction | None,
        decision: TradingDecision | None,
        ensemble: EnsemblePrediction | None,
        stored: ExplainabilityAnalysis | None,
        analysis: dict[str, Any],
    ) -> dict[str, Any]:
        sources: list[dict[str, Any]] = []

        if prediction is not None and prediction.overall_confidence is not None:
            sources.append({
                "source": "prediction",
                "confidence": prediction.overall_confidence,
                "signal": prediction.overall_signal,
            })
        if decision is not None:
            conf = getattr(decision, "confidence_score", None)
            if conf is not None:
                sources.append({
                    "source": "decision",
                    "confidence": conf,
                    "signal": decision.recommendation,
                })
        if ensemble is not None:
            conf = ensemble.ensemble_confidence
            if conf is not None:
                sources.append({
                    "source": "ensemble",
                    "confidence": conf,
                    "signal": ensemble.ensemble_signal,
                    "agreement_level": ensemble.agreement_level,
                })
        if stored is not None and stored.overall_confidence is not None:
            sources.append({
                "source": "overall_analysis",
                "confidence": stored.overall_confidence,
                "signal": stored.overall_signal,
            })

        conf_values = [s["confidence"] for s in sources if s["confidence"] is not None]
        avg_confidence = sum(conf_values) / len(conf_values) if conf_values else None

        return {
            "overall_confidence": analysis.get("overall_confidence"),
            "average_source_confidence": round(avg_confidence, 1) if avg_confidence is not None else None,
            "sources": sources,
        }

    async def _compute_historical_analogues(
        self, analysis: dict[str, Any], symbol: str,
    ) -> list[dict[str, Any]]:
        analogues: list[dict[str, Any]] = []
        for item in analysis.get("historical_evidence", []):
            record: dict[str, Any] = {
                "description": item["factor"],
                "similarity_score": item["score"],
                "impact": item["impact"],
                "source": item["source"],
                "weight": item["weight"],
            }
            analogues.append(record)

        similarity_analyses = await self._get_similarity_analyses(symbol)
        for sa in similarity_analyses:
            analogues.append({
                "description": f"Historical pattern match with {sa.avg_similarity:.0f}% similarity",
                "similarity_score": sa.avg_similarity or 50,
                "impact": "positive" if (sa.avg_return_5d or 0) >= 0 else "negative",
                "source": "similarity_analysis",
                "avg_similarity": sa.avg_similarity,
                "avg_return_5d": sa.avg_return_5d,
                "avg_return_10d": sa.avg_return_10d,
                "avg_return_20d": sa.avg_return_20d,
                "avg_return_60d": sa.avg_return_60d,
                "max_matches": sa.max_matches,
                "optimal_holding_period": sa.optimal_holding_period,
            })

        analogues.sort(key=lambda x: x.get("similarity_score", 0) or 0, reverse=True)
        return analogues

    async def _get_latest_prediction(self, symbol: str) -> Prediction | None:
        result = await self.session.execute(
            select(Prediction).where(Prediction.symbol == symbol)
            .order_by(desc(Prediction.as_of_date)).limit(1)
        )
        return result.scalar_one_or_none()

    async def _get_latest_decision(self, symbol: str) -> TradingDecision | None:
        result = await self.session.execute(
            select(TradingDecision).where(TradingDecision.symbol == symbol)
            .order_by(desc(TradingDecision.as_of_date)).limit(1)
        )
        return result.scalar_one_or_none()

    async def _get_latest_ensemble(self, symbol: str) -> EnsemblePrediction | None:
        result = await self.session.execute(
            select(EnsemblePrediction).where(EnsemblePrediction.symbol == symbol)
            .order_by(desc(EnsemblePrediction.as_of_date)).limit(1)
        )
        return result.scalar_one_or_none()

    async def _get_stored_analysis(
        self, symbol: str, as_of_date: date | None,
    ) -> ExplainabilityAnalysis | None:
        q = select(ExplainabilityAnalysis).where(ExplainabilityAnalysis.symbol == symbol)
        if as_of_date:
            q = q.where(ExplainabilityAnalysis.as_of_date == as_of_date)
        q = q.order_by(desc(ExplainabilityAnalysis.as_of_date)).limit(1)
        result = await self.session.execute(q)
        return result.scalar_one_or_none()

    async def _get_similarity_analyses(self, symbol: str) -> list[SimilarityAnalysis]:
        result = await self.session.execute(
            select(SimilarityAnalysis).where(SimilarityAnalysis.symbol == symbol)
            .order_by(desc(SimilarityAnalysis.created_at)).limit(5)
        )
        return list(result.scalars().all())
