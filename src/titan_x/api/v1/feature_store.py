from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from titan_x.api import deps
from titan_x.models.user import User
from titan_x.api.schemas import PaginatedResponse
from titan_x.services.feature_store_service import FeatureStoreService

router = APIRouter(tags=["feature-store"])


# ── Entities ──

@router.post("/entities", status_code=201)
async def create_entity(
    name: str = Query(...),
    description: str | None = None,
    metadata: str | None = None,
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_superuser),
):
    svc = FeatureStoreService(session)
    e = await svc.create_entity(name=name, description=description, metadata=_parse_json(metadata))
    return {"id": e.id, "name": e.name}


@router.get("/entities/{entity_id}")
async def get_entity(
    entity_id: int,
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_superuser),
):
    svc = FeatureStoreService(session)
    e = await svc.get_entity(entity_id)
    if not e:
        raise HTTPException(404, "Entity not found")
    return _entity_dict(e)


@router.get("/entities")
async def list_entities(
    status: str | None = None,
    limit: int = 50, offset: int = 0,
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_superuser),
):
    svc = FeatureStoreService(session)
    items = await svc.list_entities(status=status, limit=limit, offset=offset)
    return PaginatedResponse(items=[_entity_dict(e) for e in items], total=await svc.count_entities(status), limit=limit, offset=offset)


# ── Feature Definitions ──

@router.post("/features", status_code=201)
async def create_feature(
    entity_id: int = Query(...),
    name: str = Query(...),
    display_name: str | None = None,
    description: str | None = None,
    feature_type: str = "numerical",
    source: str | None = None,
    source_expression: str | None = None,
    tags: str | None = None,
    is_online: bool = True,
    is_offline: bool = True,
    immutable: bool = False,
    metadata: str | None = None,
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_superuser),
):
    svc = FeatureStoreService(session)
    fd = await svc.create_feature(
        entity_id=entity_id, name=name,
        display_name=display_name, description=description,
        feature_type=feature_type, source=source, source_expression=source_expression,
        tags=_parse_json(tags), is_online=is_online, is_offline=is_offline,
        immutable=immutable, metadata=_parse_json(metadata),
    )
    return {"id": fd.id, "name": fd.name, "entity_id": fd.entity_id}


@router.get("/features/{feature_id}")
async def get_feature(
    feature_id: int,
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_superuser),
):
    svc = FeatureStoreService(session)
    fd = await svc.get_feature(feature_id)
    if not fd:
        raise HTTPException(404, "Feature not found")
    return _feature_dict(fd)


@router.get("/features")
async def list_features(
    entity_id: int | None = None,
    feature_type: str | None = None,
    status: str | None = None,
    online_only: bool | None = None,
    limit: int = 50, offset: int = 0,
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_superuser),
):
    svc = FeatureStoreService(session)
    items = await svc.list_features(
        entity_id=entity_id, feature_type=feature_type,
        status=status, online_only=online_only,
        limit=limit, offset=offset,
    )
    return PaginatedResponse(
        items=[_feature_dict(f) for f in items],
        total=await svc.count_features(
            entity_id=entity_id, feature_type=feature_type,
            status=status, online_only=online_only,
        ),
        limit=limit,
        offset=offset,
    )


@router.patch("/features/{feature_id}")
async def update_feature(
    feature_id: int,
    display_name: str | None = None,
    description: str | None = None,
    tags: str | None = None,
    metadata: str | None = None,
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_superuser),
):
    svc = FeatureStoreService(session)
    fd = await svc.update_feature(
        feature_id, display_name=display_name,
        description=description, tags=_parse_json(tags),
        metadata=_parse_json(metadata),
    )
    if not fd:
        raise HTTPException(404, "Feature not found")
    return _feature_dict(fd)


# ── Versions ──

@router.post("/features/{feature_id}/versions", status_code=201)
async def create_version(
    feature_id: int,
    version: str = Query(...),
    change_log: str | None = None,
    metadata: str | None = None,
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_superuser),
):
    svc = FeatureStoreService(session)
    fv = await svc.create_version(
        feature_id=feature_id, version=version,
        change_log=change_log, metadata=_parse_json(metadata),
    )
    return {"id": fv.id, "version": fv.version}


@router.get("/features/{feature_id}/versions")
async def list_versions(
    feature_id: int,
    limit: int = 50, offset: int = 0,
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_superuser),
):
    svc = FeatureStoreService(session)
    items = await svc.list_versions(feature_id, limit=limit, offset=offset)
    return PaginatedResponse(items=[_ver_dict(v) for v in items], total=await svc.count_versions(feature_id), limit=limit, offset=offset)


# ── Online Store ──

@router.put("/online/{feature_id}/{entity_key}")
async def set_online_value(
    feature_id: int, entity_key: str,
    value: str = Query(...),
    value_type: str | None = None,
    ttl_seconds: int | None = None,
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_superuser),
):
    svc = FeatureStoreService(session)
    fv = await svc.set_online_value(
        feature_id, entity_key, value,
        value_type=value_type, ttl_seconds=ttl_seconds,
    )
    return {"id": fv.id, "feature_id": fv.feature_id, "entity_key": fv.entity_key}


