from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.api.dependencies import get_current_active_user, get_db
from titan_x.models.user import User
from titan_x.services.market_data_collector_service import MarketDataCollectorService

router = APIRouter(prefix="/market-data-collector", tags=["market-data-collector"])


def _svc(db: AsyncSession) -> MarketDataCollectorService:
    return MarketDataCollectorService(db)


# ============================================================
# DATA SOURCES
# ============================================================


@router.post("/sources")
async def create_source(
    name: str = Query(..., min_length=1, max_length=32),
    provider_type: str = Query(..., pattern="^(mock|yahoo|nse|alphavantage)$"),
    config: str | None = Query(None),
    priority: int = Query(0, ge=0),
    rate_limit: float | None = Query(None, ge=0.1),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    svc = _svc(db)
    src = await svc.create_source(name, provider_type, None, priority, rate_limit)
    return {"id": src.id, "name": src.name, "provider_type": src.provider_type, "enabled": src.enabled}


@router.get("/sources")
async def list_sources(
    enabled_only: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    svc = _svc(db)
    sources = await svc.list_sources(enabled_only)
    return [
        {"id": s.id, "name": s.name, "provider_type": s.provider_type, "enabled": s.enabled,
         "priority": s.priority, "status": s.status, "last_sync_at": s.last_sync_at,
         "error_count": s.error_count}
        for s in sources
    ]


@router.get("/sources/{source_id}")
async def get_source(
    source_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    svc = _svc(db)
    src = await svc.get_source(source_id)
    if not src:
        raise HTTPException(404, "Source not found")
    return {"id": src.id, "name": src.name, "provider_type": src.provider_type,
            "enabled": src.enabled, "priority": src.priority, "status": src.status,
            "config_json": src.config_json, "rate_limit_per_second": src.rate_limit_per_second,
            "last_sync_at": src.last_sync_at, "error_count": src.error_count}


@router.put("/sources/{source_id}")
async def update_source(
    source_id: int,
    enabled: bool | None = Query(None),
    priority: int | None = Query(None, ge=0),
    rate_limit: float | None = Query(None, ge=0.1),
    status: str | None = Query(None, pattern="^(active|deleted|paused)$"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    svc = _svc(db)
    kwargs = {}
    if enabled is not None:
        kwargs["enabled"] = enabled
    if priority is not None:
        kwargs["priority"] = priority
    if rate_limit is not None:
        kwargs["rate_limit_per_second"] = rate_limit
    if status is not None:
        kwargs["status"] = status
    src = await svc.update_source(source_id, **kwargs)
    return {"id": src.id, "name": src.name, "enabled": src.enabled, "status": src.status}


@router.delete("/sources/{source_id}")
async def delete_source(
    source_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    svc = _svc(db)
    await svc.delete_source(source_id)
    return {"status": "deleted"}


@router.post("/sources/{source_id}/test")
async def test_source(
    source_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    svc = _svc(db)
    return await svc.test_source(source_id)


# ============================================================
# SYNC OPERATIONS
# ============================================================


@router.post("/sync/incremental/{source_id}/{symbol}")
async def run_incremental_sync(
    source_id: int,
    symbol: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    svc = _svc(db)
    run = await svc.run_incremental_sync(source_id, symbol.upper())
    return {
        "sync_run_id": run.id,
        "symbol": run.symbol,
        "sync_type": run.sync_type,
        "status": run.status,
        "inserted": run.inserted,
        "updated": run.updated,
        "skipped": run.skipped,
        "errors": run.errors,
        "duration_ms": run.duration_ms,
        "error_message": run.error_message,
    }


@router.post("/sync/historical/{source_id}/{symbol}")
async def run_historical_sync(
    source_id: int,
    symbol: str,
    start: date = Query(...),
    end: date | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    svc = _svc(db)
    run = await svc.run_historical_sync(source_id, symbol.upper(), start, end)
    return {
        "sync_run_id": run.id,
        "symbol": run.symbol,
        "date_from": run.date_from.isoformat() if run.date_from else None,
        "date_to": run.date_to.isoformat() if run.date_to else None,
        "sync_type": run.sync_type,
        "status": run.status,
        "inserted": run.inserted,
        "updated": run.updated,
        "skipped": run.skipped,
        "errors": run.errors,
        "duration_ms": run.duration_ms,
        "error_message": run.error_message,
    }


@router.post("/sync/all/{symbol}")
async def sync_all_sources(
    symbol: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    svc = _svc(db)
    runs = await svc.sync_all_sources(symbol.upper())
    return [
        {
            "sync_run_id": r.id,
            "source_id": r.source_id,
            "status": r.status,
            "inserted": r.inserted,
            "updated": r.updated,
            "errors": r.errors,
            "duration_ms": r.duration_ms,
        }
        for r in runs
    ]


# ============================================================
# SYNC RUN HISTORY & STATS
# ============================================================


@router.get("/sync-runs")
async def list_sync_runs(
    source_id: int | None = Query(None),
    symbol: str | None = Query(None),
    sync_type: str | None = Query(None, pattern="^(incremental|historical)$"),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    svc = _svc(db)
    return await svc.get_sync_runs(source_id, symbol, sync_type, limit, offset)


@router.get("/sync-stats")
async def sync_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    svc = _svc(db)
    return await svc.get_sync_stats()


# ============================================================
# AUDIT LOGS
# ============================================================


@router.get("/audit-logs")
async def list_audit_logs(
    sync_run_id: int | None = Query(None),
    event_type: str | None = Query(None),
    severity: str | None = Query(None, pattern="^(info|warn|error)$"),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    svc = _svc(db)
    return await svc.get_audit_logs(sync_run_id, event_type, severity, limit, offset)


# ============================================================
# QUEUE
# ============================================================


@router.post("/queue/enqueue")
async def enqueue_sync(
    source_id: int = Query(...),
    task_type: str = Query(..., pattern="^(incremental_sync|historical_sync)$"),
    symbol: str = Query(..., min_length=1),
    payload: str | None = Query(None),
    priority: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    svc = _svc(db)
    import json
    payload_dict = json.loads(payload) if payload else None
    item = await svc.enqueue_sync(source_id, task_type, symbol.upper(), payload_dict, priority)
    return {"item_id": item.id, "status": item.status, "task_type": item.task_type, "symbol": item.symbol}


@router.post("/queue/process")
async def process_queue(
    batch_size: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    svc = _svc(db)
    processed = await svc.process_queue(batch_size)
    return {"processed": len(processed)}


@router.get("/queue/items")
async def list_queue_items(
    status: str | None = Query(None, pattern="^(pending|processing|completed|failed)$"),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    svc = _svc(db)
    return await svc.list_queue_items(status, limit, offset)


@router.get("/queue/stats")
async def queue_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    svc = _svc(db)
    return await svc.get_queue_stats()


@router.post("/queue/retry-failed")
async def retry_failed(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    svc = _svc(db)
    count = await svc.retry_failed_items()
    return {"retried": count}


@router.post("/queue/clear-completed")
async def clear_completed(
    older_than_days: int = Query(7, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    svc = _svc(db)
    count = await svc.clear_completed_items(older_than_days)
    return {"cleared": count}


# ============================================================
# LIVE STREAMING
# ============================================================


@router.post("/live/start/{source_name}")
async def start_live_stream(
    source_name: str,
    symbols: str = Query(..., description="Comma-separated list of symbols"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    svc = _svc(db)
    symbol_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    await svc.start_live_stream(source_name, symbol_list)
    return {"source": source_name, "symbols": symbol_list, "status": "started"}


@router.post("/live/stop/{source_name}")
async def stop_live_stream(
    source_name: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    svc = _svc(db)
    await svc.stop_live_stream(source_name)
    return {"source": source_name, "status": "stopped"}


@router.get("/live/ticks/{source_name}")
async def consume_ticks(
    source_name: str,
    max_ticks: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    svc = _svc(db)
    ticks = await svc.consume_live_ticks(source_name, max_ticks)
    return {"source": source_name, "ticks": ticks, "count": len(ticks)}


@router.get("/live/streams")
async def active_streams(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    svc = _svc(db)
    return {"active_streams": svc.get_active_streams()}


# ============================================================
# VALIDATION
# ============================================================


@router.post("/validate")
async def validate_record(
    source_id: int = Query(...),
    symbol: str = Query(...),
    trade_date: date = Query(...),
    open: float = Query(...),
    high: float = Query(...),
    low: float = Query(...),
    close: float = Query(...),
    volume: int = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    svc = _svc(db)
    record = {
        "symbol": symbol.upper(),
        "trade_date": trade_date,
        "open": open,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }
    result = await svc.validate_record(source_id, record)
    return {
        "id": result.id,
        "status": result.status,
        "checks_passed": result.checks_passed,
        "checks_failed": result.checks_failed,
        "errors": json.loads(result.errors_json) if result.errors_json else [],
    }


@router.get("/validation/stats")
async def validation_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    svc = _svc(db)
    return await svc.get_validation_stats()


# ============================================================
# CHECKSUM
# ============================================================


@router.post("/checksum/compute/{symbol}/{trade_date}")
async def compute_checksum(
    symbol: str,
    trade_date: date,
    data_type: str = Query("daily_price"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    svc = _svc(db)
    chk = await svc.compute_checksum(symbol.upper(), trade_date, data_type)
    return {
        "id": chk.id,
        "symbol": chk.symbol,
        "trade_date": chk.trade_date.isoformat(),
        "checksum_sha256": chk.checksum_sha256,
        "row_count": chk.row_count,
    }


@router.post("/checksum/verify/{symbol}/{trade_date}")
async def verify_checksum(
    symbol: str,
    trade_date: date,
    data_type: str = Query("daily_price"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    svc = _svc(db)
    ok = await svc.verify_checksum(symbol.upper(), trade_date, data_type)
    return {"symbol": symbol.upper(), "trade_date": trade_date.isoformat(), "verified": ok}


@router.post("/checksum/verify-batch/{symbol}")
async def verify_checksum_batch(
    symbol: str,
    start: date = Query(...),
    end: date = Query(...),
    data_type: str = Query("daily_price"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    svc = _svc(db)
    return await svc.verify_checksum_batch(symbol.upper(), start, end, data_type)
