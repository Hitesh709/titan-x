import json
import math
from collections.abc import Sequence
from datetime import date, timedelta
from typing import Any

import structlog
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.db.repository import BaseRepository
from titan_x.models.chart_pattern import ChartPattern
from titan_x.models.company import Company
from titan_x.models.ensemble import EnsemblePrediction
from titan_x.models.fundamental import FundamentalMetric
from titan_x.models.historical_similarity import SimilarityAnalysis
from titan_x.models.market_breadth import MarketBreadth
from titan_x.models.news import NewsArticle
from titan_x.models.news_nlp import NewsNLPAnalysis
from titan_x.models.risk import RiskMetrics
from titan_x.models.sector import SectorPerformance
from titan_x.models.technical import TechnicalIndicator

logger = structlog.get_logger(__name__)

DEFAULT_WEIGHTS = {
    "technical": 0.20,
    "fundamental": 0.20,
    "news": 0.15,
    "macro": 0.15,
    "risk": 0.15,
    "pattern": 0.15,
}

SIGNAL_MAP = {2: "strong_buy", 1: "buy", 0: "hold", -1: "sell", -2: "strong_sell"}


class EnsembleAIEngine:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = BaseRepository(session, EnsemblePrediction)

    async def predict(
        self, symbol: str, as_of_date: date | None = None,
        weights: dict[str, float] | None = None, store: bool = False,
    ) -> dict[str, Any]:
        if as_of_date is None:
            as_of_date = date.today()
        if weights is None:
            weights = dict(DEFAULT_WEIGHTS)

        company = await self._get_company(symbol)
        if company is None:
            return {"symbol": symbol, "error": f"Company {symbol} not found"}

        technical = await self._analyze_technical(symbol, as_of_date)
        fundamental = await self._analyze_fundamental(symbol, as_of_date)
        news = await self._analyze_news(symbol, as_of_date)
        macro = await self._analyze_macro(company.sector, as_of_date)
        risk = await self._analyze_risk(symbol, as_of_date)
        pattern = await self._analyze_pattern(symbol, as_of_date)

        sub_models = {
            "technical": technical,
            "fundamental": fundamental,
            "news": news,
            "macro": macro,
            "risk": risk,
            "pattern": pattern,
        }

        weighted_vote = self._compute_weighted_vote(sub_models, weights)
        agreement = self._compute_agreement(sub_models, weighted_vote["signal"])
        explanation = self._generate_explanation(
            symbol, company.company_name, sub_models, weighted_vote, agreement, weights,
        )

        result: dict[str, Any] = {
            "symbol": symbol,
            "as_of_date": as_of_date.isoformat(),
            "ensemble_score": weighted_vote["score"],
            "ensemble_signal": weighted_vote["signal"],
            "ensemble_confidence": weighted_vote["confidence"],
            "agreement_level": agreement["level"],
            "vote_breakdown_json": json.dumps(agreement["breakdown"]),
            "weights_json": json.dumps(weights),
            "explanation": explanation,
        }

        for name, sm in sub_models.items():
            result[f"{name}_score"] = sm.get("score")
            result[f"{name}_signal"] = sm.get("signal")
            result[f"{name}_confidence"] = sm.get("confidence")

        if store:
            existing = await self._session.execute(
                select(EnsemblePrediction).where(
                    EnsemblePrediction.symbol == symbol,
                    EnsemblePrediction.as_of_date == as_of_date,
                )
            )
            if existing.scalar_one_or_none() is not None:
                raise ValueError(f"Ensemble prediction already exists for {symbol} on {as_of_date}")
            rec = await self._repo.create(
                symbol=symbol, as_of_date=as_of_date,
                technical_score=result["technical_score"],
                technical_signal=result["technical_signal"],
                technical_confidence=result["technical_confidence"],
                fundamental_score=result["fundamental_score"],
                fundamental_signal=result["fundamental_signal"],
                fundamental_confidence=result["fundamental_confidence"],
                news_score=result["news_score"],
                news_signal=result["news_signal"],
                news_confidence=result["news_confidence"],
                macro_score=result["macro_score"],
                macro_signal=result["macro_signal"],
                macro_confidence=result["macro_confidence"],
                risk_score=result["risk_score"],
                risk_signal=result["risk_signal"],
                risk_confidence=result["risk_confidence"],
                pattern_score=result["pattern_score"],
                pattern_signal=result["pattern_signal"],
                pattern_confidence=result["pattern_confidence"],
                ensemble_score=result["ensemble_score"],
                ensemble_signal=result["ensemble_signal"],
                ensemble_confidence=result["ensemble_confidence"],
                agreement_level=result["agreement_level"],
                vote_breakdown_json=result["vote_breakdown_json"],
                weights_json=result["weights_json"],
                explanation=result["explanation"],
            )
            result["id"] = rec.id

        return result

    async def _get_company(self, symbol: str) -> Company | None:
        result = await self._session.execute(
            select(Company).where(Company.symbol == symbol),
        )
        return result.scalar_one_or_none()

    async def _analyze_technical(self, symbol: str, as_of_date: date) -> dict[str, Any]:
        start = as_of_date - timedelta(days=30)
        indicators = await self._session.execute(
            select(TechnicalIndicator)
            .where(
                TechnicalIndicator.symbol == symbol,
                TechnicalIndicator.trade_date.between(start, as_of_date),
            )
            .order_by(TechnicalIndicator.trade_date.desc())
        )
        rows = indicators.scalars().all()
        if not rows:
            return {"score": 50, "signal": "neutral", "confidence": 30}

        latest: dict[str, TechnicalIndicator] = {}
        for r in rows:
            if r.indicator not in latest:
                latest[r.indicator] = r

        signals: list[dict] = []
        if "rsi" in latest:
            rsi = latest["rsi"].value
            if rsi is not None:
                if rsi > 70:
                    signals.append({"score": 20, "weight": 2})
                elif rsi < 30:
                    signals.append({"score": 80, "weight": 2})
                elif rsi > 60:
                    signals.append({"score": 60, "weight": 1})
                elif rsi < 40:
                    signals.append({"score": 40, "weight": 1})
                else:
                    signals.append({"score": 50, "weight": 1})

        if "macd" in latest:
            macd = latest["macd"]
            if macd.value is not None and macd.value_secondary is not None:
                if macd.value > macd.value_secondary:
                    signals.append({"score": 65, "weight": 2})
                else:
                    signals.append({"score": 35, "weight": 2})

        for ma_name in ["sma_20", "sma_50", "ema_12"]:
            if ma_name in latest:
                ma = latest[ma_name]
                if ma.value is not None and ma.value_secondary is not None:
                    if ma.value_secondary > ma.value:
                        signals.append({"score": 65, "weight": 1})
                    else:
                        signals.append({"score": 35, "weight": 1})

        if not signals:
            return {"score": 50, "signal": "neutral", "confidence": 30}

        total = sum(s["score"] * s["weight"] for s in signals)
        wsum = sum(s["weight"] for s in signals)
        avg = total / wsum if wsum > 0 else 50
        score = max(0, min(100, avg))
        signal = self._score_to_signal(score)
        conf = min(70, 30 + len(signals) * 10)
        return {"score": round(score, 2), "signal": signal, "confidence": conf}

    async def _analyze_fundamental(self, symbol: str, as_of_date: date) -> dict[str, Any]:
        metrics = await self._session.execute(
            select(FundamentalMetric)
            .where(
                FundamentalMetric.symbol == symbol,
                FundamentalMetric.period_type == "annual",
            )
            .order_by(FundamentalMetric.fiscal_year.desc())
            .limit(20)
        )
        rows = metrics.scalars().all()
        if not rows:
            return {"score": 50, "signal": "neutral", "confidence": 20}

        values: dict[str, float] = {}
        for r in rows:
            if r.metric_name not in values and r.value is not None:
                values[r.metric_name] = r.value

        signals: list[dict] = []
        pe = values.get("PE_RATIO") or values.get("pe_ratio") or values.get("PE")
        if pe is not None and pe > 0:
            if pe < 10:
                signals.append({"score": 75, "weight": 2})
            elif pe < 20:
                signals.append({"score": 60, "weight": 1})
            elif pe > 40:
                signals.append({"score": 30, "weight": 2})
            elif pe > 25:
                signals.append({"score": 45, "weight": 1})

        roe = values.get("ROE") or values.get("roe")
        if roe is not None:
            if roe > 0.20:
                signals.append({"score": 75, "weight": 2})
            elif roe > 0.10:
                signals.append({"score": 60, "weight": 1})
            elif roe < 0:
                signals.append({"score": 25, "weight": 2})

        quality = values.get("QUALITY_SCORE") or values.get("quality_score")
        if quality is not None:
            signals.append({"score": quality, "weight": 2})

        if not signals:
            return {"score": 50, "signal": "neutral", "confidence": 20}

        total = sum(s["score"] * s["weight"] for s in signals)
        wsum = sum(s["weight"] for s in signals)
        avg = total / wsum if wsum > 0 else 50
        score = max(0, min(100, avg))
        signal = self._score_to_signal(score)
        conf = min(60, 20 + len(signals) * 10)
        return {"score": round(score, 2), "signal": signal, "confidence": conf}

    async def _analyze_news(self, symbol: str, as_of_date: date) -> dict[str, Any]:
        start = as_of_date - timedelta(days=30)
        analyses = await self._session.execute(
            select(NewsNLPAnalysis)
            .join(NewsArticle, NewsNLPAnalysis.article_id == NewsArticle.id)
            .where(
                NewsArticle.symbol == symbol,
                NewsArticle.published_at.between(start, as_of_date),
            )
            .order_by(NewsArticle.published_at.desc())
            .limit(50)
        )
        rows = analyses.scalars().all()
        if not rows:
            return {"score": 50, "signal": "neutral", "confidence": 25}

        scores: list[float] = []
        confidences: list[float] = []
        for r in rows:
            if r.sentiment_positive is not None and r.sentiment_negative is not None:
                net = (r.sentiment_positive - r.sentiment_negative) * 100
                scores.append(net)
                confidences.append(r.sentiment_confidence or 0.5)

        if not scores:
            return {"score": 50, "signal": "neutral", "confidence": 25}

        avg_net = sum(scores) / len(scores)
        avg_conf = sum(confidences) / len(confidences) if confidences else 0.5
        score = max(0, min(100, (avg_net + 100) / 2))
        signal = "bullish" if avg_net > 10 else "bearish" if avg_net < -10 else "neutral"
        conf = min(80, 25 + int(avg_conf * 50) + int(len(scores) / 5))
        return {"score": round(score, 2), "signal": signal, "confidence": conf}

    async def _analyze_macro(self, sector: str | None, as_of_date: date) -> dict[str, Any]:
        scores: list[float] = []
        conf = 30

        if sector:
            sector_perf = await self._session.execute(
                select(SectorPerformance)
                .where(
                    SectorPerformance.sector == sector,
                    SectorPerformance.period_label == "1M",
                )
                .order_by(SectorPerformance.as_of_date.desc())
                .limit(1)
            )
            sp = sector_perf.scalar_one_or_none()
            if sp and sp.momentum_score is not None:
                ms = max(-50, min(50, sp.momentum_score))
                scores.append(50 + ms)
                conf += 20
                if sp.relative_strength is not None:
                    rs = max(-2, min(2, sp.relative_strength))
                    scores.append(50 + (rs * 20))
                    conf += 10

        breadth = await self._session.execute(
            select(MarketBreadth)
            .order_by(MarketBreadth.trade_date.desc())
            .limit(1)
        )
        mb = breadth.scalar_one_or_none()
        if mb:
            if mb.index_strength_score is not None:
                scores.append(mb.index_strength_score)
                conf += 15
            if mb.breadth_oscillator is not None:
                osc = max(-100, min(100, mb.breadth_oscillator))
                scores.append(50 + osc / 2)
                conf += 15

        if not scores:
            return {"score": 50, "signal": "neutral", "confidence": 30}

        avg = sum(scores) / len(scores)
        score = max(0, min(100, avg))
        signal = self._score_to_signal(score)
        conf = min(80, conf)
        return {"score": round(score, 2), "signal": signal, "confidence": conf}

    async def _analyze_risk(self, symbol: str, as_of_date: date) -> dict[str, Any]:
        risk = await self._session.execute(
            select(RiskMetrics)
            .where(
                RiskMetrics.symbol == symbol,
                RiskMetrics.as_of_date <= as_of_date,
            )
            .order_by(RiskMetrics.as_of_date.desc())
            .limit(1)
        )
        rm = risk.scalar_one_or_none()
        if rm is None or rm.composite_risk_score is None:
            return {"score": 50, "signal": "neutral", "confidence": 25}

        risk_score = rm.composite_risk_score
        inverted = max(0, min(100, 100 - risk_score))
        if inverted >= 70:
            signal = "bullish"
        elif inverted <= 30:
            signal = "bearish"
        else:
            signal = "neutral"

        vol = rm.volatility_252d
        conf = 50
        if vol is not None:
            if vol < 20:
                conf = 75
            elif vol < 40:
                conf = 60
            elif vol < 60:
                conf = 45
            else:
                conf = 30
        if rm.liquidity_score is not None:
            conf = (conf + rm.liquidity_score) / 2

        return {"score": round(inverted, 2), "signal": signal, "confidence": round(conf, 2)}

    async def _analyze_pattern(self, symbol: str, as_of_date: date) -> dict[str, Any]:
        patterns = await self._session.execute(
            select(ChartPattern)
            .where(
                ChartPattern.symbol == symbol,
                ChartPattern.is_active == True,
                ChartPattern.end_date <= as_of_date,
            )
            .order_by(ChartPattern.confidence_score.desc().nullslast())
            .limit(5)
        )
        pat_rows = patterns.scalars().all()

        scores: list[float] = []
        conf = 20

        for p in pat_rows:
            if p.confidence_score is not None and p.confidence_score >= 40:
                if p.direction == "bullish":
                    scores.append(p.confidence_score)
                elif p.direction == "bearish":
                    scores.append(100 - p.confidence_score)
                conf = max(conf, p.confidence_score)

        sim = await self._session.execute(
            select(SimilarityAnalysis)
            .where(
                SimilarityAnalysis.symbol == symbol,
            )
            .order_by(SimilarityAnalysis.created_at.desc())
            .limit(1)
        )
        sa = sim.scalar_one_or_none()
        if sa and sa.avg_similarity is not None and sa.avg_similarity >= 50:
            scores.append(50 + sa.avg_similarity / 2)
            conf = min(85, conf + 15)
            if sa.avg_return_20d is not None:
                if sa.avg_return_20d > 3:
                    scores.append(65)
                elif sa.avg_return_20d < -3:
                    scores.append(35)

        if not scores:
            return {"score": 50, "signal": "neutral", "confidence": 20}

        avg = sum(scores) / len(scores)
        score = max(0, min(100, avg))
        signal = self._score_to_signal(score)
        conf = max(20, min(90, conf))
        return {"score": round(score, 2), "signal": signal, "confidence": conf}

    def _score_to_signal(self, score: float) -> str:
        if score >= 65:
            return "bullish"
        elif score <= 35:
            return "bearish"
        return "neutral"

    def _compute_weighted_vote(
        self, sub_models: dict[str, dict], weights: dict[str, float],
    ) -> dict[str, Any]:
        numeric_signals = {"strong_buy": 2, "buy": 1, "bullish": 1, "hold": 0, "neutral": 0, "sell": -1, "bearish": -1, "strong_sell": -2}

        total_weight = 0.0
        weighted_score = 0.0
        weighted_signal = 0.0
        conf_sum = 0.0

        for name, sm in sub_models.items():
            w = weights.get(name, 0.15)
            score = sm.get("score")
            sig = sm.get("signal")
            sig_num = numeric_signals.get(sig, 0) if sig else 0
            conf = sm.get("confidence", 50)

            if score is not None:
                weighted_score += score * w
                weighted_signal += sig_num * w
                conf_sum += conf * w
                total_weight += w

        if total_weight == 0:
            return {"score": 50, "signal": "hold", "confidence": 0}

        avg_score = weighted_score / total_weight
        avg_signal_num = weighted_signal / total_weight
        avg_conf = conf_sum / total_weight

        signal_num = round(avg_signal_num)
        signal_num = max(-2, min(2, signal_num))
        signal = SIGNAL_MAP[signal_num]

        conf = max(0, min(100, avg_conf))
        agreement_factor = self._agreement_factor(sub_models, signal)
        conf = max(0, min(100, conf * (0.7 + 0.3 * agreement_factor)))

        return {"score": round(avg_score, 2), "signal": signal, "confidence": round(conf, 2)}

    def _agreement_factor(self, sub_models: dict, consensus: str) -> float:
        numeric_signals = {"strong_buy": 2, "buy": 1, "bullish": 1, "hold": 0, "neutral": 0, "sell": -1, "bearish": -1, "strong_sell": -2}
        consensus_num = numeric_signals.get(consensus, 0)

        agreeing = 0
        total = 0
        for sm in sub_models.values():
            sig = sm.get("signal")
            if sig:
                total += 1
                if numeric_signals.get(sig, 0) == consensus_num:
                    agreeing += 1

        return agreeing / max(total, 1)

    def _compute_agreement(self, sub_models: dict, consensus: str) -> dict[str, Any]:
        factor = self._agreement_factor(sub_models, consensus)
        if factor >= 0.66:
            level = "high"
        elif factor >= 0.33:
            level = "medium"
        else:
            level = "low"

        breakdown = {}
        for name, sm in sub_models.items():
            breakdown[name] = {
                "signal": sm.get("signal", "neutral"),
                "vote_match": sm.get("signal") == consensus if sm.get("signal") else False,
            }

        return {"level": level, "factor": round(factor, 2), "breakdown": breakdown}

    def _generate_explanation(
        self, symbol: str, company_name: str | None,
        sub_models: dict[str, dict], vote: dict[str, Any],
        agreement: dict[str, Any], weights: dict[str, float],
    ) -> str:
        name = company_name or symbol
        rec_upper = vote["signal"].upper()
        parts: list[str] = []
        parts.append(f"ENSEMBLE PREDICTION for {name} ({symbol})")
        parts.append(f"Signal: {rec_upper} | Score: {vote['score']:.0f}/100 | Confidence: {vote['confidence']:.0f}% | Agreement: {agreement['level'].upper()}")
        parts.append("")

        sections: list[str] = []
        eng_names = {
            "technical": "Technical Analysis", "fundamental": "Fundamental Analysis",
            "news": "News Sentiment", "macro": "Macro Environment",
            "risk": "Risk Assessment", "pattern": "Pattern Recognition",
        }

        for name, info in sub_models.items():
            label = eng_names.get(name, name.title())
            score = info.get("score")
            sig = info.get("signal", "neutral")
            conf = info.get("confidence", 0)
            weight = weights.get(name, 0) * 100
            if score is not None:
                sections.append(
                    f"  {label}: {sig.upper()} (score={score:.0f}, confidence={conf:.0f}%, weight={weight:.0f}%)"
                )

        if sections:
            parts.append("SUB-MODEL VOTES:")
            parts.extend(sections)

        parts.append("")
        numeric_signals = {"strong_buy": 2, "buy": 1, "bullish": 1, "hold": 0, "neutral": 0, "sell": -1, "bearish": -1, "strong_sell": -2}
        votes_for = sum(1 for sm in sub_models.values() if numeric_signals.get(sm.get("signal")) == numeric_signals.get(vote["signal"]))
        votes_total = sum(1 for sm in sub_models.values() if sm.get("signal"))
        parts.append(f"Consensus: {votes_for}/{votes_total} models agree on {rec_upper}")

        if vote["signal"] in ("strong_buy", "buy"):
            parts.append("ACTION: Consider establishing or adding to long position.")
        elif vote["signal"] in ("strong_sell", "sell"):
            parts.append("ACTION: Consider reducing or exiting position.")
        else:
            parts.append("ACTION: Maintain current position. Wait for clearer signals.")

        return "\n".join(parts)

    async def get_prediction(
        self, symbol: str, as_of_date: date | None = None,
    ) -> EnsemblePrediction | None:
        stmt = select(EnsemblePrediction).where(EnsemblePrediction.symbol == symbol)
        if as_of_date:
            stmt = stmt.where(EnsemblePrediction.as_of_date == as_of_date)
        stmt = stmt.order_by(EnsemblePrediction.as_of_date.desc()).limit(1)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_prediction_history(
        self, symbol: str | None = None,
        signal: str | None = None,
        min_confidence: float | None = None,
        start_date: date | None = None, end_date: date | None = None,
        skip: int = 0, limit: int = 100,
    ) -> tuple[Sequence[EnsemblePrediction], int]:
        stmt = select(EnsemblePrediction)
        if symbol:
            stmt = stmt.where(EnsemblePrediction.symbol == symbol)
        if signal:
            stmt = stmt.where(EnsemblePrediction.ensemble_signal == signal)
        if min_confidence is not None:
            stmt = stmt.where(EnsemblePrediction.ensemble_confidence >= min_confidence)
        if start_date:
            stmt = stmt.where(EnsemblePrediction.as_of_date >= start_date)
        if end_date:
            stmt = stmt.where(EnsemblePrediction.as_of_date <= end_date)

        count_result = await self._session.execute(stmt)
        total = len(count_result.scalars().all())
        stmt = stmt.order_by(EnsemblePrediction.as_of_date.desc()).offset(skip).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all()), total

    async def delete_prediction(self, prediction_id: int) -> bool:
        return await self._repo.delete(prediction_id)
