import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.models.model_evaluation import ModelEvaluation, ModelEvaluationMetric


@dataclass
class EvaluationResult:
    accuracy: float = 0.0
    precision: float = 0.0
    recall: float = 0.0
    f1: float = 0.0
    roc_auc: float = 0.0
    profitability: float = 0.0
    win_rate: float = 0.0
    max_drawdown: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return {
            "accuracy": self.accuracy,
            "precision": self.precision,
            "recall": self.recall,
            "f1": self.f1,
            "roc_auc": self.roc_auc,
            "profitability": self.profitability,
            "win_rate": self.win_rate,
            "max_drawdown": self.max_drawdown,
        }


class ModelEvaluationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── Metric Computation ──

    def compute_metrics(
        self,
        y_true: list[float],
        y_pred: list[float],
        y_prob: list[float] | None = None,
        returns: list[float] | None = None,
        threshold: float = 0.5,
    ) -> EvaluationResult:
        if not y_true or len(y_true) != len(y_pred):
            raise ValueError("y_true and y_pred must be non-empty and same length")

        n = len(y_true)
        tp = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p >= threshold)
        fp = sum(1 for t, p in zip(y_true, y_pred) if t == 0 and p >= threshold)
        fn = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p < threshold)
        tn = sum(1 for t, p in zip(y_true, y_pred) if t == 0 and p < threshold)

        accuracy = (tp + tn) / n if n > 0 else 0.0
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

        roc_auc = self._compute_roc_auc(y_true, y_prob) if y_prob else 0.0

        profitability = self._compute_profitability(returns) if returns else 0.0
        win_rate = self._compute_win_rate(returns) if returns else 0.0
        max_drawdown = self._compute_max_drawdown(returns) if returns else 0.0

        return EvaluationResult(
            accuracy=round(accuracy, 6),
            precision=round(precision, 6),
            recall=round(recall, 6),
            f1=round(f1, 6),
            roc_auc=round(roc_auc, 6),
            profitability=round(profitability, 6),
            win_rate=round(win_rate, 6),
            max_drawdown=round(max_drawdown, 6),
        )

    def _compute_roc_auc(self, y_true: list[float], y_prob: list[float]) -> float:
        if len(y_true) != len(y_prob) or len(y_true) < 2:
            return 0.0
        if len(set(y_true)) < 2:
            return 0.0

        n_pos = sum(y_true)
        n_neg = len(y_true) - n_pos
        if n_pos == 0 or n_neg == 0:
            return 0.0

        count = 0
        for i in range(len(y_true)):
            if y_true[i] == 1:
                for j in range(len(y_true)):
                    if y_true[j] == 0:
                        if y_prob[i] > y_prob[j]:
                            count += 1
                        elif y_prob[i] == y_prob[j]:
                            count += 0.5

        return count / (n_pos * n_neg)

    def _compute_profitability(self, returns: list[float]) -> float:
        if not returns:
            return 0.0
        total = sum(returns)
        return total / len(returns)

    def _compute_win_rate(self, returns: list[float]) -> float:
        if not returns:
            return 0.0
        wins = sum(1 for r in returns if r > 0)
        return wins / len(returns)

    def _compute_max_drawdown(self, returns: list[float]) -> float:
        if not returns:
            return 0.0
        cumulative = 0.0
        peak = 0.0
        max_dd = 0.0
        for r in returns:
            cumulative += r
            if cumulative > peak:
                peak = cumulative
            dd = (peak - cumulative) / peak if peak > 0 else 0.0
            if dd > max_dd:
                max_dd = dd
        return max_dd

    # ── Evaluation Runs ──

    async def run_evaluation(
        self,
        y_true: list[float],
        y_pred: list[float],
        y_prob: list[float] | None = None,
        returns: list[float] | None = None,
        threshold: float = 0.5,
        experiment_id: int | None = None,
        model_registry_entry_id: int | None = None,
        model_registry_version_id: int | None = None,
        name: str | None = None,
        dataset_name: str | None = None,
        notes: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ModelEvaluation:
        result = self.compute_metrics(
            y_true=y_true, y_pred=y_pred, y_prob=y_prob,
            returns=returns, threshold=threshold,
        )

        eval_record = ModelEvaluation(
            experiment_id=experiment_id,
            model_registry_entry_id=model_registry_entry_id,
            model_registry_version_id=model_registry_version_id,
            name=name,
            status="completed",
            dataset_name=dataset_name,
            num_samples=len(y_true),
            duration_seconds=0.0,
            notes=notes,
            metadata_json=json.dumps(metadata) if metadata else None,
            evaluated_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        self.session.add(eval_record)
        await self.session.flush()
        await self.session.refresh(eval_record)

        metrics_to_store = [
            ("accuracy", result.accuracy),
            ("precision", result.precision),
            ("recall", result.recall),
            ("f1", result.f1),
            ("roc_auc", result.roc_auc),
            ("profitability", result.profitability),
            ("win_rate", result.win_rate),
            ("max_drawdown", result.max_drawdown),
        ]
        for metric_name, metric_value in metrics_to_store:
            mem = ModelEvaluationMetric(
                evaluation_id=eval_record.id,
                metric_name=metric_name,
                metric_value=metric_value,
                config_json=json.dumps({"threshold": threshold}) if metric_name in ("accuracy", "precision", "recall", "f1") else None,
                details_json=json.dumps({
                    "y_true": y_true[:100],
                    "y_pred": y_pred[:100],
                }) if metric_name == "accuracy" else None,
            )
            self.session.add(mem)
        await self.session.flush()

        await self.session.refresh(eval_record)
        return eval_record

    async def get_evaluation(self, evaluation_id: int) -> ModelEvaluation | None:
        return await self.session.get(ModelEvaluation, evaluation_id)

    async def list_evaluations(
        self,
        model_registry_entry_id: int | None = None,
        experiment_id: int | None = None,
        status: str | None = None,
        limit: int = 50, offset: int = 0,
    ) -> list[ModelEvaluation]:
        q = select(ModelEvaluation)
        if model_registry_entry_id is not None:
            q = q.where(ModelEvaluation.model_registry_entry_id == model_registry_entry_id)
        if experiment_id is not None:
            q = q.where(ModelEvaluation.experiment_id == experiment_id)
        if status:
            q = q.where(ModelEvaluation.status == status)
        q = q.order_by(desc(ModelEvaluation.evaluated_at)).offset(offset).limit(limit)
        r = await self.session.execute(q)
        return list(r.scalars().all())

    async def get_evaluation_metrics(self, evaluation_id: int) -> list[ModelEvaluationMetric]:
        r = await self.session.execute(
            select(ModelEvaluationMetric)
            .where(ModelEvaluationMetric.evaluation_id == evaluation_id)
            .order_by(ModelEvaluationMetric.metric_name)
        )
        return list(r.scalars().all())

    async def get_metric_history(
        self,
        metric_name: str,
        model_registry_entry_id: int | None = None,
        experiment_id: int | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        q = (
            select(ModelEvaluation, ModelEvaluationMetric)
            .join(ModelEvaluationMetric, ModelEvaluation.id == ModelEvaluationMetric.evaluation_id)
            .where(ModelEvaluationMetric.metric_name == metric_name)
        )
        if model_registry_entry_id is not None:
            q = q.where(ModelEvaluation.model_registry_entry_id == model_registry_entry_id)
        if experiment_id is not None:
            q = q.where(ModelEvaluation.experiment_id == experiment_id)
        q = q.order_by(desc(ModelEvaluation.evaluated_at)).limit(limit)
        r = await self.session.execute(q)
        rows = r.all()
        return [
            {
                "evaluation_id": ev.id,
                "metric_name": met.metric_name,
                "metric_value": met.metric_value,
                "evaluated_at": ev.evaluated_at.isoformat() if ev.evaluated_at else None,
                "dataset_name": ev.dataset_name,
                "status": ev.status,
            }
            for ev, met in rows
        ]

    async def compare_evaluations(self, evaluation_ids: list[int]) -> dict[str, Any]:
        results: dict[str, Any] = {"evaluations": [], "metrics_comparison": {}}
        for eid in evaluation_ids:
            ev = await self.get_evaluation(eid)
            if not ev:
                continue
            metrics = await self.get_evaluation_metrics(eid)
            metric_map = {m.metric_name: m.metric_value for m in metrics}
            results["evaluations"].append({
                "id": ev.id, "name": ev.name,
                "dataset_name": ev.dataset_name,
                "num_samples": ev.num_samples,
                "evaluated_at": ev.evaluated_at.isoformat() if ev.evaluated_at else None,
                "metrics": metric_map,
            })

        if results["evaluations"]:
            all_metric_names = set()
            for ev_data in results["evaluations"]:
                all_metric_names.update(ev_data["metrics"].keys())
            for metric_name in sorted(all_metric_names):
                vals = [
                    (ev["id"], ev["metrics"].get(metric_name, None))
                    for ev in results["evaluations"]
                ]
                best_id = None
                best_val = None
                for eid, val in vals:
                    if val is not None:
                        if best_val is None or val > best_val:
                            best_val = val
                            best_id = eid
                results["metrics_comparison"][metric_name] = {
                    "values": {str(eid): val for eid, val in vals},
                    "best_evaluation_id": best_id,
                    "best_value": best_val,
                }

        return results
