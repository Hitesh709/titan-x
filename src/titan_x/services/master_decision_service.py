import json
from collections import Counter
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.models.company import Company
from titan_x.models.corporate_tracking import CorporateAnalysis
from titan_x.models.decision import TradingDecision
from titan_x.models.ensemble import EnsemblePrediction
from titan_x.models.explainability import ExplainabilityAnalysis
from titan_x.models.financial_analysis import FinancialAnalysis
from titan_x.models.global_market import GlobalAnalysis
from titan_x.models.institutional_holdings import InstitutionalAnalysis
from titan_x.models.macro import MacroAnalysis
from titan_x.models.master_decision import MasterDecision
from titan_x.models.microstructure import MarketMicrostructure
from titan_x.models.prediction import Prediction
from titan_x.models.price import DailyPrice
from titan_x.models.ranking import StockRanking
from titan_x.models.regime import MarketRegime
from titan_x.models.risk import RiskMetrics
from titan_x.models.valuation import ValuationReport


class MasterDecisionService:
    def __init__(self, session: AsyncSession):
        self.session = session

    SCORE_WEIGHTS = {
        "financial_analysis": 0.15,
        "corporate_governance": 0.08,
        "institutional": 0.08,
        "valuation": 0.12,
        "momentum": 0.10,
        "liquidity": 0.05,
        "technical": 0.10,
        "macro": 0.07,
        "global": 0.07,
        "pattern": 0.05,
        "regime": 0.08,
        "prediction": 0.05,
    }
    STRONG_WEIGHT = sum(v for k, v in SCORE_WEIGHTS.items())  # 1.0

    async def evaluate(
        self, symbol: str, as_of_date: date | None = None,
    ) -> MasterDecision:
        symbol = symbol.upper()
        if as_of_date is None:
            as_of_date = date.today()

        engines: dict[str, Any] = {}

        # 1. Financial Analysis
        engines["financial_analysis"] = await self._get_one(FinancialAnalysis, FinancialAnalysis.symbol, symbol, FinancialAnalysis.analysis_date)

        # 2. Corporate Governance
        engines["corporate_governance"] = await self._get_corp_analysis(symbol)

        # 3. Institutional
        engines["institutional"] = await self._get_inst_analysis(symbol)

        # 4. Valuation
        engines["valuation"] = await self._get_one(ValuationReport, ValuationReport.symbol, symbol, ValuationReport.report_date)

        # 5. Momentum (from DailyPrice)
        engines["momentum"] = await self._get_momentum(symbol, as_of_date)

        # 6. Liquidity
        engines["liquidity"] = await self._get_one(MarketMicrostructure, MarketMicrostructure.symbol, symbol, MarketMicrostructure.as_of_date)

        # 7. Technical (from EnsemblePrediction)
        engines["technical"] = await self._get_one(EnsemblePrediction, EnsemblePrediction.symbol, symbol, EnsemblePrediction.as_of_date)

        # 8. Macro
        engines["macro"] = await self._get_one(MacroAnalysis, None, None, None, by_date=True, as_of_date=as_of_date)

        # 9. Global
        engines["global"] = await self._get_one(GlobalAnalysis, None, None, None, by_date=True, as_of_date=as_of_date)

        # 10. Pattern (from ExplainabilityAnalysis)
        engines["pattern"] = await self._get_one(ExplainabilityAnalysis, ExplainabilityAnalysis.symbol, symbol, ExplainabilityAnalysis.as_of_date)

        # 11. Regime
        engines["regime"] = await self._get_one(MarketRegime, MarketRegime.symbol, symbol, MarketRegime.as_of_date)

        # 12. Prediction
        engines["prediction"] = await self._get_one(Prediction, Prediction.symbol, symbol, Prediction.as_of_date)

        # Score each engine 0-100
        scores = {}
        evidence = {}
        signals = []
        confidences = []

        for name, data in engines.items():
            score, sig, conf, ev = self._score_engine(name, data, symbol, as_of_date)
            if score is not None:
                scores[name] = score
            if sig:
                signals.append(sig)
            if conf is not None:
                confidences.append(conf)
            if ev:
                evidence[name] = ev

        # Weighted composite
        weighted_sum = 0.0
        total_weight = 0.0
        for name, score in scores.items():
            w = self.SCORE_WEIGHTS.get(name, 0.05)
            weighted_sum += score * w
            total_weight += w

        final_score = round(weighted_sum / total_weight, 1) if total_weight > 0 else 50.0

        # Confidence: average of available confidences, with agreement bonus
        avg_conf = sum(confidences) / len(confidences) if confidences else 0.3
        agreement = self._calc_agreement(signals)
        confidence = round(min(1.0, avg_conf * 0.6 + agreement * 0.4), 2)

        # Risk: from risk metrics + liquidity + volatility
        risk_score, risk_level = await self._calc_risk(symbol, as_of_date, engines)

        # Recommendation
        recommendation = self._calc_recommendation(final_score, confidence, risk_score)

        # Weak opportunity filter
        is_weak, rejection_reason = self._check_weak(final_score, confidence, risk_level, len(scores), signals)

        # Evidence
        evidence_str = self._build_evidence(scores, evidence, signals, agreement)

        # Decision summary
        decision_summary = (
            f"{symbol}: Final Score {final_score}/100, Confidence {confidence:.0%}, "
            f"Risk {risk_level}, Recommendation: {recommendation.upper()}. "
            f"Engines: {len(scores)}/12 active. "
            f"{'REJECTED: ' + rejection_reason if is_weak else ''}"
        )

        decision = MasterDecision(
            symbol=symbol,
            as_of_date=as_of_date,
            final_ai_score=final_score,
            confidence=confidence,
            risk_score=round(risk_score, 1),
            risk_level=risk_level,
            recommendation=recommendation,
            is_weak=is_weak,
            rejection_reason=rejection_reason,
            financial_analysis_score=scores.get("financial_analysis"),
            corporate_governance_score=scores.get("corporate_governance"),
            institutional_score=scores.get("institutional"),
            valuation_score=scores.get("valuation"),
            momentum_score=scores.get("momentum"),
            liquidity_score=scores.get("liquidity"),
            technical_score=scores.get("technical"),
            macro_score=scores.get("macro"),
            global_score=scores.get("global"),
            pattern_score=scores.get("pattern"),
            regime_score=scores.get("regime"),
            prediction_score=scores.get("prediction"),
            engine_count=len(scores),
            evidence_json=json.dumps(evidence_str, indent=2),
            decision_summary=decision_summary,
        )
        self.session.add(decision)
        await self.session.flush()
        await self.session.refresh(decision)
        return decision

    async def evaluate_all(self, as_of_date: date | None = None) -> list[MasterDecision]:
        if as_of_date is None:
            as_of_date = date.today()
        result = await self.session.execute(
            select(Company.symbol).where(Company.status == "active")
        )
        symbols = [r[0] for r in result.all()]
        decisions = []
        for sym in symbols:
            d = await self.evaluate(sym, as_of_date)
            decisions.append(d)
        return decisions

    async def get_decision(self, symbol: str, as_of_date: date | None = None) -> MasterDecision | None:
        symbol = symbol.upper()
        stmt = select(MasterDecision).where(MasterDecision.symbol == symbol)
        if as_of_date:
            stmt = stmt.where(MasterDecision.as_of_date == as_of_date)
        stmt = stmt.order_by(MasterDecision.as_of_date.desc()).limit(1)
        r = await self.session.execute(stmt)
        return r.scalar_one_or_none()

    async def list_decisions(
        self, symbol: str | None = None, min_score: float | None = None,
        recommendation: str | None = None, include_weak: bool = False,
        limit: int = 50, offset: int = 0,
    ) -> list[MasterDecision]:
        stmt = select(MasterDecision)
        if symbol:
            stmt = stmt.where(MasterDecision.symbol == symbol.upper())
        if min_score is not None:
            stmt = stmt.where(MasterDecision.final_ai_score >= min_score)
        if recommendation:
            stmt = stmt.where(MasterDecision.recommendation == recommendation)
        if not include_weak:
            stmt = stmt.where(MasterDecision.is_weak == False)
        stmt = stmt.order_by(MasterDecision.final_ai_score.desc()).offset(offset).limit(limit)
        r = await self.session.execute(stmt)
        return list(r.scalars().all())

    # ============================================================
    # ENGINE SCORING
    # ============================================================

    def _score_engine(self, name: str, data: Any, symbol: str, as_of_date: date) -> tuple:
        extractors = {
            "financial_analysis": lambda d: (
                d.overall_score, d.signal, d.confidence or 0.5,
                f"FA: {d.overall_score}/100 ({d.signal}), summary: {d.summary_text[:100] if d.summary_text else 'N/A'}"
            ) if d else (None, None, None, None),
            "corporate_governance": lambda d: (
                d.weighted_score, d.signal, d.confidence or 0.5,
                f"CG: {d.weighted_score}/100 ({d.signal}), promoter/insider/shareholding analysis"
            ) if d else (None, None, None, None),
            "institutional": lambda d: (
                d.composite_score, d.signal, d.confidence or 0.5,
                f"INST: {d.composite_score}/100 ({d.signal}), FII/DII/MF/ETF flows"
            ) if d else (None, None, None, None),
            "valuation": lambda d: (
                self._valuation_to_score(d), self._valuation_to_signal(d), 0.6,
                f"VAL: fair={d.composite_fair_value}, current={d.current_price}, MoS={d.margin_of_safety_pct}%, rec={d.recommendation}"
            ) if d and d.composite_fair_value else (None, None, None, None),
            "momentum": lambda d: (
                d.get("score"), d.get("signal"), d.get("confidence"),
                f"MOM: 20d={d.get('ret_20d'):.2%}, 5d={d.get('ret_5d'):.2%}, vsSMA20={d.get('price_vs_sma_20'):.2%}"
            ) if d else (None, None, None, None),
            "liquidity": lambda d: (
                d.liquidity_score, d.liquidity_rating, 0.5,
                f"LIQ: {d.liquidity_score}/100 ({d.liquidity_rating}), vol={d.volume_ratio}x avg"
            ) if d and d.liquidity_score is not None else (None, None, None, None),
            "technical": lambda d: (
                self._ensemble_to_score(d), d.ensemble_signal if hasattr(d, 'ensemble_signal') else None, d.ensemble_confidence if hasattr(d, 'ensemble_confidence') else 0.5,
                f"TECH: ens_score={d.ensemble_score if hasattr(d, 'ensemble_score') else 'N/A'}, sig={d.ensemble_signal if hasattr(d, 'ensemble_signal') else 'N/A'}"
            ) if d else (None, None, None, None),
            "macro": lambda d: (
                d.composite_macro_score, d.risk_regime, 0.5,
                f"MACRO: {d.composite_macro_score}/100, regime={d.macro_regime}, growth-inflation={d.growth_inflation_regime}"
            ) if d else (None, None, None, None),
            "global": lambda d: (
                d.global_score, d.global_sentiment, 0.5,
                f"GLOBAL: {d.global_score}/100 ({d.global_sentiment}), US={d.us_score}, EU={d.europe_score}, ASIA={d.asia_score}"
            ) if d else (None, None, None, None),
            "pattern": lambda d: (
                d.overall_score, d.overall_signal, d.overall_confidence,
                f"PATTERN: {d.overall_score}/100 ({d.overall_signal}), conf={d.overall_confidence:.0%}"
            ) if d and d.overall_score is not None else (None, None, None, None),
            "regime": lambda d: (
                self._regime_to_score(d), None, d.confidence,
                f"REGIME: trend={d.trend_regime}, vol={d.volatility_regime}, sentiment={d.sentiment_regime}, momentum_20d={d.momentum_20d:.2%}"
            ) if d else (None, None, None, None),
            "prediction": lambda d: (
                self._prediction_to_score(d), d.signal_20d or d.signal_5d, d.confidence_20d or d.confidence_5d or 0.5,
                f"PRED: 5d={d.signal_5d}({d.confidence_5d:.0%}), 20d={d.signal_20d}({d.confidence_20d:.0%})"
            ) if d else (None, None, None, None),
        }
        extractor = extractors.get(name, lambda d: (None, None, None, None))
        return extractor(data)

    # ============================================================
    # HELPERS
    # ============================================================

    async def _get_one(self, model, symbol_col, symbol, date_col, by_date=False, as_of_date=None):
        if by_date:
            stmt = select(model).order_by(model.as_of_date.desc()).limit(1)
        else:
            stmt = select(model).where(symbol_col == symbol).order_by(date_col.desc()).limit(1)
        r = await self.session.execute(stmt)
        return r.scalar_one_or_none()

    async def _get_corp_analysis(self, symbol: str):
        r = await self.session.execute(
            select(Company.id).where(Company.symbol == symbol)
        )
        cid = r.scalar_one_or_none()
        if not cid:
            return None
        r2 = await self.session.execute(
            select(CorporateAnalysis).where(CorporateAnalysis.company_id == cid)
            .order_by(CorporateAnalysis.analysis_date.desc()).limit(1)
        )
        return r2.scalar_one_or_none()

    async def _get_inst_analysis(self, symbol: str):
        r = await self.session.execute(
            select(Company.id).where(Company.symbol == symbol)
        )
        cid = r.scalar_one_or_none()
        if not cid:
            return None
        r2 = await self.session.execute(
            select(InstitutionalAnalysis).where(InstitutionalAnalysis.company_id == cid)
            .order_by(InstitutionalAnalysis.analysis_date.desc()).limit(1)
        )
        return r2.scalar_one_or_none()

    async def _get_momentum(self, symbol: str, as_of_date: date) -> dict | None:
        lookback = as_of_date - timedelta(days=60)
        r = await self.session.execute(
            select(DailyPrice).where(
                DailyPrice.symbol == symbol,
                DailyPrice.trade_date >= lookback,
                DailyPrice.trade_date <= as_of_date,
            ).order_by(DailyPrice.trade_date.asc())
        )
        prices = list(r.scalars().all())
        if len(prices) < 5:
            return None
        closes = [p.close for p in prices]
        ret_20d = (closes[-1] - closes[-21]) / closes[-21] if len(closes) >= 21 else 0
        ret_5d = (closes[-1] - closes[-6]) / closes[-6] if len(closes) >= 6 else 0
        sma_20 = sum(closes[-20:]) / 20 if len(closes) >= 20 else closes[-1]
        pv = (closes[-1] - sma_20) / sma_20 if sma_20 > 0 else 0
        score = max(0, min(100, round(50 + ret_20d * 150 + ret_5d * 100 + pv * 100, 1)))
        sig = "bullish" if score >= 55 else "bearish" if score <= 45 else "neutral"
        conf = min(0.8, max(0.3, abs(score - 50) / 100 + 0.3))
        return {"score": score, "signal": sig, "confidence": round(conf, 2), "ret_20d": ret_20d, "ret_5d": ret_5d, "price_vs_sma_20": pv}

    async def _calc_risk(self, symbol: str, as_of_date: date, engines: dict) -> tuple:
        risk_scores = []
        rk = await self._get_one(RiskMetrics, RiskMetrics.symbol, symbol, RiskMetrics.as_of_date)
        if rk and rk.composite_risk_score is not None:
            risk_scores.append(rk.composite_risk_score)
        ms = engines.get("liquidity")
        if ms and ms.liquidity_score is not None:
            risk_scores.append(100 - ms.liquidity_score)
        regime = engines.get("regime")
        if regime and regime.volatility_regime == "high_volatility":
            risk_scores.append(75)
        elif regime and regime.volatility_regime == "low_volatility":
            risk_scores.append(25)
        avg_risk = sum(risk_scores) / len(risk_scores) if risk_scores else 50.0
        if avg_risk >= 65:
            level = "high"
        elif avg_risk >= 35:
            level = "moderate"
        else:
            level = "low"
        return avg_risk, level

    def _calc_recommendation(self, score: float, confidence: float, risk_score: float) -> str:
        effective = score * confidence
        risk_penalty = (risk_score - 50) * 0.2
        adjusted = effective - risk_penalty
        if adjusted >= 55:
            return "strong_buy"
        elif adjusted >= 40:
            return "buy"
        elif adjusted >= 25:
            return "hold"
        elif adjusted >= 10:
            return "sell"
        return "strong_sell"

    def _check_weak(self, score: float, confidence: float, risk_level: str, engine_count: int, signals: list) -> tuple:
        if engine_count < 3:
            return True, f"Insufficient data: only {engine_count}/12 engines active"
        if confidence < 0.25:
            return True, f"Low confidence: {confidence:.0%}"
        if risk_level == "high" and score < 40:
            return True, f"High risk ({risk_level}) with weak score ({score})"
        if score < 15:
            return True, f"Very low score: {score}/100"
        buy_count = sum(1 for s in signals if s in ("strong_buy", "buy", "bullish"))
        sell_count = sum(1 for s in signals if s in ("strong_sell", "sell", "bearish"))
        total_sig = buy_count + sell_count
        if total_sig >= 4:
            ratio = buy_count / total_sig
            if 0.3 < ratio < 0.7:
                return True, f"Conflicting signals: {buy_count} bullish vs {sell_count} bearish"
        return False, None

    def _calc_agreement(self, signals: list) -> float:
        if not signals:
            return 0.0
        buy = sum(1 for s in signals if s in ("strong_buy", "buy", "bullish", "risk_on"))
        sell = sum(1 for s in signals if s in ("strong_sell", "sell", "bearish", "risk_off"))
        total = buy + sell
        if total == 0:
            return 0.5
        majority = max(buy, sell)
        return majority / total

    def _build_evidence(self, scores: dict, evidence: dict, signals: list, agreement: float) -> dict:
        return {
            "engine_scores": scores,
            "engine_evidence": evidence,
            "signal_summary": dict(Counter(signals)),
            "agreement_score": round(agreement, 2),
        }

    def _valuation_to_score(self, vr) -> float | None:
        if not vr or not vr.composite_fair_value or not vr.current_price:
            return None
        upside = (vr.composite_fair_value - vr.current_price) / vr.current_price
        return max(0, min(100, round(50 + upside * 100, 1)))

    def _valuation_to_signal(self, vr) -> str | None:
        return vr.recommendation if vr else None

    def _regime_to_score(self, rg) -> float:
        score = 50.0
        if rg.trend_regime == "bull":
            score += 20
        elif rg.trend_regime == "bear":
            score -= 20
        if rg.sentiment_regime == "risk_on":
            score += 10
        elif rg.sentiment_regime == "risk_off":
            score -= 10
        return max(0, min(100, score))

    def _prediction_to_score(self, pred) -> float | None:
        if pred and pred.expected_return_20d is not None:
            return max(0, min(100, round(50 + pred.expected_return_20d * 200, 1)))
        return None

    def _ensemble_to_score(self, ens) -> float | None:
        if hasattr(ens, 'ensemble_score') and ens.ensemble_score is not None:
            return ens.ensemble_score
        srcs = []
        for s in ['technical', 'fundamental', 'news', 'macro', 'risk', 'pattern', 'similarity']:
            v = getattr(ens, f'{s}_score', None)
            if v is not None:
                srcs.append(v)
        return round(sum(srcs) / len(srcs), 1) if srcs else None