@router.get("/online/{feature_id}/{entity_key}")
async def get_online_value(
    feature_id: int, entity_key: str,
    bypass_cache: bool = False,
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_superuser),
):
    svc = FeatureStoreService(session)
    value = await svc.get_online_value(feature_id, entity_key, check_cache=not bypass_cache)
    if value is None:
        raise HTTPException(404, "Online value not found or expired")
    return {"feature_id": feature_id, "entity_key": entity_key, "value": value}


@router.post("/online/batch")
async def get_online_features(
    feature_ids: str = Query(...),
    entity_key: str = Query(...),
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_superuser),
):
    svc = FeatureStoreService(session)
    fids = [int(x) for x in feature_ids.split(",")]
    result = await svc.get_online_features(fids, entity_key)
    return {"entity_key": entity_key, "features": {str(k): v for k, v in result.items()}}


@router.delete("/online/{feature_id}/{entity_key}")
async def delete_online_value(
    feature_id: int, entity_key: str,
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_superuser),
):
    svc = FeatureStoreService(session)
    ok = await svc.delete_online_value(feature_id, entity_key)
    if not ok:
        raise HTTPException(404, "Online value not found")
    return {"deleted": True}


@router.post("/online/purge-expired")
async def purge_expired(
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_superuser),
):
    svc = FeatureStoreService(session)
    count = await svc.purge_expired_values()
    return {"purged": count}


# ── Offline Store ──

@router.post("/offline/batch", status_code=201)
async def set_offline_batch(
    feature_id: int = Query(...),
    batch_id: str = Query(...),
    values: str = Query(...),
    as_of_date: str | None = None,
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_superuser),
):
    svc = FeatureStoreService(session)
    parsed = _parse_json(values)
    as_of = datetime.fromisoformat(as_of_date) if as_of_date else None
    rows = await svc.set_offline_batch(
        feature_id, parsed, batch_id, as_of_date=as_of,
    )
    return {"count": len(rows), "batch_id": batch_id}


@router.get("/offline/{feature_id}")
async def get_offline_values(
    feature_id: int,
    as_of_date: str | None = None,
    batch_id: str | None = None,
    entity_key: str | None = None,
    limit: int = 1000, offset: int = 0,
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_superuser),
):
    svc = FeatureStoreService(session)
    as_of = datetime.fromisoformat(as_of_date) if as_of_date else None
    items = await svc.get_offline_values(
        feature_id, as_of_date=as_of, batch_id=batch_id,
        entity_key=entity_key, limit=limit, offset=offset,
    )
    return PaginatedResponse(
        items=[_offline_dict(o) for o in items],
        total=await svc.count_offline_values(
            feature_id, as_of_date=as_of, batch_id=batch_id, entity_key=entity_key,
        ),
        limit=limit,
        offset=offset,
    )


@router.post("/offline/dataset")
async def get_offline_dataset(
    feature_ids: str = Query(...),
    as_of_date: str | None = None,
    batch_id: str | None = None,
    entity_keys: str | None = None,
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_superuser),
):
    svc = FeatureStoreService(session)
    fids = [int(x) for x in feature_ids.split(",")]
    as_of = datetime.fromisoformat(as_of_date) if as_of_date else None
    keys = entity_keys.split(",") if entity_keys else None
    data = await svc.get_offline_dataset(fids, as_of_date=as_of, batch_id=batch_id, entity_keys=keys)
    return {"rows": data, "count": len(data)}


# ── Lineage ──

@router.post("/lineage", status_code=201)
async def add_lineage(
    feature_id: int = Query(...),
    source_type: str = Query(...),
    source_name: str = Query(...),
    source_version: str | None = None,
    transformation_description: str | None = None,
    dependencies: str | None = None,
    metadata: str | None = None,
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_superuser),
):
    svc = FeatureStoreService(session)
    deps = [int(x) for x in dependencies.split(",")] if dependencies else None
    fl = await svc.add_lineage(
        feature_id=feature_id, source_type=source_type, source_name=source_name,
        source_version=source_version, transformation_description=transformation_description,
        dependencies=deps, metadata=_parse_json(metadata),
    )
    return {"id": fl.id, "source_type": fl.source_type, "source_name": fl.source_name}


@router.get("/lineage/{feature_id}")
async def get_lineage(
    feature_id: int,
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_superuser),
):
    svc = FeatureStoreService(session)
    items = await svc.get_lineage(feature_id)
    return {"feature_id": feature_id, "lineage": [_lineage_dict(l) for l in items]}


@router.get("/lineage/{feature_id}/graph")
async def get_lineage_graph(
    feature_id: int,
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_superuser),
):
    svc = FeatureStoreService(session)
    return await svc.get_lineage_graph(feature_id)


# ── Validation Rules ──

