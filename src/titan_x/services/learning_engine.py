import json
import math
from collections.abc import Sequence
from datetime import date, datetime, timedelta, timezone
from typing import Any

import structlog
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.db.repository import BaseRepository
from titan_x.models.ensemble import EnsemblePrediction
from titan_x.models.learning import LearningHistory, ModelWeight
from titan_x.models.prediction import Prediction
from titan_x.models.price import DailyPrice

logger = structlog.get_logger(__name__)

HORIZONS = [5, 10, 15, 20, 30]
SOURCE_NAMES = ["technical", "fundamental", "news", "macro", "risk", "pattern"]
DEFAULT_WEIGHTS: dict[str, float] = {
    "technical": 0.20, "fundamental": 0.20, "news": 0.15,
    "macro": 0.15, "risk": 0.15, "pattern": 0.15,
}
SIGNAL_DIRECTION: dict[str, int] = {
    "strong_buy": 1, "buy": 1, "bullish": 1,
    "hold": 0, "neutral": 0,
    "sell": -1, "bearish": -1, "strong_sell": -1,
}


class LearningEngine:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._history_repo = BaseRepository(session, LearningHistory)
        self._weight_repo = BaseRepository(session, ModelWeight)

    async def evaluate_prediction(self, prediction_id: int) -> dict[str, Any]:
        pred = await self._session.get(Prediction, prediction_id)
        if pred is None:
            raise ValueError(f"Prediction {prediction_id} not found")

        symbol = pred.symbol
        as_of = pred.as_of_date
        evaluated: list[dict[str, Any]] = []

        for horizon in HORIZONS:
            signal_col = f"signal_{horizon}d"
            ret_col = f"expected_return_{horizon}d"
            conf_col = f"confidence_{horizon}d"
            prob_col = f"probability_{horizon}d"

            pred_signal = getattr(pred, signal_col, None)
            pred_return = getattr(pred, ret_col, None)
            pred_conf = getattr(pred, conf_col, None)
            pred_prob = getattr(pred, prob_col, None)

            if pred_signal is None and pred_return is None:
                continue

            actual_return = await self._compute_actual_return(symbol, as_of, horizon)
            if actual_return is None:
                continue

            actual_signal = self._return_to_signal(actual_return)
            pred_dir = SIGNAL_DIRECTION.get(pred_signal or "hold", 0)
            actual_dir = SIGNAL_DIRECTION.get(actual_signal, 0)

            if pred_dir == 0 and actual_dir == 0:
                was_correct = True
            elif pred_dir == 0 or actual_dir == 0:
                was_correct = False
            else:
                was_correct = pred_dir == actual_dir

            abs_err = abs((pred_return or 0) - actual_return) if pred_return is not None else None
            sq_err = abs_err ** 2 if abs_err is not None else None

            data_sources = {}
            if pred.data_sources_json:
                try:
                    data_sources = json.loads(pred.data_sources_json)
                except (json.JSONDecodeError, TypeError):
                    data_sources = {}

            record = await self._history_repo.create(
                prediction_id=prediction_id,
                symbol=symbol,
                as_of_date=as_of,
                horizon_days=horizon,
                predicted_return_pct=pred_return,
                actual_return_pct=round(actual_return, 4),
                predicted_signal=pred_signal,
                actual_signal=actual_signal,
                predicted_direction=pred_dir,
                actual_direction=actual_dir,
                was_correct=was_correct,
                absolute_error=abs_err,
                squared_error=sq_err,
                predicted_confidence=pred_conf,
                data_sources_json=json.dumps(data_sources),
                evaluated_at=datetime.now(tz=timezone.utc),
            )

            evaluated.append({
                "id": record.id,
                "horizon": horizon,
                "predicted_return": pred_return,
                "actual_return": round(actual_return, 4),
                "predicted_signal": pred_signal,
                "actual_signal": actual_signal,
                "was_correct": was_correct,
                "absolute_error": abs_err,
            })

        return {"prediction_id": prediction_id, "symbol": symbol, "results": evaluated}

    async def evaluate_outdated_predictions(
        self, max_records: int = 50,
    ) -> list[dict[str, Any]]:
        today = date.today()
        results: list[dict[str, Any]] = []

        for horizon in HORIZONS:
            cutoff = today - timedelta(days=horizon + 1)
            already = select(LearningHistory.prediction_id).where(
                LearningHistory.horizon_days == horizon,
            )
            query = (
                select(Prediction)
                .where(
                    Prediction.as_of_date <= cutoff,
                    Prediction.id.notin_(already),
                )
                .order_by(desc(Prediction.as_of_date))
                .limit(max_records // len(HORIZONS))
            )
            rows = (await self._session.execute(query)).scalars().all()

            for pred in rows:
                try:
                    result = await self.evaluate_prediction(pred.id)
                    results.append(result)
                except Exception as exc:
                    logger.warning("eval_failed", prediction_id=pred.id, error=str(exc))

        return results

    async def compute_summary(
        self, symbol: str | None = None, horizon_days: int | None = None,
    ) -> dict[str, Any]:
        query = select(LearningHistory)
        count_query = select(func.count()).select_from(LearningHistory)
        if symbol:
            query = query.where(LearningHistory.symbol == symbol)
            count_query = count_query.where(LearningHistory.symbol == symbol)
        if horizon_days:
            query = query.where(LearningHistory.horizon_days == horizon_days)
            count_query = count_query.where(LearningHistory.horizon_days == horizon_days)

        rows = (await self._session.execute(query)).scalars().all()

        total = len(rows)
        if total == 0:
            return {"total": 0, "accuracy": 0, "precision_bullish": 0, "recall_bullish": 0, "precision_bearish": 0, "recall_bearish": 0, "avg_abs_error": 0, "profitability": 0}

        correct = sum(1 for r in rows if r.was_correct)
        accuracy = correct / total * 100

        tp_bullish = sum(1 for r in rows if r.predicted_direction == 1 and r.actual_direction == 1)
        fp_bullish = sum(1 for r in rows if r.predicted_direction == 1 and r.actual_direction != 1)
        fn_bullish = sum(1 for r in rows if r.predicted_direction != 1 and r.actual_direction == 1)
        prec_bullish = tp_bullish / (tp_bullish + fp_bullish) * 100 if (tp_bullish + fp_bullish) > 0 else 0
        rec_bullish = tp_bullish / (tp_bullish + fn_bullish) * 100 if (tp_bullish + fn_bullish) > 0 else 0

        tp_bearish = sum(1 for r in rows if r.predicted_direction == -1 and r.actual_direction == -1)
        fp_bearish = sum(1 for r in rows if r.predicted_direction == -1 and r.actual_direction != -1)
        fn_bearish = sum(1 for r in rows if r.predicted_direction != -1 and r.actual_direction == -1)
        prec_bearish = tp_bearish / (tp_bearish + fp_bearish) * 100 if (tp_bearish + fp_bearish) > 0 else 0
        rec_bearish = tp_bearish / (tp_bearish + fn_bearish) * 100 if (tp_bearish + fn_bearish) > 0 else 0

        abs_errors = [r.absolute_error for r in rows if r.absolute_error is not None]
        avg_abs_error = sum(abs_errors) / len(abs_errors) if abs_errors else 0

        profitability = self._compute_profitability(rows)

        return {
            "total": total,
            "correct": correct,
            "accuracy": round(accuracy, 2),
            "precision_bullish": round(prec_bullish, 2),
            "recall_bullish": round(rec_bullish, 2),
            "precision_bearish": round(prec_bearish, 2),
            "recall_bearish": round(rec_bearish, 2),
            "avg_absolute_error": round(avg_abs_error, 4),
            "profitability": round(profitability, 4),
        }

    async def update_source_weights(
        self, source_name: str,
    ) -> dict[str, Any]:
        records = (
            await self._session.execute(
                select(LearningHistory)
                .where(LearningHistory.data_sources_json.contains(source_name))
                .order_by(desc(LearningHistory.evaluated_at))
                .limit(200)
            )
        ).scalars().all()

        total = len(records)
        if total == 0:
            return {"source": source_name, "total": 0, "weight": 0, "message": "no data"}

        correct = sum(1 for r in records if r.was_correct)
        accuracy = correct / total

        tp_bullish = sum(1 for r in records if r.predicted_direction == 1 and r.actual_direction == 1)
        fp_bullish = sum(1 for r in records if r.predicted_direction == 1 and r.actual_direction != 1)
        fn_bullish = sum(1 for r in records if r.predicted_direction != 1 and r.actual_direction == 1)
        prec_bullish = tp_bullish / (tp_bullish + fp_bullish) if (tp_bullish + fp_bullish) > 0 else 0
        rec_bullish = tp_bullish / (tp_bullish + fn_bullish) if (tp_bullish + fn_bullish) > 0 else 0

        tp_bearish = sum(1 for r in records if r.predicted_direction == -1 and r.actual_direction == -1)
        fp_bearish = sum(1 for r in records if r.predicted_direction == -1 and r.actual_direction != -1)
        fn_bearish = sum(1 for r in records if r.predicted_direction != -1 and r.actual_direction == -1)
        prec_bearish = tp_bearish / (tp_bearish + fp_bearish) if (tp_bearish + fp_bearish) > 0 else 0
        rec_bearish = tp_bearish / (tp_bearish + fn_bearish) if (tp_bearish + fn_bearish) > 0 else 0

        returns_when_correct = [
            r.actual_return_pct for r in records
            if r.was_correct and r.actual_return_pct is not None and r.actual_return_pct != 0
        ]
        returns_when_wrong = [
            r.actual_return_pct for r in records
            if not r.was_correct and r.actual_return_pct is not None and r.actual_return_pct != 0
        ]

        avg_correct = sum(returns_when_correct) / len(returns_when_correct) if returns_when_correct else 0
        avg_wrong = sum(returns_when_wrong) / len(returns_when_wrong) if returns_when_wrong else 0

        base_weight = DEFAULT_WEIGHTS.get(source_name, 0.15)
        new_weight = base_weight * (accuracy / 0.5)
        new_weight = max(0.05, min(0.50, new_weight))

        existing = await self._find_weight(source_name)
        if existing:
            existing.weight = round(new_weight, 4)
            existing.accuracy = round(accuracy, 4)
            existing.precision_bullish = round(prec_bullish, 4)
            existing.recall_bullish = round(rec_bullish, 4)
            existing.precision_bearish = round(prec_bearish, 4)
            existing.recall_bearish = round(rec_bearish, 4)
            existing.total_predictions = total
            existing.correct_predictions = correct
            existing.avg_return_when_correct = round(avg_correct, 4)
            existing.avg_return_when_wrong = round(avg_wrong, 4)
            existing.last_updated = datetime.now(tz=timezone.utc)
        else:
            await self._weight_repo.create(
                source_name=source_name,
                weight=round(new_weight, 4),
                accuracy=round(accuracy, 4),
                precision_bullish=round(prec_bullish, 4),
                recall_bullish=round(rec_bullish, 4),
                precision_bearish=round(prec_bearish, 4),
                recall_bearish=round(rec_bearish, 4),
                total_predictions=total,
                correct_predictions=correct,
                avg_return_when_correct=round(avg_correct, 4),
                avg_return_when_wrong=round(avg_wrong, 4),
            )

        await self._session.flush()
        return {
            "source": source_name,
            "total": total,
            "correct": correct,
            "accuracy": round(accuracy * 100, 2),
            "new_weight": round(new_weight, 4),
        }

    async def update_all_weights(self) -> dict[str, Any]:
        results: dict[str, Any] = {}
        for source in SOURCE_NAMES:
            try:
                result = await self.update_source_weights(source)
                results[source] = result
            except Exception as exc:
                logger.warning("weight_update_failed", source=source, error=str(exc))
                results[source] = {"error": str(exc)}

        weights = await self.normalize_weights()
        results["normalized_weights"] = weights
        return results

    async def normalize_weights(self) -> dict[str, float]:
        rows = (await self._session.execute(
            select(ModelWeight).where(ModelWeight.symbol.is_(None))
        )).scalars().all()

        if not rows:
            return dict(DEFAULT_WEIGHTS)

        total_weight = sum(r.weight for r in rows)
        if total_weight <= 0:
            return dict(DEFAULT_WEIGHTS)

        ratio = 1.0 / total_weight
        for r in rows:
            r.weight = round(r.weight * ratio, 4)
        await self._session.flush()

        return {r.source_name: r.weight for r in rows}

    async def get_weights(
        self, source_name: str | None = None,
    ) -> list[dict[str, Any]]:
        query = select(ModelWeight).order_by(ModelWeight.source_name)
        if source_name:
            query = query.where(ModelWeight.source_name == source_name)
        rows = (await self._session.execute(query)).scalars().all()
        return [
            {
                "id": r.id,
                "source_name": r.source_name,
                "symbol": r.symbol,
                "weight": r.weight,
                "accuracy": r.accuracy,
                "precision_bullish": r.precision_bullish,
                "recall_bullish": r.recall_bullish,
                "precision_bearish": r.precision_bearish,
                "recall_bearish": r.recall_bearish,
                "total_predictions": r.total_predictions,
                "correct_predictions": r.correct_predictions,
                "avg_return_when_correct": r.avg_return_when_correct,
                "avg_return_when_wrong": r.avg_return_when_wrong,
                "last_updated": r.last_updated.isoformat() if r.last_updated else None,
            }
            for r in rows
        ]

    async def get_history(
        self, symbol: str | None = None, horizon_days: int | None = None,
        was_correct: bool | None = None, skip: int = 0, limit: int = 100,
    ) -> tuple[Sequence[LearningHistory], int]:
        query = select(LearningHistory).order_by(desc(LearningHistory.evaluated_at))
        count_query = select(func.count()).select_from(LearningHistory)
        if symbol:
            query = query.where(LearningHistory.symbol == symbol)
            count_query = count_query.where(LearningHistory.symbol == symbol)
        if horizon_days:
            query = query.where(LearningHistory.horizon_days == horizon_days)
            count_query = count_query.where(LearningHistory.horizon_days == horizon_days)
        if was_correct is not None:
            query = query.where(LearningHistory.was_correct == was_correct)
            count_query = count_query.where(LearningHistory.was_correct == was_correct)
        total = (await self._session.execute(count_query)).scalar() or 0
        query = query.offset(skip).limit(limit)
        rows = (await self._session.execute(query)).scalars().all()
        return rows, total

    async def get_history_record(self, record_id: int) -> dict[str, Any] | None:
        record = await self._history_repo.get(record_id)
        if record is None:
            return None
        return {
            "id": record.id,
            "prediction_id": record.prediction_id,
            "symbol": record.symbol,
            "as_of_date": record.as_of_date.isoformat() if record.as_of_date else None,
            "horizon_days": record.horizon_days,
            "predicted_return_pct": record.predicted_return_pct,
            "actual_return_pct": record.actual_return_pct,
            "predicted_signal": record.predicted_signal,
            "actual_signal": record.actual_signal,
            "predicted_direction": record.predicted_direction,
            "actual_direction": record.actual_direction,
            "was_correct": record.was_correct,
            "absolute_error": record.absolute_error,
            "squared_error": record.squared_error,
            "predicted_confidence": record.predicted_confidence,
            "data_sources_json": record.data_sources_json,
            "evaluated_at": record.evaluated_at.isoformat() if record.evaluated_at else None,
        }

    async def delete_history(self, record_id: int) -> bool:
        return await self._history_repo.delete(record_id)

    async def _compute_actual_return(self, symbol: str, as_of_date: date, horizon: int) -> float | None:
        start = as_of_date
        end = as_of_date + timedelta(days=horizon)

        rows = (await self._session.execute(
            select(DailyPrice)
            .where(
                DailyPrice.symbol == symbol.upper(),
                DailyPrice.trade_date.between(start, end),
            )
            .order_by(DailyPrice.trade_date)
        )).scalars().all()

        if len(rows) < 2:
            return None

        start_price = rows[0].close
        end_price = rows[-1].close
        if not start_price or not end_price or start_price == 0:
            return None

        return (end_price - start_price) / start_price * 100

    def _return_to_signal(self, return_pct: float) -> str:
        if return_pct > 2:
            return "bullish"
        elif return_pct < -2:
            return "bearish"
        return "neutral"

    def _compute_profitability(self, records: Sequence[LearningHistory]) -> float:
        total_return = 0.0
        count = 0
        for r in records:
            if r.actual_return_pct is None:
                continue
            if r.predicted_signal in ("strong_buy", "buy", "bullish"):
                total_return += r.actual_return_pct
                count += 1
            elif r.predicted_signal in ("strong_sell", "sell", "bearish"):
                total_return += -r.actual_return_pct
                count += 1
        return total_return / count if count > 0 else 0.0

    async def _find_weight(self, source_name: str) -> ModelWeight | None:
        result = await self._session.execute(
            select(ModelWeight).where(
                ModelWeight.source_name == source_name,
                ModelWeight.symbol.is_(None),
            )
        )
        return result.scalar_one_or_none()
