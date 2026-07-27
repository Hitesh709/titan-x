import json
import math
from collections.abc import Sequence
from datetime import date, datetime, timedelta, timezone
from typing import Any

import structlog
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.db.repository import BaseRepository
from titan_x.models.chart_pattern import ChartPattern
from titan_x.models.company import Company
from titan_x.models.dynamic_ai_score import DynamicAIScore, DynamicWeight
from titan_x.models.fundamental import FundamentalMetric
from titan_x.models.historical_similarity import SimilarityAnalysis
from titan_x.models.macro import MacroAnalysis
from titan_x.models.market_breadth import MarketBreadth
from titan_x.models.news import NewsArticle
from titan_x.models.news_nlp import NewsNLPAnalysis
from titan_x.models.regime import MarketRegime
from titan_x.models.risk import RiskMetrics
from titan_x.models.sector import SectorPerformance
from titan_x.models.technical import TechnicalIndicator

logger = structlog.get_logger(__name__)

SOURCE_NAMES = [
    "technical", "fundamental", "news", "macro",
    "liquidity", "risk", "market_regime",
]

DEFAULT_WEIGHTS: dict[str, float] = {s: 1.0 / len(SOURCE_NAMES) for s in SOURCE_NAMES}

SIGNAL_MAP = {2: "strong_buy", 1: "buy", 0: "hold", -1: "sell", -2: "strong_sell"}


