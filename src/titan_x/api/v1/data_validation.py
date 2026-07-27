from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.api.dependencies import get_current_active_user, get_db
from titan_x.models.user import User
from titan_x.services.dataset_validation_service import DatasetValidationService

router = APIRouter(prefix="/data-validation", tags=["data-validation"])


def _svc(db: AsyncSession) -> DatasetValidationService:
    return DatasetValidationService(db)


@router.post("/validate/{symbol}")
async def validate_dataset(
    symbol: str,
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    svc = _svc(db)
    run = await svc.validate_dataset(symbol.upper(), date_from, date_to)
    return {
        "run_id": run.id,
        "symbol": run.symbol,
        "date_from": run.date_from.isoformat() if run.date_from else None,
        "date_to": run.date_to.isoformat() if run.date_to else None,
        "status": run.status,
        "total_records": run.total_records,
        "anomalies_found": run.anomalies_found,
        "missing_values": run.missing_values,
        "duplicate_rows": run.duplicate_rows,
        "price_anomalies": run.price_anomalies,
        "volume_anomalies": run.volume_anomalies,
        "corp_action_mismatches": run.corp_action_mismatches,
        "timestamp_mismatches": run.timestamp_mismatches,
        "quality_score": run.quality_score,
        "quality_rating": run.quality_rating,
        "error_message": run.error_message,
    }


@router.get("/runs")
async def list_runs(
    symbol: str | None = Query(None),
    status: str | None = Query(None, pattern="^(running|completed|failed)$"),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    svc = _svc(db)
    return await svc.list_validation_runs(symbol, status, limit, offset)


@router.get("/runs/{run_id}")
async def get_run(
    run_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    svc = _svc(db)
    run = await svc.get_validation_run(run_id)
    if not run:
        raise HTTPException(404, "Validation run not found")
    return run


@router.get("/anomalies")
async def list_anomalies(
    run_id: int | None = Query(None),
    anomaly_type: str | None = Query(None, pattern="^(missing_value|duplicate_row|price_anomaly|volume_anomaly|corp_action_mismatch|timestamp_mismatch)$"),
    severity: str | None = Query(None, pattern="^(low|medium|high)$"),
    symbol: str | None = Query(None),
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    svc = _svc(db)
    return await svc.get_anomalies(run_id, anomaly_type, severity, symbol, limit, offset)


@router.get("/anomalies/stats")
async def anomaly_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    svc = _svc(db)
    return await svc.get_anomaly_stats()


@router.get("/quality/scores")
async def list_quality_scores(
    symbol: str | None = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    svc = _svc(db)
    return await svc.get_quality_scores(symbol, limit, offset)


@router.get("/quality/stats")
async def quality_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    svc = _svc(db)
    return await svc.get_quality_stats()


@router.post("/clear")
async def clear_old_data(
    older_than_days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    svc = _svc(db)
    count = await svc.clear_anomalies(older_than_days)
    return {"cleared": count}


# Lightweight standalone checks

@router.post("/check/missing-values")
async def check_missing_values(
    symbol: str = Query(...),
    date_from: date = Query(...),
    date_to: date = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    svc = _svc(db)
    run = await svc.validate_dataset(symbol.upper(), date_from, date_to)
    return {
        "run_id": run.id,
        "missing_values": run.missing_values,
        "total_records": run.total_records,
    }


@router.post("/check/duplicates")
async def check_duplicates(
    symbol: str = Query(...),
    date_from: date = Query(...),
    date_to: date = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    svc = _svc(db)
    run = await svc.validate_dataset(symbol.upper(), date_from, date_to)
    return {
        "run_id": run.id,
        "duplicate_rows": run.duplicate_rows,
        "total_records": run.total_records,
    }


@router.post("/check/price-anomalies")
async def check_price_anomalies(
    symbol: str = Query(...),
    date_from: date = Query(...),
    date_to: date = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    svc = _svc(db)
    run = await svc.validate_dataset(symbol.upper(), date_from, date_to)
    return {
        "run_id": run.id,
        "price_anomalies": run.price_anomalies,
        "total_records": run.total_records,
    }


@router.post("/check/volume-anomalies")
async def check_volume_anomalies(
    symbol: str = Query(...),
    date_from: date = Query(...),
    date_to: date = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    svc = _svc(db)
    run = await svc.validate_dataset(symbol.upper(), date_from, date_to)
    return {
        "run_id": run.id,
        "volume_anomalies": run.volume_anomalies,
        "total_records": run.total_records,
    }


@router.post("/check/corp-action-mismatch")
async def check_corp_action_mismatch(
    symbol: str = Query(...),
    date_from: date = Query(...),
    date_to: date = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    svc = _svc(db)
    run = await svc.validate_dataset(symbol.upper(), date_from, date_to)
    return {
        "run_id": run.id,
        "corp_action_mismatches": run.corp_action_mismatches,
        "total_records": run.total_records,
    }


@router.post("/check/timestamps")
async def check_timestamps(
    symbol: str = Query(...),
    date_from: date = Query(...),
    date_to: date = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    svc = _svc(db)
    run = await svc.validate_dataset(symbol.upper(), date_from, date_to)
    return {
        "run_id": run.id,
        "timestamp_mismatches": run.timestamp_mismatches,
        "total_records": run.total_records,
    }


@router.post("/check/quality-score")
async def check_quality_score(
    symbol: str = Query(...),
    date_from: date = Query(...),
    date_to: date = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    svc = _svc(db)
    run = await svc.validate_dataset(symbol.upper(), date_from, date_to)
    return {
        "run_id": run.id,
        "quality_score": run.quality_score,
        "quality_rating": run.quality_rating,
        "completeness": None,
        "uniqueness": None,
        "accuracy": None,
        "consistency": None,
        "timeliness": None,
    }
