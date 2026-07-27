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
from titan_x.models.fundamental import FundamentalMetric
from titan_x.models.historical_similarity import SimilarityAnalysis
from titan_x.models.market_breadth import MarketBreadth
from titan_x.models.prediction import Prediction
from titan_x.models.risk import RiskMetrics
from titan_x.models.sector import SectorPerformance
from titan_x.models.technical import TechnicalIndicator

logger = structlog.get_logger(__name__)

HORIZONS = [5, 10, 15, 20, 30]
SIMILARITY_HORIZON_MAP = {5: "avg_return_5d", 10: "avg_return_10d", 20: "avg_return_20d"}


class PredictionEngine:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = BaseRepository(session, Prediction)

    async def predict(
        self, symbol: str, as_of_date: date | None = None, store: bool = True,
    ) -> dict[str, Any]:
        if as_of_date is None:
            as_of_date = date.today()

        company = await self._get_company(symbol)
        if company is None:
            return {"symbol": symbol, "error": f"Company {symbol} not found"}

        similarities = await self._get_similarities(symbol)
        latest_price = await self._get_latest_price(symbol)
        technical = await self._get_technical_data(symbol, as_of_date)
        patterns = await self._get_patterns(symbol, as_of_date)
        risk = await self._get_risk_metrics(symbol, as_of_date)
        fundamentals = await self._get_fundamentals(symbol)
        sector_data = await self._get_sector_data(company.sector, as_of_date)
        breadth = await self._get_market_breadth(as_of_date)

        horizons_data: dict[int, dict[str, Any]] = {}
        best_horizon = 20
        best_score = -999.0

        for h in HORIZONS:
            h_result = self._compute_horizon_prediction(
                h, similarities, technical, patterns, risk, fundamentals, sector_data, breadth, latest_price,
            )
            horizons_data[h] = h_result
            score = h_result.get("expected_return", 0) if h_result.get("signal") in ("buy", "strong_buy") else -abs(h_result.get("expected_return", 0))
            if score > best_score:
                best_score = score
                best_horizon = h

        holding_period = best_horizon
        if similarities and similarities[0].optimal_holding_period is not None:
            holding_period = similarities[0].optimal_holding_period

        overall_score, overall_signal, overall_conf = self._compute_overall(horizons_data)

        data_sources = {
            "has_similarity": len(similarities) > 0,
            "has_technical": bool(technical),
            "has_patterns": len(patterns) > 0,
            "has_risk": risk is not None,
            "has_fundamentals": len(fundamentals) > 0,
            "has_sector": sector_data is not None,
            "has_breadth": breadth is not None,
            "has_price": latest_price is not None,
        }

        explanation = self._build_explanation(symbol, horizons_data, holding_period, overall_signal, overall_conf)

        result: dict[str, Any] = {
            "symbol": symbol,
            "as_of_date": as_of_date,
            "holding_period": holding_period,
            "overall_signal": overall_signal,
            "overall_score": round(overall_score, 2),
            "overall_confidence": round(overall_conf, 2),
            "horizon_summary_json": json.dumps({str(h): horizons_data[h] for h in HORIZONS}),
            "data_sources_json": json.dumps(data_sources),
            "explanation": explanation,
            "metadata_json": "{}",
        }

        for h in HORIZONS:
            hd = horizons_data[h]
            result[f"probability_{h}d"] = round(hd["probability"], 2)
            result[f"expected_return_{h}d"] = round(hd["expected_return"], 4)
            result[f"expected_drawdown_{h}d"] = round(hd["expected_drawdown"], 4)
            result[f"confidence_{h}d"] = round(hd["confidence"], 2)
            result[f"signal_{h}d"] = hd["signal"]

        if store:
            existing = await self._get_prediction(symbol, as_of_date)
            if existing:
                raise ValueError(f"Prediction for {symbol} on {as_of_date} already exists")
            try:
                stored = await self._repo.create(**{k: v for k, v in result.items() if hasattr(Prediction, k)})
                result["id"] = stored.id
            except Exception:
                await self._session.rollback()
                raise

        return result

    def _compute_horizon_prediction(
        self, horizon: int,
        similarities: Sequence[SimilarityAnalysis],
        technical: dict[str, Any] | None,
        patterns: Sequence[ChartPattern],
        risk: RiskMetrics | None,
        fundamentals: Sequence[FundamentalMetric],
        sector_data: dict[str, Any] | None,
        breadth: dict[str, Any] | None,
        latest_price: Any | None,
    ) -> dict[str, Any]:
        signals: list[dict[str, Any]] = []

        sim_return = self._get_similarity_return(similarities, horizon)
        if sim_return is not None:
            sim_conf = similarities[0].avg_similarity if similarities and similarities[0].avg_similarity is not None else 50
            signals.append({"type": "similarity", "value": sim_return, "weight": 0.35, "conf": sim_conf / 100})

        tech_score = self._compute_technical_score(technical, horizon)
        if tech_score is not None:
            signals.append({"type": "technical", "value": tech_score["return"], "weight": 0.25, "conf": tech_score["confidence"]})

        pattern_score = self._compute_pattern_score(patterns, horizon)
        if pattern_score is not None:
            signals.append({"type": "pattern", "value": pattern_score["return"], "weight": 0.15, "conf": pattern_score["confidence"]})

        sector_score = self._compute_sector_score(sector_data, horizon)
        if sector_score is not None:
            signals.append({"type": "sector", "value": sector_score["return"], "weight": 0.10, "conf": sector_score["confidence"]})

        breadth_score = self._compute_breadth_score(breadth, horizon)
        if breadth_score is not None:
            signals.append({"type": "breadth", "value": breadth_score["return"], "weight": 0.08, "conf": breadth_score["confidence"]})

        fundamental_score = self._compute_fundamental_score(fundamentals)
        if fundamental_score is not None:
            signals.append({"type": "fundamental", "value": fundamental_score["return"], "weight": 0.07, "conf": fundamental_score["confidence"]})

        if not signals:
            return {
                "probability": 50.0,
                "expected_return": 0.0,
                "expected_drawdown": 0.0,
                "confidence": 20.0,
                "signal": "hold",
            }

        total_weight = sum(s["weight"] for s in signals)
        weighted_return = sum(s["value"] * s["weight"] for s in signals) / total_weight
        weighted_conf = sum(s["conf"] * s["weight"] for s in signals) / total_weight

        probability = self._compute_probability(weighted_return, weighted_conf, signals)
        expected_return = max(-100, min(100, weighted_return))
        expected_drawdown = self._compute_expected_drawdown(horizon, risk, weighted_return)
        confidence = max(5, min(95, weighted_conf * 100))

        signal = self._return_to_signal(expected_return, probability, confidence)

        return {
            "probability": probability,
            "expected_return": round(expected_return, 4),
            "expected_drawdown": round(expected_drawdown, 4),
            "confidence": round(confidence, 2),
            "signal": signal,
        }

    def _get_similarity_return(self, similarities: Sequence[SimilarityAnalysis], horizon: int) -> float | None:
        if not similarities:
            return None
        sa = similarities[0]

        direct = SIMILARITY_HORIZON_MAP.get(horizon)
        if direct:
            val = getattr(sa, direct, None)
            if val is not None:
                return float(val)

        if horizon == 15:
            r10 = sa.avg_return_10d
            r20 = sa.avg_return_20d
            if r10 is not None and r20 is not None:
                return float(r10 + (r20 - r10) * 0.5)
            if r10 is not None:
                return float(r10 * 1.5)
            if r20 is not None:
                return float(r20 * 0.75)
        elif horizon == 30:
            r20 = sa.avg_return_20d
            r60 = sa.avg_return_60d
            if r20 is not None and r60 is not None:
                return float(r20 + (r60 - r20) * 0.25)
            if r20 is not None:
                return float(r20 * 1.25)
            if r60 is not None:
                return float(r60 * 0.5)

        return None

    def _compute_technical_score(self, technical: dict[str, Any] | None, horizon: int) -> dict[str, Any] | None:
        if not technical:
            return None

        signals: list[float] = []
        confs: list[float] = []

        if "sma_20" in technical and "sma_50" in technical:
            sma20 = technical["sma_20"].value
            sma50 = technical["sma_50"].value
            if sma20 is not None and sma50 is not None and sma50 > 0:
                slope = (sma20 - sma50) / sma50
                scaled_return = slope * 100
                signals.append(max(-20, min(20, scaled_return)))
                confs.append(60)

        if "macd" in technical:
            macd = technical["macd"]
            if macd.value is not None and macd.value_secondary is not None:
                macd_diff = (macd.value - macd.value_secondary) / abs(macd.value_secondary) if macd.value_secondary != 0 else 0
                signals.append(max(-15, min(15, macd_diff * 100)))
                confs.append(65)

        if "rsi" in technical:
            rsi = technical["rsi"].value
            if rsi is not None:
                if rsi > 70:
                    signals.append(-5)
                    confs.append(70)
                elif rsi < 30:
                    signals.append(8)
                    confs.append(70)
                elif rsi > 60:
                    signals.append(3)
                    confs.append(50)
                elif rsi < 40:
                    signals.append(-2)
                    confs.append(50)

        if not signals:
            return None

        avg_return = sum(signals) / len(signals) * (horizon / 20) ** 0.5
        avg_conf = sum(confs) / len(confs) / 100
        return {"return": avg_return, "confidence": avg_conf}

    def _compute_pattern_score(self, patterns: Sequence[ChartPattern], horizon: int) -> dict[str, Any] | None:
        if not patterns:
            return None

        scores: list[float] = []
        confs: list[float] = []

        for p in patterns:
            if not p.is_active or p.confidence_score is None:
                continue
            if p.confidence_score < 40:
                continue
            if p.direction == "bullish":
                ret = p.confidence_score * 0.15
            elif p.direction == "bearish":
                ret = -p.confidence_score * 0.15
            else:
                continue
            scores.append(ret)
            confs.append(p.confidence_score)

        if not scores:
            return None

        avg_return = sum(scores) / len(scores) * (horizon / 20) ** 0.5
        avg_conf = sum(confs) / len(confs) / 100
        return {"return": avg_return, "confidence": avg_conf}

    def _compute_sector_score(self, sector_data: dict[str, Any] | None, horizon: int) -> dict[str, Any] | None:
        if not sector_data:
            return None
        momentum = sector_data.get("momentum_score", 0)
        rotation = sector_data.get("rotation_signal", "neutral")
        strength = sector_data.get("relative_strength", 0)

        ret = momentum * 0.5 + strength * 0.5
        ret = ret * (horizon / 20) ** 0.5 * 0.01

        conf = 40 + abs(momentum + strength) / 2
        if rotation == "strengthening":
            conf += 10
        elif rotation == "weakening":
            conf -= 10

        return {"return": max(-10, min(10, ret)), "confidence": max(0.1, min(1, conf / 100))}

    def _compute_breadth_score(self, breadth: dict[str, Any] | None, horizon: int) -> dict[str, Any] | None:
        if not breadth:
            return None
        strength = breadth.get("index_strength_score", 50)
        adv_decl_ratio = breadth.get("adv_decl_ratio", 1.0)

        ret = (strength - 50) * 0.1 + (adv_decl_ratio - 1) * 0.5
        ret = ret * (horizon / 20) ** 0.5
        conf = 30 + abs(strength - 50) * 0.6
        return {"return": max(-10, min(10, ret)), "confidence": max(0.1, min(1, conf / 100))}

    def _compute_fundamental_score(self, fundamentals: Sequence[FundamentalMetric]) -> dict[str, Any] | None:
        if not fundamentals:
            return None
        pe = None
        quality = None
        roe = None

        for m in fundamentals:
            if m.metric_name == "PE_RATIO" and m.value is not None and m.value > 0:
                pe = m.value
            elif m.metric_name == "QUALITY_SCORE" and m.value is not None:
                quality = m.value
            elif m.metric_name == "ROE" and m.value is not None:
                roe = m.value

        if pe is None and quality is None and roe is None:
            return None

        ret = 0.0
        conf = 30

        if pe is not None:
            if pe < 10:
                ret += 3
                conf += 15
            elif pe < 15:
                ret += 1
                conf += 5
            elif pe > 30:
                ret -= 2
                conf -= 5
            elif pe > 50:
                ret -= 4
                conf -= 10

        if quality is not None:
            ret += (quality - 50) * 0.1
            conf += abs(quality - 50) * 0.3

        if roe is not None:
            if roe > 20:
                ret += 2
                conf += 10
            elif roe > 10:
                ret += 1
                conf += 5
            elif roe < 0:
                ret -= 3
                conf -= 10

        return {"return": max(-10, min(10, ret)), "confidence": max(0.1, min(1, conf / 100))}

    def _compute_probability(self, weighted_return: float, weighted_conf: float, signals: list[dict]) -> float:
        if weighted_return > 0:
            base = 50 + min(45, abs(weighted_return) * weighted_conf * 5)
        else:
            base = 50 - min(45, abs(weighted_return) * weighted_conf * 5)

        agreement = self._compute_signal_agreement(signals)
        base = base * 0.7 + agreement * 0.3
        return max(5, min(95, base))

    def _compute_signal_agreement(self, signals: list[dict]) -> float:
        if not signals:
            return 50
        directions = [1 if s["value"] > 0.5 else (-1 if s["value"] < -0.5 else 0) for s in signals]
        if not directions:
            return 50
        positive = sum(1 for d in directions if d > 0)
        negative = sum(1 for d in directions if d < 0)
        neutral = len(directions) - positive - negative
        majority = max(positive, negative)
        if majority == 0:
            return 50
        return majority / len(directions) * 100

    def _compute_expected_drawdown(self, horizon: int, risk: RiskMetrics | None, expected_return: float) -> float:
        vol = 0.20
        if risk is not None:
            if risk.volatility_252d is not None:
                vol = risk.volatility_252d / 100
            elif risk.volatility_60d is not None:
                vol = risk.volatility_60d / 100

        time_factor = (horizon / 252) ** 0.5
        base_dd = vol * time_factor * 2.33

        if expected_return < 0:
            base_dd = base_dd + abs(expected_return) * 0.5

        if risk is not None:
            if risk.max_drawdown_1y is not None:
                base_dd = max(base_dd, risk.max_drawdown_1y / 100)
            if risk.event_risk_score is not None:
                base_dd += risk.event_risk_score * 0.01

        return max(0, min(50, base_dd * 100))

    def _return_to_signal(self, expected_return: float, probability: float, confidence: float) -> str:
        combined = expected_return * (probability / 100) * (confidence / 100)
        if combined > 3:
            return "strong_buy"
        elif combined > 1:
            return "buy"
        elif combined < -3:
            return "strong_sell"
        elif combined < -1:
            return "sell"
        return "hold"

    def _compute_overall(self, horizons_data: dict[int, dict]) -> tuple[float, str, float]:
        scores = [h.get("expected_return", 0) for h in horizons_data.values()]
        confs = [h.get("confidence", 0) for h in horizons_data.values()]

        if not scores or all(s == 0 for s in scores):
            return 50, "hold", 20

        avg_score = sum(scores) / len(scores)
        avg_conf = sum(confs) / len(confs)

        weighted_signals = sum(
            h.get("expected_return", 0) * h.get("confidence", 0) * h.get("probability", 50) / 5000
            for h in horizons_data.values()
        )

        if weighted_signals > 2:
            signal = "strong_buy"
        elif weighted_signals > 0.5:
            signal = "buy"
        elif weighted_signals < -2:
            signal = "strong_sell"
        elif weighted_signals < -0.5:
            signal = "sell"
        else:
            signal = "hold"

        return avg_score, signal, avg_conf

    def _build_explanation(
        self, symbol: str, horizons_data: dict[int, dict],
        holding_period: int, signal: str, conf: float,
    ) -> str:
        lines: list[str] = []
        lines.append(f"PREDICTION ANALYSIS FOR {symbol}")
        lines.append("")

        for h in HORIZONS:
            hd = horizons_data[h]
            lines.append(
                f"  {h}-Day: Signal={hd['signal'].upper()}, "
                f"Return={hd['expected_return']:+.2f}%, "
                f"Prob={hd['probability']:.0f}%, "
                f"Drawdown={hd['expected_drawdown']:.2f}%, "
                f"Conf={hd['confidence']:.0f}%"
            )

        lines.append("")
        lines.append(f"Optimal Holding Period: {holding_period} days")
        lines.append(f"Overall: {signal.upper()} (confidence={conf:.0f}%)")
        lines.append("")
        lines.append("KEY FACTORS:")
        lines.append("  - Historical similarity forward returns inform base expectations")
        lines.append("  - Technical indicators validate trend direction and strength")
        lines.append("  - Chart patterns provide medium-term directional bias")
        lines.append("  - Sector & market breadth establish macro regime context")
        lines.append("  - Risk metrics calibrate expected drawdown estimates")

        lines.append("")
        action = "Consider establishing long position with defined risk parameters." if signal in ("strong_buy", "buy") else "Consider reducing exposure or establishing hedge." if signal in ("strong_sell", "sell") else "Maintain neutral posture; wait for clearer signals."
        lines.append(f"ACTION: {action}")

        return "\n".join(lines)

    async def _get_company(self, symbol: str) -> Company | None:
        result = await self._session.execute(
            select(Company).where(Company.symbol == symbol.upper())
        )
        return result.scalar_one_or_none()

    async def _get_similarities(self, symbol: str) -> Sequence[SimilarityAnalysis]:
        result = await self._session.execute(
            select(SimilarityAnalysis)
            .where(SimilarityAnalysis.symbol == symbol)
            .order_by(desc(SimilarityAnalysis.created_at))
            .limit(1)
        )
        return result.scalars().all()

    async def _get_latest_price(self, symbol: str) -> Any | None:
        from titan_x.models.price import DailyPrice
        result = await self._session.execute(
            select(DailyPrice)
            .where(DailyPrice.symbol == symbol)
            .order_by(desc(DailyPrice.trade_date))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _get_technical_data(self, symbol: str, as_of_date: date) -> dict[str, Any]:
        lookback = as_of_date - timedelta(days=5)
        result = await self._session.execute(
            select(TechnicalIndicator)
            .where(
                TechnicalIndicator.symbol == symbol,
                TechnicalIndicator.trade_date >= lookback,
                TechnicalIndicator.trade_date <= as_of_date,
                TechnicalIndicator.indicator.in_(["sma_20", "sma_50", "ema_12", "macd", "rsi"]),
            )
            .order_by(TechnicalIndicator.indicator, desc(TechnicalIndicator.trade_date))
        )
        rows = result.scalars().all()
        data: dict[str, Any] = {}
        for r in rows:
            if r.indicator not in data:
                data[r.indicator] = r
        return data

    async def _get_patterns(self, symbol: str, as_of_date: date) -> Sequence[ChartPattern]:
        result = await self._session.execute(
            select(ChartPattern)
            .where(
                ChartPattern.symbol == symbol,
                ChartPattern.is_active == True,  # noqa: E712
                ChartPattern.end_date <= as_of_date,
            )
            .order_by(desc(ChartPattern.confidence_score))
            .limit(10)
        )
        return result.scalars().all()

    async def _get_risk_metrics(self, symbol: str, as_of_date: date) -> RiskMetrics | None:
        result = await self._session.execute(
            select(RiskMetrics)
            .where(
                RiskMetrics.symbol == symbol,
                RiskMetrics.as_of_date <= as_of_date,
            )
            .order_by(desc(RiskMetrics.as_of_date))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _get_fundamentals(self, symbol: str) -> Sequence[FundamentalMetric]:
        result = await self._session.execute(
            select(FundamentalMetric)
            .where(
                FundamentalMetric.symbol == symbol,
                FundamentalMetric.period_type == "annual",
                FundamentalMetric.metric_name.in_(["PE_RATIO", "QUALITY_SCORE", "ROE"]),
            )
            .order_by(desc(FundamentalMetric.fiscal_year))
            .limit(10)
        )
        return result.scalars().all()

    async def _get_sector_data(self, sector: str | None, as_of_date: date) -> dict[str, Any] | None:
        if not sector:
            return None
        result = await self._session.execute(
            select(SectorPerformance)
            .where(
                SectorPerformance.sector == sector,
                SectorPerformance.as_of_date <= as_of_date,
            )
            .order_by(desc(SectorPerformance.as_of_date))
            .limit(5)
        )
        rows = result.scalars().all()
        if not rows:
            return None
        momentum = sum(r.momentum_score or 0 for r in rows) / len(rows)
        strength = sum(r.relative_strength or 50 for r in rows) / len(rows)
        rotation = "neutral"
        return {"momentum_score": momentum, "relative_strength": strength, "rotation_signal": rotation}

    async def _get_market_breadth(self, as_of_date: date) -> dict[str, Any] | None:
        result = await self._session.execute(
            select(MarketBreadth)
            .where(MarketBreadth.trade_date <= as_of_date)
            .order_by(desc(MarketBreadth.trade_date))
            .limit(1)
        )
        breadth = result.scalar_one_or_none()
        if breadth is None:
            return None
        adv_decl = breadth.advancing / breadth.declining if breadth.declining > 0 else 1.0
        return {
            "index_strength_score": breadth.index_strength_score or 50,
            "adv_decl_ratio": adv_decl,
        }

    async def get_prediction(
        self, symbol: str, as_of_date: date | None = None,
    ) -> Prediction | None:
        query = select(Prediction).where(Prediction.symbol == symbol)
        if as_of_date:
            query = query.where(Prediction.as_of_date == as_of_date)
        query = query.order_by(desc(Prediction.as_of_date)).limit(1)
        result = await self._session.execute(query)
        return result.scalar_one_or_none()

    async def _get_prediction(self, symbol: str, as_of_date: date) -> Prediction | None:
        result = await self._session.execute(
            select(Prediction).where(
                Prediction.symbol == symbol,
                Prediction.as_of_date == as_of_date,
            )
        )
        return result.scalar_one_or_none()

    async def get_prediction_history(
        self, symbol: str | None = None, signal: str | None = None,
        min_confidence: float | None = None,
        start_date: date | None = None, end_date: date | None = None,
        skip: int = 0, limit: int = 100,
    ) -> tuple[Sequence[Prediction], int]:
        query = select(Prediction)
        count_query = select(func.count()).select_from(Prediction)

        if symbol:
            query = query.where(Prediction.symbol == symbol)
            count_query = count_query.where(Prediction.symbol == symbol)
        if signal:
            query = query.where(Prediction.overall_signal == signal)
            count_query = count_query.where(Prediction.overall_signal == signal)
        if min_confidence is not None:
            query = query.where(Prediction.overall_confidence >= min_confidence)
            count_query = count_query.where(Prediction.overall_confidence >= min_confidence)
        if start_date:
            query = query.where(Prediction.as_of_date >= start_date)
            count_query = count_query.where(Prediction.as_of_date >= start_date)
        if end_date:
            query = query.where(Prediction.as_of_date <= end_date)
            count_query = count_query.where(Prediction.as_of_date <= end_date)

        total_result = await self._session.execute(count_query)
        total = total_result.scalar() or 0

        query = query.order_by(desc(Prediction.as_of_date)).offset(skip).limit(limit)
        result = await self._session.execute(query)
        return result.scalars().all(), total

    async def delete_prediction(self, prediction_id: int) -> bool:
        return await self._repo.delete(prediction_id)
