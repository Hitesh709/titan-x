from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from titan_x.api import deps
from titan_x.models.user import User
from titan_x.api.schemas import PaginatedResponse
from titan_x.services.drift_detection_service import DriftDetectionService

router = APIRouter(tags=["drift-detection"])


# ── Distribution Profiles ──

@router.post("/distribution-profiles", status_code=201)
async def create_distribution_profile(
    feature_name: str = Query(...),
    values: str = Query(...),
    model_registry_entry_id: int | None = None,
    profile_type: str = "baseline",
    dataset_name: str | None = None,
    session=Depends(deps.get_session),
    _=Depends(deps.get_current_active_superuser),
):
    svc = DriftDetectionService(session)
    dp = await svc.create_distribution_profile(
        feature_name=feature_name,
        values=_parse_float_list(values),
        model_registry_entry_id=model_registry_entry_id,
        profile_type=profile_type,
        dataset_name=dataset_name,
    )
    return {
        "id": dp.id, "feature_name": dp.feature_name,
        "profile_type": dp.profile_type, "num_samples": dp.num_samples,
    }


@router.get("/distribution-profiles/baseline/{model_entry_id}")
async def get_baseline_profiles(
    model_entry_id: int,
    session=Depends(deps.get_session),
    _=Depends(deps.get_current_active_superuser),
):
    svc = DriftDetectionService(session)
    items = await svc.get_baseline_profiles(model_entry_id)
    return {"profiles": [_profile_dict(p) for p in items]}


# ── Drift Detection Run ──

@router.post("/drift-detection/run", status_code=201)
async def run_drift_detection(
    baseline_data: str = Query(...),
    current_data: str = Query(...),
    baseline_metrics: str | None = None,
    current_metrics: str | None = None,
    model_registry_entry_id: int | None = None,
    name: str | None = None,
    baseline_dataset: str | None = None,
    current_dataset: str | None = None,
    psi_threshold: float = 0.2,
    js_threshold: float = 0.1,
    concept_drift_threshold: float = 0.1,
    alert_on_drift: bool = True,
    session=Depends(deps.get_session),
    _=Depends(deps.get_current_active_superuser),
):
    svc = DriftDetectionService(session)
    run = await svc.run_drift_detection(
        baseline_data=_parse_json_dict_float_lists(baseline_data),
        current_data=_parse_json_dict_float_lists(current_data),
        baseline_metrics=_parse_json(baseline_metrics),
        current_metrics=_parse_json(current_metrics),
        model_registry_entry_id=model_registry_entry_id,
        name=name,
        baseline_dataset=baseline_dataset,
        current_dataset=current_dataset,
        psi_threshold=psi_threshold,
        js_threshold=js_threshold,
        concept_drift_threshold=concept_drift_threshold,
        alert_on_drift=alert_on_drift,
    )
    return await svc.get_run_summary(run.id)


# ── Queries ──

@router.get("/drift-detection/runs/{run_id}")
async def get_run(
    run_id: int,
    session=Depends(deps.get_session),
    _=Depends(deps.get_current_active_superuser),
):
    svc = DriftDetectionService(session)
    summary = await svc.get_run_summary(run_id)
    if not summary:
        raise HTTPException(404, "Run not found")
    return summary


@router.get("/drift-detection/runs")
async def list_runs(
    model_registry_entry_id: int | None = None,
    drift_detected: bool | None = None,
    limit: int = 50, offset: int = 0,
    session=Depends(deps.get_session),
    _=Depends(deps.get_current_active_superuser),
):
    svc = DriftDetectionService(session)
    items = await svc.list_runs(
        model_registry_entry_id=model_registry_entry_id,
        drift_detected=drift_detected,
        limit=limit, offset=offset,
    )
    return PaginatedResponse(
        items=[_run_dict(r) for r in items],
        total=len(items), limit=limit, offset=offset,
    )


@router.get("/drift-detection/runs/{run_id}/features")
async def get_feature_drift(
    run_id: int,
    session=Depends(deps.get_session),
    _=Depends(deps.get_current_active_superuser),
):
    svc = DriftDetectionService(session)
    items = await svc.get_feature_drift_results(run_id)
    return {
        "run_id": run_id,
        "features": [_feat_dict(f) for f in items],
    }


