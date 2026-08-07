import json
import math
from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.models.ai_ranking_v2 import AIRankingV2, RankingModelWeight
from titan_x.models.ensemble import EnsemblePrediction
from titan_x.models.nightly_evaluation import NightlyEvaluation, PredictionError
from titan_x.models.prediction import Prediction
from titan_x.models.price import DailyPrice

DEFAULT_FAILURE_THRESHOLD_PCT = 10.0
DEFAULT_BIAS_THRESHOLD = 5.0

PILLAR_FIELDS = [
    ("technical", "technical_score", "technical_signal"),
    ("fundamental", "fundamental_score", "fundamental_signal"),
    ("news", "news_score", "news_signal"),
    ("macro", "macro_score", "macro_signal"),
    ("risk", "risk_score", "risk_signal"),
    ("pattern", "pattern_score", "pattern_signal"),
]


class NightlyEvaluationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def run_evaluation(
        self, evaluation_date: date | None = None,
        lookback_days: int = 30,
        failure_threshold_pct: float = DEFAULT_FAILURE_THRESHOLD_PCT,
    ) -> NightlyEvaluation:
        if evaluation_date is None:
            evaluation_date = date.today()

        period_end = evaluation_date - timedelta(days=1)
        period_start = period_end - timedelta(days=lookback_days)

        eval_record = NightlyEvaluation(
            evaluation_date=evaluation_date,
            period_start=period_start,
            period_end=period_end,
            status="running",
            failure_threshold_pct=failure_threshold_pct,
        )
        self.session.add(eval_record)
        await self.session.flush()

        horizon_configs = [
            (5, "signal_5d", "expected_return_5d", "probability_5d", "confidence_5d"),
            (10, "signal_10d", "expected_return_10d", "probability_10d", "confidence_10d"),
            (15, "signal_15d", "expected_return_15d", "probability_15d", "confidence_15d"),
            (20, "signal_20d", "expected_return_20d", "probability_20d", "confidence_20d"),
            (30, "signal_30d", "expected_return_30d", "probability_30d", "confidence_30d"),
        ]

        pred_r = await self.session.execute(
            select(Prediction).where(
                Prediction.as_of_date.between(period_start, period_end),
            )
        )
        predictions = list(pred_r.scalars().all())
        if not predictions:
            return await self._finalize_empty(eval_record, period_start, period_end)

        price_lookup = await self._bulk_load_prices(predictions, horizon_configs)

        errors: list[PredictionError] = []
        total_correct = 0
        total_count = 0
        all_abs_errors: list[float] = []
        all_errors: list[float] = []

        for pred in predictions:
            for horizon, signal_field, return_field, prob_field, conf_field in horizon_configs:
                signal = getattr(pred, signal_field, None)
                expected_return = getattr(pred, return_field, None)
                confidence = getattr(pred, conf_field, None)

                if signal is None or expected_return is None:
                    continue

                target_date = pred.as_of_date + timedelta(days=horizon)
                entry_price = price_lookup.get((pred.symbol, pred.as_of_date))
                actual_price = price_lookup.get((pred.symbol, target_date))

                if actual_price is None or entry_price is None or entry_price == 0:
                    continue

                actual_return_pct = round((actual_price - entry_price) / entry_price * 100, 2)
                error_pct = round(expected_return - actual_return_pct, 2)
                abs_error_pct = round(abs(error_pct), 2)
                actual_direction = self._direction_from_return(actual_return_pct)
                was_correct = signal == actual_direction

                is_failure = abs_error_pct > failure_threshold_pct

                pe = PredictionError(
                    evaluation_id=eval_record.id,
                    symbol=pred.symbol,
                    as_of_date=pred.as_of_date,
                    horizon=horizon,
                    signal=signal,
                    predicted_return_pct=expected_return,
                    actual_return_pct=actual_return_pct,
                    error_pct=error_pct,
                    abs_error_pct=abs_error_pct,
                    predicted_direction=signal,
                    actual_direction=actual_direction,
                    was_correct=was_correct,
                    is_failure=is_failure,
                    confidence=confidence,
                )
                errors.append(pe)

                total_count += 1
                if was_correct:
                    total_correct += 1
                all_abs_errors.append(abs_error_pct)
                all_errors.append(error_pct)

        for pe in errors:
            self.session.add(pe)
        await self.session.flush()

        accuracy = round(total_correct / total_count * 100, 2) if total_count else None
        mae = round(sum(all_abs_errors) / len(all_abs_errors), 2) if all_abs_errors else None
        rmse = round(math.sqrt(sum(e * e for e in all_errors) / len(all_errors)), 2) if all_errors else None
        bias_score = round(sum(all_errors) / len(all_errors), 2) if all_errors else None

        bias_direction = None
        if bias_score is not None:
            if bias_score > DEFAULT_BIAS_THRESHOLD:
                bias_direction = "overprediction"
            elif bias_score < -DEFAULT_BIAS_THRESHOLD:
                bias_direction = "underprediction"
            else:
                bias_direction = "none"

        failure_count = sum(1 for e in errors if e.is_failure)

        weight_adjustments = await self._compute_weight_adjustments(
            predictions, errors, period_start, period_end,
        )

        summary = self._build_summary(
            total_count, total_correct, accuracy, mae, rmse,
            bias_score, bias_direction, failure_count, errors,
            period_start, period_end,
        )

        eval_record.total_predictions = total_count
        eval_record.correct_predictions = total_correct
        eval_record.incorrect_predictions = total_count - total_correct
        eval_record.accuracy = accuracy
        eval_record.mae = mae
        eval_record.rmse = rmse
        eval_record.bias_score = bias_score
        eval_record.bias_direction = bias_direction
        eval_record.failure_count = failure_count
        eval_record.weight_adjustments_json = json.dumps(weight_adjustments, indent=2)
        eval_record.summary_json = json.dumps(summary, indent=2, default=str)
        eval_record.status = "completed"

        await self.session.flush()
        await self.session.refresh(eval_record)
        return eval_record

    async def get_evaluation(self, evaluation_id: int) -> NightlyEvaluation | None:
        r = await self.session.execute(
            select(NightlyEvaluation).where(NightlyEvaluation.id == evaluation_id)
        )
        return r.scalar_one_or_none()

    async def get_evaluations(
        self, limit: int = 20, offset: int = 0,
    ) -> list[NightlyEvaluation]:
        r = await self.session.execute(
            select(NightlyEvaluation)
            .order_by(desc(NightlyEvaluation.evaluation_date))
            .offset(offset).limit(limit)
        )
        return list(r.scalars().all())

    async def count_evaluations(self) -> int:
        r = await self.session.execute(select(func.count()).select_from(NightlyEvaluation))
        return r.scalar() or 0

    async def get_latest_evaluation(self) -> NightlyEvaluation | None:
        r = await self.session.execute(
            select(NightlyEvaluation)
            .where(NightlyEvaluation.status == "completed")
            .order_by(desc(NightlyEvaluation.evaluation_date))
            .limit(1)
        )
        return r.scalar_one_or_none()

    async def get_errors(
        self, evaluation_id: int,
        is_failure: bool | None = None,
        limit: int = 100, offset: int = 0,
    ) -> list[PredictionError]:
        q = select(PredictionError).where(PredictionError.evaluation_id == evaluation_id)
        if is_failure is not None:
            q = q.where(PredictionError.is_failure == is_failure)
        q = q.order_by(desc(PredictionError.abs_error_pct)).offset(offset).limit(limit)
        r = await self.session.execute(q)
        return list(r.scalars().all())

    async def count_errors(
        self, evaluation_id: int, is_failure: bool | None = None,
    ) -> int:
        q = select(func.count()).select_from(PredictionError).where(PredictionError.evaluation_id == evaluation_id)
        if is_failure is not None:
            q = q.where(PredictionError.is_failure == is_failure)
        return (await self.session.execute(q)).scalar() or 0

    async def get_failures(
        self, evaluation_id: int,
        limit: int = 100, offset: int = 0,
    ) -> list[PredictionError]:
        return await self.get_errors(evaluation_id, is_failure=True, limit=limit, offset=offset)

    async def get_trend(
        self, limit: int = 30,
    ) -> list[dict[str, Any]]:
        r = await self.session.execute(
            select(NightlyEvaluation)
            .where(NightlyEvaluation.status == "completed")
            .order_by(desc(NightlyEvaluation.evaluation_date))
            .limit(limit)
        )
        evals = list(r.scalars().all())
        return [
            {
                "id": e.id,
                "evaluation_date": e.evaluation_date.isoformat(),
                "accuracy": e.accuracy,
                "mae": e.mae,
                "rmse": e.rmse,
                "bias_score": e.bias_score,
                "bias_direction": e.bias_direction,
                "total_predictions": e.total_predictions,
                "failure_count": e.failure_count,
            }
            for e in reversed(evals)
        ]

    async def _bulk_load_prices(
        self, predictions: list[Prediction],
        horizon_configs: list[tuple[int, str, str, str, str]],
    ) -> dict[tuple[str, date], float]:
        symbols = set()
        date_needed: set[date] = set()
        for pred in predictions:
            symbols.add(pred.symbol)
            date_needed.add(pred.as_of_date)
            for horizon, *_ in horizon_configs:
                date_needed.add(pred.as_of_date + timedelta(days=horizon))

        all_dates = []
        cur = min(date_needed)
        end = max(date_needed)
        while cur <= end:
            all_dates.append(cur)
            cur += timedelta(days=1)

        if not symbols or not all_dates:
            return {}

        r = await self.session.execute(
            select(DailyPrice).where(
                DailyPrice.symbol.in_(list(symbols)),
                DailyPrice.trade_date.in_(all_dates),
            )
        )
        prices = list(r.scalars().all())

        lookup: dict[tuple[str, date], float] = {}
        for p in prices:
            key = (p.symbol, p.trade_date)
            if key not in lookup:
                lookup[key] = p.close
        return lookup

    async def _finalize_empty(
        self, eval_record: NightlyEvaluation,
        period_start: date, period_end: date,
    ) -> NightlyEvaluation:
        eval_record.status = "completed"
        summary = {
            "period": {"start": str(period_start), "end": str(period_end)},
            "total_evaluated": 0,
            "accuracy": None, "mae": None, "rmse": None,
            "bias": {"score": None, "direction": None},
            "failures": {"count": 0, "top_symbols": []},
            "signal_accuracy": {},
        }
        eval_record.summary_json = json.dumps(summary, indent=2, default=str)
        eval_record.weight_adjustments_json = json.dumps({
            "recommendation_summary": "No predictions to evaluate",
        }, indent=2)
        await self.session.flush()
        await self.session.refresh(eval_record)
        return eval_record

    async def _compute_weight_adjustments(
        self,
        predictions: list[Prediction],
        errors: list[PredictionError],
        period_start: date, period_end: date,
    ) -> dict[str, Any]:
        recommendations: dict[str, Any] = {}

        ensemble_symbols = set(e.symbol for e in errors)
        if ensemble_symbols:
            r = await self.session.execute(
                select(EnsemblePrediction).where(
                    EnsemblePrediction.symbol.in_(list(ensemble_symbols)),
                    EnsemblePrediction.as_of_date.between(period_start, period_end),
                )
            )
            ensembles = list(r.scalars().all())
            pillar_correctness: dict[str, list[bool]] = defaultdict(list)

            for ens in ensembles:
                pred_errs = [e for e in errors if e.symbol == ens.symbol and e.as_of_date == ens.as_of_date]
                if not pred_errs:
                    continue
                pe = pred_errs[0]

                for pillar_name, score_field, signal_field in PILLAR_FIELDS:
                    pillar_signal = getattr(ens, signal_field, None)
                    if pillar_signal is not None:
                        pillar_correctness[pillar_name].append(pillar_signal == pe.actual_direction)

            pillar_accuracies: dict[str, float] = {}
            for pname, outcomes in pillar_correctness.items():
                acc = sum(1 for o in outcomes if o) / len(outcomes) * 100 if outcomes else 0
                pillar_accuracies[pname] = round(acc, 1)

            latest_weights = await self._get_latest_weights()

            if latest_weights:
                weight_field_map = {
                    "technical": ("weight_technical", "dynamic_weight_technical"),
                    "fundamental": ("weight_fundamental", "dynamic_weight_fundamental"),
                    "sentiment": ("weight_sentiment", "dynamic_weight_sentiment"),
                    "momentum": ("weight_momentum", "dynamic_weight_momentum"),
                }
            else:
                weight_field_map = {
                    "technical": ("weight_technical", "dynamic_weight_technical"),
                    "fundamental": ("weight_fundamental", "dynamic_weight_fundamental"),
                    "news": ("weight_sentiment", "dynamic_weight_sentiment"),
                    "macro": ("weight_momentum", "dynamic_weight_momentum"),
                }

            adjustments = {}
            for pname, acc in pillar_accuracies.items():
                current_weight = latest_weights.get(pname, 0.25) if latest_weights else 0.25
                if acc > 60:
                    boost = round(min(0.10, (acc - 50) / 500), 2)
                    adjustments[pname] = {
                        "current_weight": current_weight,
                        "recommended_weight": round(min(0.50, current_weight + boost), 2),
                        "change": round(boost, 2),
                        "accuracy_pct": acc,
                        "reason": f"Pillar accuracy {acc}% exceeds baseline",
                    }
                elif acc < 40:
                    reduction = round(min(0.10, (50 - acc) / 500), 2)
                    adjustments[pname] = {
                        "current_weight": current_weight,
                        "recommended_weight": round(max(0.05, current_weight - reduction), 2),
                        "change": round(-reduction, 2),
                        "accuracy_pct": acc,
                        "reason": f"Pillar accuracy {acc}% below baseline",
                    }
                else:
                    adjustments[pname] = {
                        "current_weight": current_weight,
                        "recommended_weight": current_weight,
                        "change": 0.0,
                        "accuracy_pct": acc,
                        "reason": "Within acceptable range",
                    }

            recommendations["pillar_adjustments"] = adjustments

            by_horizon: dict[int, dict[str, Any]] = {}
            for horizon in sorted(set(e.horizon for e in errors)):
                horizon_errs = [e for e in errors if e.horizon == horizon]
                if not horizon_errs:
                    continue
                h_correct = sum(1 for e in horizon_errs if e.was_correct)
                h_total = len(horizon_errs)
                h_acc = round(h_correct / h_total * 100, 1) if h_total else 0
                h_mae = round(sum(e.abs_error_pct or 0 for e in horizon_errs) / h_total, 2)
                by_horizon[str(horizon) + "d"] = {
                    "accuracy": h_acc,
                    "mae": h_mae,
                    "total": h_total,
                }
            recommendations["by_horizon"] = by_horizon

        recommendations["failure_threshold_pct"] = DEFAULT_FAILURE_THRESHOLD_PCT
        recommendations["recommendation_summary"] = self._generate_recommendation_summary(recommendations)

        return recommendations

    async def _get_latest_weights(self) -> dict[str, float] | None:
        r = await self.session.execute(
            select(RankingModelWeight)
            .order_by(desc(RankingModelWeight.as_of_date))
            .limit(1)
        )
        w = r.scalar_one_or_none()
        if not w:
            return None
        return {
            "technical": w.weight_technical,
            "fundamental": w.weight_fundamental,
            "sentiment": w.weight_sentiment,
            "momentum": w.weight_momentum,
        }

    def _build_summary(
        self, total_count: int, total_correct: int,
        accuracy: float | None, mae: float | None, rmse: float | None,
        bias_score: float | None, bias_direction: str | None,
        failure_count: int, errors: list[PredictionError],
        period_start: date, period_end: date,
    ) -> dict[str, Any]:
        by_signal: dict[str, dict[str, int]] = {}
        for err in errors:
            sig = err.signal or "unknown"
            if sig not in by_signal:
                by_signal[sig] = {"total": 0, "correct": 0}
            by_signal[sig]["total"] += 1
            if err.was_correct:
                by_signal[sig]["correct"] += 1

        signal_accuracy = {}
        for sig, counts in by_signal.items():
            signal_accuracy[sig] = round(counts["correct"] / counts["total"] * 100, 1)

        failure_symbols: dict[str, int] = {}
        for err in errors:
            if err.is_failure:
                failure_symbols[err.symbol] = failure_symbols.get(err.symbol, 0) + 1
        top_failures = sorted(failure_symbols.items(), key=lambda x: -x[1])[:10]

        return {
            "period": {"start": str(period_start), "end": str(period_end)},
            "total_evaluated": total_count,
            "accuracy": accuracy,
            "mae": mae,
            "rmse": rmse,
            "bias": {"score": bias_score, "direction": bias_direction},
            "failures": {"count": failure_count, "top_symbols": top_failures},
            "signal_accuracy": signal_accuracy,
        }

    def _generate_recommendation_summary(self, recommendations: dict[str, Any]) -> str:
        parts = []
        adj = recommendations.get("pillar_adjustments", {})
        increases = [p for p, v in adj.items() if v.get("change", 0) > 0]
        decreases = [p for p, v in adj.items() if v.get("change", 0) < 0]
        if increases:
            parts.append(f"Increase weight on: {', '.join(increases)}")
        if decreases:
            parts.append(f"Decrease weight on: {', '.join(decreases)}")
        if not increases and not decreases:
            parts.append("No weight changes recommended")

        by_horizon = recommendations.get("by_horizon", {})
        best_horizon = max(by_horizon, key=lambda h: by_horizon[h]["accuracy"]) if by_horizon else None
        worst_horizon = min(by_horizon, key=lambda h: by_horizon[h]["accuracy"]) if by_horizon else None
        if best_horizon:
            parts.append(f"Best horizon: {best_horizon}")
        if worst_horizon:
            parts.append(f"Worst horizon: {worst_horizon}")

        return "; ".join(parts)

    @staticmethod
    def _direction_from_return(return_pct: float) -> str:
        if return_pct > 1.0:
            return "bullish"
        elif return_pct < -1.0:
            return "bearish"
        return "neutral"