@router.post("/validation-rules", status_code=201)
async def create_validation_rule(
    name: str = Query(...),
    rule_type: str = Query(...),
    feature_id: int | None = None,
    description: str | None = None,
    config: str | None = None,
    severity: str = "error",
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_superuser),
):
    svc = FeatureStoreService(session)
    rule = await svc.create_validation_rule(
        name=name, rule_type=rule_type, feature_id=feature_id,
        description=description, config=_parse_json(config), severity=severity,
    )
    return {"id": rule.id, "name": rule.name, "rule_type": rule.rule_type}


@router.get("/validation-rules")
async def list_validation_rules(
    feature_id: int | None = None,
    rule_type: str | None = None,
    limit: int = 50, offset: int = 0,
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_superuser),
):
    svc = FeatureStoreService(session)
    items = await svc.list_validation_rules(
        feature_id=feature_id, rule_type=rule_type,
        limit=limit, offset=offset,
    )
    return PaginatedResponse(
        items=[_rule_dict(r) for r in items],
        total=await svc.count_validation_rules(feature_id=feature_id, rule_type=rule_type),
        limit=limit,
        offset=offset,
    )


# ── Validation ──

@router.post("/validate")
async def validate_value(
    feature_id: int = Query(...),
    value: str = Query(...),
    entity_key: str | None = None,
    batch_id: str | None = None,
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_superuser),
):
    svc = FeatureStoreService(session)
    results = await svc.validate_value(feature_id, value, entity_key=entity_key, batch_id=batch_id)
    return {"results": [_val_dict(v) for v in results]}


@router.get("/validation-results")
async def get_validation_results(
    feature_id: int | None = None,
    batch_id: str | None = None,
    status: str | None = None,
    limit: int = 100, offset: int = 0,
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_superuser),
):
    svc = FeatureStoreService(session)
    items = await svc.get_validation_results(
        feature_id=feature_id, batch_id=batch_id,
        status=status, limit=limit, offset=offset,
    )
    return PaginatedResponse(
        items=[_val_dict(v) for v in items],
        total=await svc.count_validation_results(feature_id=feature_id, batch_id=batch_id, status=status),
        limit=limit,
        offset=offset,
    )


# ── Cache ──

@router.get("/cache/stats")
async def cache_stats(
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_superuser),
):
    svc = FeatureStoreService(session)
    return await svc.get_cache_hit_rate()


@router.post("/cache/warm")
async def warm_cache(
    feature_id: int = Query(...),
    values: str = Query(...),
    ttl_seconds: int = 3600,
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_superuser),
):
    svc = FeatureStoreService(session)
    parsed = _parse_json(values)
    count = await svc.warm_cache(feature_id, parsed, ttl_seconds=ttl_seconds)
    return {"cached": count}


@router.delete("/cache")
async def clear_cache(
    feature_id: int | None = None,
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_superuser),
):
    svc = FeatureStoreService(session)
    count = await svc.clear_cache(feature_id=feature_id)
    return {"cleared": count}


# ── Helpers ──

def _parse_json(val: str | None) -> Any:
    if val is None:
        return None
    import json as _json
    return _json.loads(val)


def _entity_dict(e: Any) -> dict:
    return {
        "id": e.id, "name": e.name, "description": e.description,
        "status": e.status, "created_at": e.created_at.isoformat() if e.created_at else None,
    }


def _feature_dict(fd: Any) -> dict:
    return {
        "id": fd.id, "entity_id": fd.entity_id, "name": fd.name,
        "display_name": fd.display_name, "description": fd.description,
        "feature_type": fd.feature_type, "source": fd.source,
        "is_online": fd.is_online, "is_offline": fd.is_offline,
        "immutable": fd.immutable, "status": fd.status,
        "created_at": fd.created_at.isoformat() if fd.created_at else None,
    }


def _ver_dict(v: Any) -> dict:
    return {
        "id": v.id, "feature_id": v.feature_id, "version": v.version,
        "change_log": v.change_log, "status": v.status,
        "created_at": v.created_at.isoformat() if v.created_at else None,
    }


def _offline_dict(o: Any) -> dict:
    return {
        "id": o.id, "feature_id": o.feature_id, "entity_key": o.entity_key,
        "value": o.value, "value_type": o.value_type,
        "batch_id": o.batch_id,
        "as_of_date": o.as_of_date.isoformat() if o.as_of_date else None,
    }


def _lineage_dict(l: Any) -> dict:
    return {
        "id": l.id, "feature_id": l.feature_id, "source_type": l.source_type,
        "source_name": l.source_name, "source_version": l.source_version,
        "transformation_description": l.transformation_description,
    }


def _rule_dict(r: Any) -> dict:
    return {
        "id": r.id, "feature_id": r.feature_id, "name": r.name,
        "description": r.description, "rule_type": r.rule_type,
        "severity": r.severity, "status": r.status,
    }


def _val_dict(v: Any) -> dict:
    return {
        "id": v.id, "rule_id": v.rule_id, "feature_id": v.feature_id,
        "batch_id": v.batch_id, "entity_key": v.entity_key,
        "status": v.status, "actual_value": v.actual_value,
        "message": v.message,
        "validated_at": v.validated_at.isoformat() if v.validated_at else None,
    }