@router.get("/drift-detection/runs/{run_id}/concept")
async def get_concept_drift(
    run_id: int,
    session=Depends(deps.get_session),
    _=Depends(deps.get_current_active_superuser),
):
    svc = DriftDetectionService(session)
    items = await svc.get_concept_drift_results(run_id)
    return {
        "run_id": run_id,
        "concept_drift": [_conc_dict(c) for c in items],
    }


# ── Alerts ──

@router.get("/drift-alerts")
async def get_alerts(
    acknowledged: bool | None = None,
    severity: str | None = None,
    limit: int = 50, offset: int = 0,
    session=Depends(deps.get_session),
    _=Depends(deps.get_current_active_superuser),
):
    svc = DriftDetectionService(session)
    items = await svc.get_alerts(
        acknowledged=acknowledged, severity=severity,
        limit=limit, offset=offset,
    )
    return PaginatedResponse(
        items=[_alert_dict(a) for a in items],
        total=len(items), limit=limit, offset=offset,
    )


@router.post("/drift-alerts/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: int,
    session=Depends(deps.get_session),
    _=Depends(deps.get_current_active_superuser),
):
    svc = DriftDetectionService(session)
    alert = await svc.acknowledge_alert(alert_id)
    if not alert:
        raise HTTPException(404, "Alert not found")
    return _alert_dict(alert)


# ── Monitoring ──

@router.post("/distribution-monitoring", status_code=201)
async def monitor_distributions(
    features: str = Query(...),
    model_registry_entry_id: int = Query(...),
    dataset_name: str | None = None,
    session=Depends(deps.get_session),
    _=Depends(deps.get_current_active_superuser),
):
    svc = DriftDetectionService(session)
    profiles = await svc.monitor_distributions(
        features=_parse_json_dict_float_lists(features),
        model_registry_entry_id=model_registry_entry_id,
        dataset_name=dataset_name,
    )
    return {"profiles_created": len(profiles)}


# ── Helpers ──

def _parse_float_list(val: str) -> list[float]:
    return [float(x.strip()) for x in val.split(",") if x.strip()]


def _parse_json(val: str | None) -> Any:
    if val is None:
        return None
    import json as _json
    return _json.loads(val)


def _parse_json_dict_float_lists(val: str) -> dict[str, list[float]]:
    import json as _json
    raw = _json.loads(val)
    return {k: [float(x) for x in v] for k, v in raw.items()}


def _profile_dict(p: Any) -> dict:
    return {
        "id": p.id, "feature_name": p.feature_name,
        "profile_type": p.profile_type, "num_samples": p.num_samples,
        "mean": p.mean, "std": p.std,
        "min": p.minimum, "max": p.maximum,
        "median": p.median, "p25": p.p25, "p75": p.p75,
        "dataset_name": p.dataset_name,
    }


def _run_dict(r: Any) -> dict:
    return {
        "id": r.id, "name": r.name, "status": r.status,
        "drift_detected": r.drift_detected,
        "overall_drift_score": r.overall_drift_score,
        "num_features_compared": r.num_features_compared,
        "num_drifted_features": r.num_drifted_features,
        "baseline_dataset": r.baseline_dataset,
        "current_dataset": r.current_dataset,
        "ran_at": r.ran_at.isoformat() if r.ran_at else None,
    }


def _feat_dict(f: Any) -> dict:
    return {
        "feature_name": f.feature_name, "drift_score": f.drift_score,
        "drift_type": f.drift_type, "drifted": f.drifted,
        "threshold": f.threshold,
        "baseline_mean": f.baseline_mean, "current_mean": f.current_mean,
        "baseline_std": f.baseline_std, "current_std": f.current_std,
    }


def _conc_dict(c: Any) -> dict:
    return {
        "metric_name": c.metric_name,
        "baseline_value": c.baseline_value, "current_value": c.current_value,
        "absolute_change": c.absolute_change,
        "percentage_change": c.percentage_change,
        "drifted": c.drifted, "threshold": c.threshold,
    }


def _alert_dict(a: Any) -> dict:
    return {
        "id": a.id, "alert_type": a.alert_type,
        "feature_name": a.feature_name, "severity": a.severity,
        "message": a.message, "drift_score": a.drift_score,
        "threshold": a.threshold, "acknowledged": a.acknowledged,
        "acknowledged_at": a.acknowledged_at.isoformat() if a.acknowledged_at else None,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }
