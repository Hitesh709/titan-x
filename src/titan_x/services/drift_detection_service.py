import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.models.drift_detection import (
    ConceptDriftResult,
    DistributionProfile,
    DriftAlert,
    DriftDetectionRun,
    FeatureDriftResult,
)

PSI_THRESHOLD = 0.2
JS_THRESHOLD = 0.1
CONCEPT_DRIFT_PCT_THRESHOLD = 0.1


@dataclass
class FeatureDriftInfo:
    feature_name: str
    drift_score: float
    p_value: float | None
    drifted: bool
    drift_type: str
    baseline_stats: dict[str, Any]
    current_stats: dict[str, Any]


@dataclass
class ConceptDriftInfo:
    metric_name: str
    baseline_value: float
    current_value: float
    percentage_change: float
    drifted: bool


class DriftDetectionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── Distribution Profiling ──

    async def create_distribution_profile(
        self,
        feature_name: str,
        values: list[float],
        model_registry_entry_id: int | None = None,
        profile_type: str = "baseline",
        dataset_name: str | None = None,
    ) -> DistributionProfile:
        stats = self._compute_stats(values)
        hist = self._compute_histogram(values)
        dp = DistributionProfile(
            model_registry_entry_id=model_registry_entry_id,
            feature_name=feature_name,
            profile_type=profile_type,
            dataset_name=dataset_name,
            num_samples=stats["count"],
            mean=stats["mean"], std=stats["std"],
            minimum=stats["min"], maximum=stats["max"],
            median=stats["median"], p25=stats["p25"], p75=stats["p75"],
            histogram_json=json.dumps(hist),
        )
        self.session.add(dp)
        await self.session.flush()
        await self.session.refresh(dp)
        return dp

    async def get_distribution_profile(
        self, profile_id: int,
    ) -> DistributionProfile | None:
        return await self.session.get(DistributionProfile, profile_id)

    async def get_baseline_profiles(
        self, model_registry_entry_id: int,
    ) -> list[DistributionProfile]:
        r = await self.session.execute(
            select(DistributionProfile).where(
                DistributionProfile.model_registry_entry_id == model_registry_entry_id,
                DistributionProfile.profile_type == "baseline",
            )
        )
        return list(r.scalars().all())

    # ── Drift Detection Run ──

    async def run_drift_detection(
        self,
        baseline_data: dict[str, list[float]],
        current_data: dict[str, list[float]],
        baseline_metrics: dict[str, float] | None = None,
        current_metrics: dict[str, float] | None = None,
        model_registry_entry_id: int | None = None,
        model_registry_version_id: int | None = None,
        name: str | None = None,
        baseline_dataset: str | None = None,
        current_dataset: str | None = None,
        psi_threshold: float = PSI_THRESHOLD,
        js_threshold: float = JS_THRESHOLD,
        concept_drift_threshold: float = CONCEPT_DRIFT_PCT_THRESHOLD,
        alert_on_drift: bool = True,
    ) -> DriftDetectionRun:
        started_at = datetime.now(timezone.utc).replace(tzinfo=None)
        all_features = set(baseline_data.keys()) & set(current_data.keys())

        run = DriftDetectionRun(
            model_registry_entry_id=model_registry_entry_id,
            model_registry_version_id=model_registry_version_id,
            name=name,
            status="running",
            baseline_dataset=baseline_dataset,
            current_dataset=current_dataset,
            num_features_compared=len(all_features),
            ran_at=started_at,
        )
        self.session.add(run)
        await self.session.flush()
        await self.session.refresh(run)

        feature_results: list[FeatureDriftResult] = []
        num_drifted = 0
        total_drift_score = 0.0

        for feature_name in sorted(all_features):
            base_vals = baseline_data[feature_name]
            curr_vals = current_data[feature_name]

            psi = self._compute_psi(base_vals, curr_vals)
            js = self._compute_js_divergence(base_vals, curr_vals)
            base_stats = self._compute_stats(base_vals)
            curr_stats = self._compute_stats(curr_vals)

            drift_score = max(psi, js)
            drift_type = "psi" if psi >= js else "js_divergence"
            drifted = drift_score > (psi_threshold if drift_type == "psi" else js_threshold)

            if drifted:
                num_drifted += 1
            total_drift_score += drift_score

            result = FeatureDriftResult(
                run_id=run.id,
                feature_name=feature_name,
                drift_type=drift_type,
                drift_score=round(drift_score, 6),
                p_value=None,
                drifted=drifted,
                threshold=psi_threshold if drift_type == "psi" else js_threshold,
                baseline_mean=base_stats["mean"],
                baseline_std=base_stats["std"],
                baseline_count=base_stats["count"],
                current_mean=curr_stats["mean"],
                current_std=curr_stats["std"],
                current_count=curr_stats["count"],
            )
            self.session.add(result)
            feature_results.append(result)

        concept_results: list[ConceptDriftResult] = []
        if baseline_metrics and current_metrics:
            for metric_name in baseline_metrics:
                base_val = baseline_metrics[metric_name]
                curr_val = current_metrics.get(metric_name)
                if curr_val is None:
                    continue
                abs_change = curr_val - base_val
                pct_change = abs_change / base_val if base_val != 0 else 0.0
                drifted = abs(pct_change) > concept_drift_threshold

                cr = ConceptDriftResult(
                    run_id=run.id,
                    metric_name=metric_name,
                    baseline_value=base_val,
                    current_value=curr_val,
                    absolute_change=round(abs_change, 6),
                    percentage_change=round(pct_change, 6),
                    drifted=drifted,
                    threshold=concept_drift_threshold,
                )
                self.session.add(cr)
                concept_results.append(cr)

        overall_score = (total_drift_score / len(all_features)) if all_features else 0.0
        drift_detected = num_drifted > 0 or any(cr.drifted for cr in concept_results)

        run.status = "completed"
        run.drift_detected = drift_detected
        run.overall_drift_score = round(overall_score, 6)
        run.num_drifted_features = num_drifted
        completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        run.duration_seconds = (completed_at - started_at).total_seconds()

        if alert_on_drift and drift_detected:
            await self._generate_alerts(run, feature_results, concept_results)

        await self.session.flush()
        await self.session.refresh(run)
        return run

    async def _generate_alerts(
        self, run: DriftDetectionRun,
        feature_results: list[FeatureDriftResult],
        concept_results: list[ConceptDriftResult],
    ) -> None:
        for fr in feature_results:
            if fr.drifted:
                severity = self._severity_from_score(fr.drift_score)
                alert = DriftAlert(
                    run_id=run.id,
                    alert_type="feature_drift",
                    feature_name=fr.feature_name,
                    severity=severity,
                    message=(
                        f"Feature '{fr.feature_name}' drifted ({fr.drift_type}={fr.drift_score:.4f}, "
                        f"threshold={fr.threshold})"
                    ),
                    drift_score=fr.drift_score,
                    threshold=fr.threshold,
                )
                self.session.add(alert)

        for cr in concept_results:
            if cr.drifted:
                severity = self._severity_from_score(abs(cr.percentage_change))
                alert = DriftAlert(
                    run_id=run.id,
                    alert_type="concept_drift",
                    severity=severity,
                    message=(
                        f"Concept drift detected: '{cr.metric_name}' changed "
                        f"by {cr.percentage_change*100:.1f}% "
                        f"({cr.baseline_value:.4f} -> {cr.current_value:.4f})"
                    ),
                    drift_score=abs(cr.percentage_change),
                    threshold=cr.threshold,
                )
                self.session.add(alert)

        if run.overall_drift_score and run.overall_drift_score > 0.3:
            alert = DriftAlert(
                run_id=run.id,
                alert_type="data_drift",
                severity="high",
                message=(
                    f"Overall data drift detected: score={run.overall_drift_score:.4f}, "
                    f"{run.num_drifted_features}/{run.num_features_compared} features drifted"
                ),
                drift_score=run.overall_drift_score,
            )
            self.session.add(alert)

    def _severity_from_score(self, score: float) -> str:
        if score > 0.5:
            return "critical"
        if score > 0.3:
            return "high"
        if score > 0.2:
            return "medium"
        return "low"

    # ── Distribution Monitoring ──

    async def monitor_distributions(
        self,
        features: dict[str, list[float]],
        model_registry_entry_id: int,
        dataset_name: str | None = None,
    ) -> list[DistributionProfile]:
        profiles: list[DistributionProfile] = []
        for feature_name, values in features.items():
            dp = await self.create_distribution_profile(
                feature_name=feature_name, values=values,
                model_registry_entry_id=model_registry_entry_id,
                profile_type="monitoring",
                dataset_name=dataset_name,
            )
            profiles.append(dp)
        return profiles

    # ── Statistical Methods ──

    def _compute_stats(self, values: list[float]) -> dict[str, Any]:
        n = len(values)
        if n == 0:
            return {"count": 0, "mean": 0, "std": 0, "min": 0, "max": 0, "median": 0, "p25": 0, "p75": 0}

        mean = sum(values) / n
        variance = sum((x - mean) ** 2 for x in values) / n
        std = math.sqrt(variance)
        sorted_vals = sorted(values)
        min_v = sorted_vals[0]
        max_v = sorted_vals[-1]

        def percentile(p: float) -> float:
            k = (n - 1) * p
            f = math.floor(k)
            c = math.ceil(k)
            if f == c:
                return sorted_vals[int(k)]
            d0 = sorted_vals[f] * (c - k)
            d1 = sorted_vals[c] * (k - f)
            return d0 + d1

        return {
            "count": n,
            "mean": mean,
            "std": std,
            "min": min_v,
            "max": max_v,
            "median": percentile(0.5),
            "p25": percentile(0.25),
            "p75": percentile(0.75),
        }

    def _compute_histogram(self, values: list[float], num_bins: int = 10) -> dict[str, Any]:
        if not values:
            return {"bins": [], "counts": []}
        min_v = min(values)
        max_v = max(values)
        if min_v == max_v:
            return {"bins": [min_v], "counts": [len(values)]}
        bin_width = (max_v - min_v) / num_bins
        bins = [min_v + i * bin_width for i in range(num_bins + 1)]
        counts = [0] * num_bins
        for v in values:
            idx = min(int((v - min_v) / bin_width), num_bins - 1)
            counts[idx] += 1
        return {"bins": bins, "counts": counts}

    def _compute_psi(self, baseline: list[float], current: list[float], num_bins: int = 10) -> float:
        if not baseline or not current:
            return 0.0

        all_vals = baseline + current
        min_v = min(all_vals)
        max_v = max(all_vals)
        if min_v == max_v:
            return 0.0

        bin_width = (max_v - min_v) / num_bins
        bins = [min_v + i * bin_width for i in range(num_bins + 1)]
        base_counts = [0] * num_bins
        curr_counts = [0] * num_bins

        for v in baseline:
            idx = min(int((v - min_v) / bin_width), num_bins - 1)
            base_counts[idx] += 1
        for v in current:
            idx = min(int((v - min_v) / bin_width), num_bins - 1)
            curr_counts[idx] += 1

        base_total = len(baseline)
        curr_total = len(current)

        psi = 0.0
        for i in range(num_bins):
            p_i = base_counts[i] / base_total
            q_i = curr_counts[i] / curr_total
            p_i = max(p_i, 0.0001)
            q_i = max(q_i, 0.0001)
            psi += (p_i - q_i) * math.log(p_i / q_i)

        return psi

    def _compute_js_divergence(self, p_values: list[float], q_values: list[float], num_bins: int = 10) -> float:
        if not p_values or not q_values:
            return 0.0

        all_vals = p_values + q_values
        min_v = min(all_vals)
        max_v = max(all_vals)
        if min_v == max_v:
            return 0.0

        bin_width = (max_v - min_v) / num_bins
        bins = [min_v + i * bin_width for i in range(num_bins + 1)]
        p_counts = [0] * num_bins
        q_counts = [0] * num_bins

        for v in p_values:
            idx = min(int((v - min_v) / bin_width), num_bins - 1)
            p_counts[idx] += 1
        for v in q_values:
            idx = min(int((v - min_v) / bin_width), num_bins - 1)
            q_counts[idx] += 1

        p_total = len(p_values)
        q_total = len(q_values)

        p_probs = [max(c / p_total, 0.0001) for c in p_counts]
        q_probs = [max(c / q_total, 0.0001) for c in q_counts]

        m_probs = [(p + q) / 2 for p, q in zip(p_probs, q_probs)]

        kl_pm = sum(p * math.log(p / m) for p, m in zip(p_probs, m_probs))
        kl_qm = sum(q * math.log(q / m) for q, m in zip(q_probs, m_probs))

        return (kl_pm + kl_qm) / 2

    # ── Query Methods ──

    async def get_run(self, run_id: int) -> DriftDetectionRun | None:
        return await self.session.get(DriftDetectionRun, run_id)

    async def list_runs(
        self, model_registry_entry_id: int | None = None,
        drift_detected: bool | None = None,
        limit: int = 50, offset: int = 0,
    ) -> list[DriftDetectionRun]:
        q = select(DriftDetectionRun)
        if model_registry_entry_id is not None:
            q = q.where(DriftDetectionRun.model_registry_entry_id == model_registry_entry_id)
        if drift_detected is not None:
            q = q.where(DriftDetectionRun.drift_detected == drift_detected)
        q = q.order_by(desc(DriftDetectionRun.ran_at)).offset(offset).limit(limit)
        r = await self.session.execute(q)
        return list(r.scalars().all())

    async def count_runs(
        self, model_registry_entry_id: int | None = None,
        drift_detected: bool | None = None,
    ) -> int:
        q = select(func.count()).select_from(DriftDetectionRun)
        if model_registry_entry_id is not None:
            q = q.where(DriftDetectionRun.model_registry_entry_id == model_registry_entry_id)
        if drift_detected is not None:
            q = q.where(DriftDetectionRun.drift_detected == drift_detected)
        return (await self.session.execute(q)).scalar() or 0

    async def get_feature_drift_results(self, run_id: int) -> list[FeatureDriftResult]:
        r = await self.session.execute(
            select(FeatureDriftResult)
            .where(FeatureDriftResult.run_id == run_id)
            .order_by(desc(FeatureDriftResult.drift_score))
        )
        return list(r.scalars().all())

    async def get_concept_drift_results(self, run_id: int) -> list[ConceptDriftResult]:
        r = await self.session.execute(
            select(ConceptDriftResult)
            .where(ConceptDriftResult.run_id == run_id)
            .order_by(ConceptDriftResult.metric_name)
        )
        return list(r.scalars().all())

    async def get_alerts(
        self, acknowledged: bool | None = None,
        severity: str | None = None,
        limit: int = 50, offset: int = 0,
    ) -> list[DriftAlert]:
        q = select(DriftAlert)
        if acknowledged is not None:
            q = q.where(DriftAlert.acknowledged == acknowledged)
        if severity is not None:
            q = q.where(DriftAlert.severity == severity)
        q = q.order_by(desc(DriftAlert.created_at)).offset(offset).limit(limit)
        r = await self.session.execute(q)
        return list(r.scalars().all())

    async def count_alerts(
        self, acknowledged: bool | None = None,
        severity: str | None = None,
    ) -> int:
        q = select(func.count()).select_from(DriftAlert)
        if acknowledged is not None:
            q = q.where(DriftAlert.acknowledged == acknowledged)
        if severity is not None:
            q = q.where(DriftAlert.severity == severity)
        return (await self.session.execute(q)).scalar() or 0

    async def acknowledge_alert(self, alert_id: int) -> DriftAlert | None:
        alert = await self.session.get(DriftAlert, alert_id)
        if not alert:
            return None
        alert.acknowledged = True
        alert.acknowledged_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await self.session.flush()
        await self.session.refresh(alert)
        return alert

    async def get_run_summary(self, run_id: int) -> dict[str, Any] | None:
        run = await self.get_run(run_id)
        if not run:
            return None
        feature_results = await self.get_feature_drift_results(run_id)
        concept_results = await self.get_concept_drift_results(run_id)
        return {
            "run": {
                "id": run.id, "name": run.name, "status": run.status,
                "drift_detected": run.drift_detected,
                "overall_drift_score": run.overall_drift_score,
                "num_features_compared": run.num_features_compared,
                "num_drifted_features": run.num_drifted_features,
                "baseline_dataset": run.baseline_dataset,
                "current_dataset": run.current_dataset,
                "duration_seconds": run.duration_seconds,
                "ran_at": run.ran_at.isoformat() if run.ran_at else None,
            },
            "feature_drift": [
                {
                    "feature_name": f.feature_name, "drift_score": f.drift_score,
                    "drift_type": f.drift_type, "drifted": f.drifted,
                    "threshold": f.threshold,
                    "baseline_mean": f.baseline_mean, "current_mean": f.current_mean,
                }
                for f in feature_results
            ],
            "concept_drift": [
                {
                    "metric_name": c.metric_name,
                    "baseline_value": c.baseline_value, "current_value": c.current_value,
                    "percentage_change": c.percentage_change, "drifted": c.drifted,
                }
                for c in concept_results
            ],
        }