class DynamicAIScoreService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = BaseRepository(session, DynamicAIScore)

    async def compute_score(
        self, symbol: str, as_of_date: date | None = None, store: bool = False,
    ) -> dict[str, Any]:
        if as_of_date is None:
            as_of_date = date.today()

        company = await self._get_company(symbol)
        if company is None:
            return {"symbol": symbol, "error": f"Company {symbol} not found"}

        signals = {
            "technical": await self._signal_technical(symbol, as_of_date),
            "fundamental": await self._signal_fundamental(symbol, as_of_date),
            "news": await self._signal_news(symbol, as_of_date),
            "macro": await self._signal_macro(company.sector, as_of_date),
            "liquidity": await self._signal_liquidity(symbol, as_of_date),
            "risk": await self._signal_risk(symbol, as_of_date),
            "market_regime": await self._signal_market_regime(symbol, as_of_date),
        }

        weights = await self._load_weights()
        combined = self._combine(signals, weights)

        result = self._build_result(symbol, as_of_date, signals, combined, weights)

        if store:
            rec = await self._repo.create(**result["db_fields"])
            result["id"] = rec.id

        return result

    async def _get_company(self, symbol: str) -> Company | None:
        result = await self._session.execute(
            select(Company).where(Company.symbol == symbol),
        )
        return result.scalar_one_or_none()

    async def _signal_technical(self, symbol: str, as_of_date: date) -> dict[str, Any]:
        start = as_of_date - timedelta(days=30)
        rows = (await self._session.execute(
            select(TechnicalIndicator)
            .where(
                TechnicalIndicator.symbol == symbol,
                TechnicalIndicator.trade_date.between(start, as_of_date),
            )
            .order_by(TechnicalIndicator.trade_date.desc())
        )).scalars().all()
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
        conf = min(70, 30 + len(signals) * 10)
        return {"score": round(score, 2), "signal": self._score_to_signal(score), "confidence": conf}

    async def _signal_fundamental(self, symbol: str, as_of_date: date) -> dict[str, Any]:
        rows = (await self._session.execute(
            select(FundamentalMetric)
            .where(
                FundamentalMetric.symbol == symbol,
                FundamentalMetric.period_type == "annual",
            )
            .order_by(FundamentalMetric.fiscal_year.desc())
            .limit(20)
        )).scalars().all()
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
        conf = min(60, 20 + len(signals) * 10)
        return {"score": round(score, 2), "signal": self._score_to_signal(score), "confidence": conf}

    async def _signal_news(self, symbol: str, as_of_date: date) -> dict[str, Any]:
        start = as_of_date - timedelta(days=30)
        rows = (await self._session.execute(
            select(NewsNLPAnalysis)
            .join(NewsArticle, NewsNLPAnalysis.article_id == NewsArticle.id)
            .where(
                NewsArticle.symbol == symbol,
                NewsArticle.published_at.between(start, as_of_date),
            )
            .order_by(NewsArticle.published_at.desc())
            .limit(50)
        )).scalars().all()
        if not rows:
            return {"score": 50, "signal": "neutral", "confidence": 25}

        scores: list[float] = []
        confs: list[float] = []
        for r in rows:
            if r.sentiment_positive is not None and r.sentiment_negative is not None:
                net = (r.sentiment_positive - r.sentiment_negative) * 100
                scores.append(net)
                confs.append(r.sentiment_confidence or 0.5)

        if not scores:
            return {"score": 50, "signal": "neutral", "confidence": 25}

        avg_net = sum(scores) / len(scores)
        avg_conf = sum(confs) / len(confs) if confs else 0.5
        score = max(0, min(100, (avg_net + 100) / 2))
        if avg_net > 10:
            signal = "bullish"
        elif avg_net < -10:
            signal = "bearish"
        else:
            signal = "neutral"
        conf = min(80, 25 + int(avg_conf * 50) + int(len(scores) / 5))
        return {"score": round(score, 2), "signal": signal, "confidence": conf}

    async def _signal_macro(self, sector: str | None, as_of_date: date) -> dict[str, Any]:
        scores: list[float] = []
        conf = 30

        if sector:
            sp = (await self._session.execute(
                select(SectorPerformance)
                .where(
                    SectorPerformance.sector == sector,
                    SectorPerformance.period_label == "1M",
                )
                .order_by(SectorPerformance.as_of_date.desc())
                .limit(1)
            )).scalar_one_or_none()
            if sp and sp.momentum_score is not None:
                ms = max(-50, min(50, sp.momentum_score))
                scores.append(50 + ms)
                conf += 20
                if sp.relative_strength is not None:
                    rs = max(-2, min(2, sp.relative_strength))
                    scores.append(50 + (rs * 20))
                    conf += 10

        ma = (await self._session.execute(
            select(MacroAnalysis)
            .order_by(MacroAnalysis.as_of_date.desc())
            .limit(1)
        )).scalar_one_or_none()
        if ma and ma.composite_macro_score is not None:
            scores.append(ma.composite_macro_score)
            conf += 15

        mb = (await self._session.execute(
            select(MarketBreadth)
            .order_by(MarketBreadth.trade_date.desc())
            .limit(1)
        )).scalar_one_or_none()
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
        conf = min(80, conf)
        return {"score": round(score, 2), "signal": self._score_to_signal(score), "confidence": conf}

    async def _signal_liquidity(self, symbol: str, as_of_date: date) -> dict[str, Any]:
        rm = (await self._session.execute(
            select(RiskMetrics)
            .where(
                RiskMetrics.symbol == symbol,
                RiskMetrics.as_of_date <= as_of_date,
            )
            .order_by(RiskMetrics.as_of_date.desc())
            .limit(1)
        )).scalar_one_or_none()

        if rm is None:
            return {"score": 50, "signal": "neutral", "confidence": 25}

        liquidity_score = rm.liquidity_score
        if liquidity_score is not None:
            score = max(0, min(100, liquidity_score))
        else:
            score = 50

        vol = rm.avg_daily_volume_20d
        adv = rm.avg_dollar_volume_20d
        conf = 40
        if vol is not None and adv is not None:
            if vol > 5_000_000 and adv > 50_000_000:
                conf = 75
            elif vol > 1_000_000 and adv > 10_000_000:
                conf = 60
            elif vol > 200_000 and adv > 2_000_000:
                conf = 50
            else:
                conf = 35

        signal = self._score_to_signal(score)
        return {"score": round(score, 2), "signal": signal, "confidence": round(conf, 2)}

    async def _signal_risk(self, symbol: str, as_of_date: date) -> dict[str, Any]:
        rm = (await self._session.execute(
            select(RiskMetrics)
            .where(
                RiskMetrics.symbol == symbol,
                RiskMetrics.as_of_date <= as_of_date,
            )
            .order_by(RiskMetrics.as_of_date.desc())
            .limit(1)
        )).scalar_one_or_none()

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

        return {"score": round(inverted, 2), "signal": signal, "confidence": round(conf, 2)}

    async def _signal_market_regime(self, symbol: str, as_of_date: date) -> dict[str, Any]:
        regime = (await self._session.execute(
            select(MarketRegime)
            .where(
                MarketRegime.symbol == symbol,
                MarketRegime.as_of_date <= as_of_date,
            )
            .order_by(MarketRegime.as_of_date.desc())
            .limit(1)
        )).scalar_one_or_none()

        if regime is None:
            return {"score": 50, "signal": "neutral", "confidence": 25}

        scores: list[float] = []
        if regime.trend_score is not None:
            scores.append(regime.trend_score)
        if regime.sentiment_score is not None:
            scores.append(regime.sentiment_score)
        if regime.volatility_score is not None:
            scores.append(100 - regime.volatility_score)

        if not scores:
            return {"score": 50, "signal": "neutral", "confidence": 25}

        avg = max(0, min(100, sum(scores) / len(scores)))
        signal = self._score_to_signal(avg)
        conf = max(25, min(90, int(regime.confidence * 100)))
        return {"score": round(avg, 2), "signal": signal, "confidence": conf}

    def _score_to_signal(self, score: float) -> str:
        if score >= 65:
            return "bullish"
        elif score <= 35:
            return "bearish"
        return "neutral"

    async def _load_weights(self) -> dict[str, float]:
        rows = (await self._session.execute(
            select(DynamicWeight)
        )).scalars().all()

        if not rows:
            return dict(DEFAULT_WEIGHTS)

        weights: dict[str, float] = {}
        for r in rows:
            weights[r.source_name] = r.weight
        for source in SOURCE_NAMES:
            weights.setdefault(source, DEFAULT_WEIGHTS[source])
        return weights

    def _combine(
        self, signals: dict[str, dict[str, Any]], weights: dict[str, float],
    ) -> dict[str, Any]:
        numeric_signals = {
            "strong_buy": 2, "buy": 1, "bullish": 1,
            "hold": 0, "neutral": 0,
            "sell": -1, "bearish": -1, "strong_sell": -2,
        }

        total_weight = 0.0
        weighted_score = 0.0
        weighted_signal = 0.0
        conf_sum = 0.0

        for name in SOURCE_NAMES:
            sm = signals.get(name, {})
            w = weights.get(name, DEFAULT_WEIGHTS.get(name, 0))
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
        agreement_factor = self._agreement_factor(signals, signal)
        conf = max(0, min(100, conf * (0.7 + 0.3 * agreement_factor)))

        return {
            "score": round(avg_score, 2),
            "signal": signal,
            "confidence": round(conf, 2),
        }

    def _agreement_factor(
        self, signals: dict[str, dict[str, Any]], consensus: str,
    ) -> float:
        numeric_signals = {
            "strong_buy": 2, "buy": 1, "bullish": 1,
            "hold": 0, "neutral": 0,
            "sell": -1, "bearish": -1, "strong_sell": -2,
        }
        consensus_num = numeric_signals.get(consensus, 0)
        agreeing = 0
        total = 0
        for name in SOURCE_NAMES:
            sm = signals.get(name, {})
            sig = sm.get("signal")
            if sig:
                total += 1
                if numeric_signals.get(sig, 0) == consensus_num:
                    agreeing += 1
        return agreeing / max(total, 1)

    def _build_result(
        self, symbol: str, as_of_date: date,
        signals: dict[str, dict[str, Any]],
        combined: dict[str, Any],
        weights: dict[str, float],
    ) -> dict[str, Any]:
        db_fields: dict[str, Any] = {
            "symbol": symbol,
            "as_of_date": as_of_date,
        }

        for name in SOURCE_NAMES:
            sm = signals.get(name, {})
            db_fields[f"{name}_score"] = sm.get("score")
            db_fields[f"{name}_signal"] = sm.get("signal")
            db_fields[f"{name}_confidence"] = sm.get("confidence")

        db_fields["combined_score"] = combined["score"]
        db_fields["combined_signal"] = combined["signal"]
        db_fields["combined_confidence"] = combined["confidence"]
        db_fields["weights_json"] = json.dumps(weights)

        source_signals = {}
        for name in SOURCE_NAMES:
            sm = signals.get(name, {})
            source_signals[name] = {
                "score": sm.get("score"),
                "signal": sm.get("signal"),
                "confidence": sm.get("confidence"),
            }
        db_fields["source_signals_json"] = json.dumps(source_signals)

        result: dict[str, Any] = {
            "symbol": symbol,
            "as_of_date": as_of_date.isoformat(),
            "combined_score": combined["score"],
            "combined_signal": combined["signal"],
            "combined_confidence": combined["confidence"],
            "weights": weights,
            "source_signals": source_signals,
            "db_fields": db_fields,
        }
        for name in SOURCE_NAMES:
            sm = signals.get(name, {})
            result[f"{name}_score"] = sm.get("score")
            result[f"{name}_signal"] = sm.get("signal")
            result[f"{name}_confidence"] = sm.get("confidence")

        return result

    async def adjust_weights(
        self, symbol: str, as_of_date: date, actual_return_pct: float,
    ) -> dict[str, Any]:
        score = await self.get_score(symbol, as_of_date)
        if score is None:
            return {"error": f"No score found for {symbol} on {as_of_date}"}

        source_signals = json.loads(score.source_signals_json or "{}")
        adjustments: dict[str, float] = {}
        details: dict[str, Any] = {}

        for name in SOURCE_NAMES:
            sig_info = source_signals.get(name, {})
            sig = sig_info.get("signal", "neutral")
            conf = sig_info.get("confidence", 50)

            predicted_direction = self._signal_to_direction(sig)
            actual_direction = 1 if actual_return_pct > 0.5 else (-1 if actual_return_pct < -0.5 else 0)

            correct = predicted_direction == actual_direction

            weight = await self._get_or_create_weight(name)
            weight.total_predictions += 1
            if correct:
                weight.correct_predictions += 1
            weight.adjusted_at = datetime.now(timezone.utc)

            accuracy = weight.accuracy()
            weight.performance_score = accuracy

            if accuracy >= 70:
                adjustment = 0.02
            elif accuracy >= 50:
                adjustment = 0.0
            elif accuracy >= 30:
                adjustment = -0.01
            else:
                adjustment = -0.02

            if not correct and conf >= 60:
                adjustment -= 0.01

            adjustments[name] = adjustment
            details[name] = {
                "signal": sig,
                "predicted_direction": predicted_direction,
                "actual_direction": actual_direction,
                "correct": correct,
                "correct_predictions": weight.correct_predictions,
                "total_predictions": weight.total_predictions,
                "accuracy": round(accuracy, 2),
                "adjustment": adjustment,
            }

            self._session.add(weight)

        rows = (await self._session.execute(
            select(DynamicWeight)
        )).scalars().all()
        weight_map: dict[str, float] = {}
        for r in rows:
            w = max(0.01, min(1.0, r.weight + adjustments.get(r.source_name, 0)))
            r.weight = w
            weight_map[r.source_name] = round(w, 4)

        total_w = sum(weight_map.values())
        if total_w > 0:
            for r in rows:
                r.weight = round(r.weight / total_w, 4)
                weight_map[r.source_name] = r.weight

        await self._session.flush()

        return {
            "symbol": symbol,
            "as_of_date": as_of_date.isoformat(),
            "actual_return_pct": actual_return_pct,
            "adjusted_weights": weight_map,
            "details": details,
        }

    def _signal_to_direction(self, signal: str) -> int:
        if signal in ("strong_buy", "buy", "bullish"):
            return 1
        elif signal in ("strong_sell", "sell", "bearish"):
            return -1
        return 0

    async def _get_or_create_weight(self, source_name: str) -> DynamicWeight:
        result = await self._session.execute(
            select(DynamicWeight).where(DynamicWeight.source_name == source_name),
        )
        weight = result.scalar_one_or_none()
        if weight is None:
            weight = DynamicWeight(
                source_name=source_name,
                weight=DEFAULT_WEIGHTS.get(source_name, 0.15),
                performance_score=None,
                total_predictions=0,
                correct_predictions=0,
            )
            self._session.add(weight)
            await self._session.flush()
        return weight

    async def get_score(
        self, symbol: str, as_of_date: date,
    ) -> DynamicAIScore | None:
        result = await self._session.execute(
            select(DynamicAIScore).where(
                DynamicAIScore.symbol == symbol,
                DynamicAIScore.as_of_date == as_of_date,
            )
        )
        return result.scalar_one_or_none()

    async def get_score_history(
        self, symbol: str | None = None,
        signal: str | None = None,
        min_score: float | None = None,
        start_date: date | None = None, end_date: date | None = None,
        skip: int = 0, limit: int = 100,
    ) -> tuple[Sequence[DynamicAIScore], int]:
        stmt = select(DynamicAIScore)
        if symbol:
            stmt = stmt.where(DynamicAIScore.symbol == symbol)
        if signal:
            stmt = stmt.where(DynamicAIScore.combined_signal == signal)
        if min_score is not None:
            stmt = stmt.where(DynamicAIScore.combined_score >= min_score)
        if start_date:
            stmt = stmt.where(DynamicAIScore.as_of_date >= start_date)
        if end_date:
            stmt = stmt.where(DynamicAIScore.as_of_date <= end_date)

        count_result = await self._session.execute(stmt)
        total = len(count_result.scalars().all())
        stmt = stmt.order_by(desc(DynamicAIScore.as_of_date)).offset(skip).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all()), total

    async def get_weights(self) -> dict[str, Any]:
        rows = (await self._session.execute(
            select(DynamicWeight).order_by(DynamicWeight.source_name)
        )).scalars().all()
        return {
            "weights": {r.source_name: r.weight for r in rows},
            "performance": {
                r.source_name: {
                    "weight": r.weight,
                    "performance_score": r.performance_score,
                    "accuracy": round(r.accuracy(), 2),
                    "total_predictions": r.total_predictions,
                    "correct_predictions": r.correct_predictions,
                    "adjusted_at": r.adjusted_at.isoformat() if r.adjusted_at else None,
                }
                for r in rows
            },
        }

    async def delete_score(self, score_id: int) -> bool:
        return await self._repo.delete(score_id)
