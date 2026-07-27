import json
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, delete, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.models.feature_store import (
    FeatureLineage,
    FeatureOfflineStore,
    FeatureStoreDef,
    FeatureStoreEntity,
    FeatureStoreValue,
    FeatureValidationResult,
    FeatureValidationRule,
    FeatureVersion,
)


class FeatureStoreService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── Entities ──

    async def create_entity(
        self, name: str,
        description: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> FeatureStoreEntity:
        e = FeatureStoreEntity(
            name=name, description=description,
            metadata_json=json.dumps(metadata) if metadata else None,
        )
        self.session.add(e)
        await self.session.flush()
        await self.session.refresh(e)
        return e

    async def get_entity(self, entity_id: int) -> FeatureStoreEntity | None:
        return await self.session.get(FeatureStoreEntity, entity_id)

    async def get_entity_by_name(self, name: str) -> FeatureStoreEntity | None:
        r = await self.session.execute(
            select(FeatureStoreEntity).where(FeatureStoreEntity.name == name)
        )
        return r.scalar_one_or_none()

    async def list_entities(self, status: str | None = None, limit: int = 50, offset: int = 0) -> list[FeatureStoreEntity]:
        q = select(FeatureStoreEntity)
        if status:
            q = q.where(FeatureStoreEntity.status == status)
        q = q.order_by(desc(FeatureStoreEntity.created_at)).offset(offset).limit(limit)
        r = await self.session.execute(q)
        return list(r.scalars().all())

    # ── Feature Definitions ──

    async def create_feature(
        self, entity_id: int, name: str,
        display_name: str | None = None,
        description: str | None = None,
        feature_type: str = "numerical",
        source: str | None = None,
        source_expression: str | None = None,
        tags: list[str] | None = None,
        is_online: bool = True,
        is_offline: bool = True,
        immutable: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> FeatureStoreDef:
        fd = FeatureStoreDef(
            entity_id=entity_id, name=name,
            display_name=display_name, description=description,
            feature_type=feature_type,
            source=source, source_expression=source_expression,
            tags_json=json.dumps(tags) if tags else None,
            is_online=is_online, is_offline=is_offline,
            immutable=immutable,
            metadata_json=json.dumps(metadata) if metadata else None,
        )
        self.session.add(fd)
        await self.session.flush()
        await self.session.refresh(fd)
        await self._create_initial_version(fd)
        return fd

    async def _create_initial_version(self, fd: FeatureStoreDef) -> FeatureVersion:
        fv = FeatureVersion(
            feature_id=fd.id,
            version="1.0.0",
            definition_json=json.dumps({
                "entity_id": fd.entity_id, "name": fd.name,
                "feature_type": fd.feature_type, "source": fd.source,
                "is_online": fd.is_online, "is_offline": fd.is_offline,
                "immutable": fd.immutable,
            }),
            change_log="Initial version",
        )
        self.session.add(fv)
        await self.session.flush()
        await self.session.refresh(fv)
        return fv

    async def get_feature(self, feature_id: int) -> FeatureStoreDef | None:
        return await self.session.get(FeatureStoreDef, feature_id)

    async def get_feature_by_name(self, entity_id: int, name: str) -> FeatureStoreDef | None:
        r = await self.session.execute(
            select(FeatureStoreDef).where(
                FeatureStoreDef.entity_id == entity_id,
                FeatureStoreDef.name == name,
            )
        )
        return r.scalar_one_or_none()

    async def list_features(
        self, entity_id: int | None = None,
        feature_type: str | None = None,
        status: str | None = None,
        online_only: bool | None = None,
        limit: int = 50, offset: int = 0,
    ) -> list[FeatureStoreDef]:
        q = select(FeatureStoreDef)
        if entity_id is not None:
            q = q.where(FeatureStoreDef.entity_id == entity_id)
        if feature_type:
            q = q.where(FeatureStoreDef.feature_type == feature_type)
        if status:
            q = q.where(FeatureStoreDef.status == status)
        if online_only is True:
            q = q.where(FeatureStoreDef.is_online == True)
        elif online_only is False:
            q = q.where(FeatureStoreDef.is_offline == True)
        q = q.order_by(FeatureStoreDef.name).offset(offset).limit(limit)
        r = await self.session.execute(q)
        return list(r.scalars().all())

    async def update_feature(
        self, feature_id: int,
        display_name: str | None = None,
        description: str | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> FeatureStoreDef | None:
        fd = await self.get_feature(feature_id)
        if not fd:
            return None
        if display_name is not None:
            fd.display_name = display_name
        if description is not None:
            fd.description = description
        if tags is not None:
            fd.tags_json = json.dumps(tags)
        if metadata is not None:
            fd.metadata_json = json.dumps(metadata)
        await self.session.flush()
        await self.session.refresh(fd)
        return fd

    # ── Versions ──

    async def create_version(
        self, feature_id: int, version: str,
        change_log: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> FeatureVersion:
        fd = await self.get_feature(feature_id)
        fv = FeatureVersion(
            feature_id=feature_id, version=version,
            definition_json=json.dumps({
                "entity_id": fd.entity_id, "name": fd.name,
                "feature_type": fd.feature_type, "source": fd.source,
                "is_online": fd.is_online, "is_offline": fd.is_offline,
                "immutable": fd.immutable,
            }) if fd else None,
            change_log=change_log,
            metadata_json=json.dumps(metadata) if metadata else None,
        )
        self.session.add(fv)
        await self.session.flush()
        await self.session.refresh(fv)
        return fv

    async def get_version(self, version_id: int) -> FeatureVersion | None:
        return await self.session.get(FeatureVersion, version_id)

    async def list_versions(
        self, feature_id: int,
        limit: int = 50, offset: int = 0,
    ) -> list[FeatureVersion]:
        r = await self.session.execute(
            select(FeatureVersion)
            .where(FeatureVersion.feature_id == feature_id)
            .order_by(desc(FeatureVersion.created_at))
            .offset(offset).limit(limit)
        )
        return list(r.scalars().all())

    # ── Online Store (FeatureStoreValue / cache) ──

    async def set_online_value(
        self, feature_id: int, entity_key: str, value: str,
        value_type: str | None = None,
        ttl_seconds: int | None = None,
    ) -> FeatureStoreValue:
        existing = await self._get_online_value(feature_id, entity_key)
        expires_at = None
        if ttl_seconds is not None:
            expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(seconds=ttl_seconds)
        if existing:
            existing.value = value
            existing.value_type = value_type
            existing.ttl_seconds = ttl_seconds
            existing.expires_at = expires_at
            await self.session.flush()
            await self.session.refresh(existing)
            return existing
        fv = FeatureStoreValue(
            feature_id=feature_id, entity_key=entity_key,
            value=value, value_type=value_type,
            ttl_seconds=ttl_seconds, expires_at=expires_at,
        )
        self.session.add(fv)
        await self.session.flush()
        await self.session.refresh(fv)
        return fv

    async def _get_online_value(self, feature_id: int, entity_key: str) -> FeatureStoreValue | None:
        r = await self.session.execute(
            select(FeatureStoreValue).where(
                FeatureStoreValue.feature_id == feature_id,
                FeatureStoreValue.entity_key == entity_key,
            )
        )
        return r.scalar_one_or_none()

    async def get_online_value(
        self, feature_id: int, entity_key: str,
        check_cache: bool = True,
    ) -> str | None:
        fv = await self._get_online_value(feature_id, entity_key)
        if not fv:
            return None
        if check_cache and fv.is_expired():
            return None
        return fv.value

    async def get_online_features(
        self, feature_ids: list[int], entity_key: str,
    ) -> dict[int, str | None]:
        result: dict[int, str | None] = {}
        r = await self.session.execute(
            select(FeatureStoreValue).where(
                FeatureStoreValue.feature_id.in_(feature_ids),
                FeatureStoreValue.entity_key == entity_key,
            )
        )
        rows = r.scalars().all()
        found = {fv.feature_id: fv for fv in rows}
        for fid in feature_ids:
            fv = found.get(fid)
            if fv and not fv.is_expired():
                result[fid] = fv.value
            else:
                result[fid] = None
        return result

    async def delete_online_value(self, feature_id: int, entity_key: str) -> bool:
        r = await self.session.execute(
            delete(FeatureStoreValue).where(
                FeatureStoreValue.feature_id == feature_id,
                FeatureStoreValue.entity_key == entity_key,
            )
        )
        return r.rowcount > 0

    async def purge_expired_values(self) -> int:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        r = await self.session.execute(
            delete(FeatureStoreValue).where(
                FeatureStoreValue.expires_at.isnot(None),
                FeatureStoreValue.expires_at < now,
            )
        )
        return r.rowcount

    # ── Offline Store ──

    async def set_offline_batch(
        self, feature_id: int, values: list[dict[str, Any]],
        batch_id: str, as_of_date: datetime | None = None,
    ) -> list[FeatureOfflineStore]:
        as_of = as_of_date or datetime.now(timezone.utc).replace(tzinfo=None)
        rows: list[FeatureOfflineStore] = []
        for entry in values:
            row = FeatureOfflineStore(
                feature_id=feature_id,
                entity_key=entry["entity_key"],
                value=str(entry["value"]),
                value_type=entry.get("value_type"),
                batch_id=batch_id,
                as_of_date=as_of,
            )
            self.session.add(row)
            rows.append(row)
        await self.session.flush()
        for r in rows:
            await self.session.refresh(r)
        return rows

    async def get_offline_values(
        self, feature_id: int,
        as_of_date: datetime | None = None,
        batch_id: str | None = None,
        entity_key: str | None = None,
        limit: int = 1000, offset: int = 0,
    ) -> list[FeatureOfflineStore]:
        q = select(FeatureOfflineStore).where(FeatureOfflineStore.feature_id == feature_id)
        if as_of_date:
            q = q.where(FeatureOfflineStore.as_of_date <= as_of_date)
        if batch_id:
            q = q.where(FeatureOfflineStore.batch_id == batch_id)
        if entity_key:
            q = q.where(FeatureOfflineStore.entity_key == entity_key)
        q = q.order_by(desc(FeatureOfflineStore.as_of_date)).offset(offset).limit(limit)
        r = await self.session.execute(q)
        return list(r.scalars().all())

    async def get_offline_dataset(
        self, feature_ids: list[int],
        as_of_date: datetime | None = None,
        batch_id: str | None = None,
        entity_keys: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        if not feature_ids:
            return []
        q = select(FeatureOfflineStore).where(FeatureOfflineStore.feature_id.in_(feature_ids))
        if as_of_date:
            q = q.where(FeatureOfflineStore.as_of_date <= as_of_date)
        if batch_id:
            q = q.where(FeatureOfflineStore.batch_id == batch_id)
        if entity_keys:
            q = q.where(FeatureOfflineStore.entity_key.in_(entity_keys))
        q = q.order_by(FeatureOfflineStore.entity_key, FeatureOfflineStore.feature_id)
        r = await self.session.execute(q)
        rows = r.scalars().all()

        grouped: dict[str, dict[str, Any]] = {}
        for row in rows:
            if row.entity_key not in grouped:
                grouped[row.entity_key] = {"entity_key": row.entity_key}
            grouped[row.entity_key][str(row.feature_id)] = row.value
        return list(grouped.values())

    # ── Lineage ──

    async def add_lineage(
        self, feature_id: int,
        source_type: str, source_name: str,
        source_version: str | None = None,
        transformation_description: str | None = None,
        dependencies: list[int] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> FeatureLineage:
        fl = FeatureLineage(
            feature_id=feature_id, source_type=source_type,
            source_name=source_name, source_version=source_version,
            transformation_description=transformation_description,
            dependencies_json=json.dumps(dependencies) if dependencies else None,
            metadata_json=json.dumps(metadata) if metadata else None,
        )
        self.session.add(fl)
        await self.session.flush()
        await self.session.refresh(fl)
        return fl

    async def get_lineage(self, feature_id: int) -> list[FeatureLineage]:
        r = await self.session.execute(
            select(FeatureLineage)
            .where(FeatureLineage.feature_id == feature_id)
            .order_by(FeatureLineage.source_type)
        )
        return list(r.scalars().all())

    async def get_lineage_graph(self, feature_id: int) -> dict[str, Any]:
        feature = await self.get_feature(feature_id)
        if not feature:
            return {"feature": None, "upstream": [], "downstream": []}
        upstream = await self.get_lineage(feature_id)
        dep_ids: list[int] = []
        for u in upstream:
            if u.dependencies_json:
                dep_ids.extend(json.loads(u.dependencies_json))
        r = await self.session.execute(
            select(FeatureLineage).where(FeatureLineage.dependencies_json.isnot(None))
        )
        all_lineage = r.scalars().all()
        downstream = [
            l for l in all_lineage
            if l.dependencies_json and str(feature_id) in l.dependencies_json
        ]
        return {
            "feature": {"id": feature.id, "name": feature.name},
            "upstream": [
                {"id": u.id, "source_type": u.source_type, "source_name": u.source_name}
                for u in upstream
            ],
            "downstream": [
                {"id": d.id, "feature_id": d.feature_id, "source_name": d.source_name}
                for d in downstream
            ],
        }

    # ── Validation Rules ──

    async def create_validation_rule(
        self, name: str, rule_type: str,
        feature_id: int | None = None,
        description: str | None = None,
        config: dict[str, Any] | None = None,
        severity: str = "error",
    ) -> FeatureValidationRule:
        rule = FeatureValidationRule(
            feature_id=feature_id, name=name,
            description=description, rule_type=rule_type,
            config_json=json.dumps(config) if config else None,
            severity=severity,
        )
        self.session.add(rule)
        await self.session.flush()
        await self.session.refresh(rule)
        return rule

    async def list_validation_rules(
        self, feature_id: int | None = None,
        rule_type: str | None = None,
        limit: int = 50, offset: int = 0,
    ) -> list[FeatureValidationRule]:
        q = select(FeatureValidationRule)
        if feature_id is not None:
            q = q.where(
                or_(
                    FeatureValidationRule.feature_id == feature_id,
                    FeatureValidationRule.feature_id.is_(None),
                )
            )
        if rule_type:
            q = q.where(FeatureValidationRule.rule_type == rule_type)
        q = q.order_by(FeatureValidationRule.name).offset(offset).limit(limit)
        r = await self.session.execute(q)
        return list(r.scalars().all())

    # ── Validation ──

    async def validate_value(
        self, feature_id: int, value: Any,
        entity_key: str | None = None,
        batch_id: str | None = None,
    ) -> list[FeatureValidationResult]:
        rules = await self.list_validation_rules(feature_id=feature_id)
        results: list[FeatureValidationResult] = []
        for rule in rules:
            status, message = self._apply_rule(rule, value)
            result = FeatureValidationResult(
                rule_id=rule.id, feature_id=feature_id,
                batch_id=batch_id, entity_key=entity_key,
                status=status, actual_value=str(value),
                message=message,
                validated_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )
            self.session.add(result)
            results.append(result)
        await self.session.flush()
        for r in results:
            await self.session.refresh(r)
        return results

    def _apply_rule(self, rule: FeatureValidationRule, value: Any) -> tuple[str, str]:
        config = json.loads(rule.config_json) if rule.config_json else {}
        try:
            if rule.rule_type == "null_check":
                if value is None or str(value).strip() == "":
                    return ("failed", "Value is null or empty")
                return ("passed", "Value is not null")

            elif rule.rule_type == "range":
                num = float(value)
                min_v = config.get("min")
                max_v = config.get("max")
                if min_v is not None and num < min_v:
                    return ("failed", f"Value {num} is below minimum {min_v}")
                if max_v is not None and num > max_v:
                    return ("failed", f"Value {num} exceeds maximum {max_v}")
                return ("passed", f"Value {num} is within range")

            elif rule.rule_type == "type_check":
                expected = config.get("type", "numerical")
                if expected == "numerical":
                    float(value)
                    return ("passed", "Is numerical")
                elif expected == "integer":
                    int(value)
                    return ("passed", "Is integer")
                elif expected == "boolean":
                    if str(value).lower() not in ("true", "false", "1", "0"):
                        return ("failed", f"Not a boolean: {value}")
                    return ("passed", "Is boolean")
                return ("passed", f"Type check: {expected}")

            elif rule.rule_type == "regex":
                import re as regex_mod
                pattern = config.get("pattern", "")
                if not regex_mod.match(pattern, str(value)):
                    return ("failed", f"Value '{value}' does not match pattern '{pattern}'")
                return ("passed", "Matches regex pattern")

            elif rule.rule_type == "cardinality":
                max_card = config.get("max_unique", 100)
                return ("passed", f"Cardinality check configured (max {max_card})")

            return ("passed", "No check applied")

        except (ValueError, TypeError) as e:
            return ("error", f"Validation error: {e!s}")

    async def get_validation_results(
        self, feature_id: int | None = None,
        batch_id: str | None = None,
        status: str | None = None,
        limit: int = 100, offset: int = 0,
    ) -> list[FeatureValidationResult]:
        q = select(FeatureValidationResult)
        if feature_id is not None:
            q = q.where(FeatureValidationResult.feature_id == feature_id)
        if batch_id is not None:
            q = q.where(FeatureValidationResult.batch_id == batch_id)
        if status is not None:
            q = q.where(FeatureValidationResult.status == status)
        q = q.order_by(desc(FeatureValidationResult.validated_at)).offset(offset).limit(limit)
        r = await self.session.execute(q)
        return list(r.scalars().all())

    # ── Cache utilities ──

    async def get_cache_hit_rate(self) -> dict[str, Any]:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        total = await self.session.scalar(select(func.count(FeatureStoreValue.id)))
        expired = await self.session.scalar(
            select(func.count(FeatureStoreValue.id)).where(
                FeatureStoreValue.expires_at.isnot(None),
                FeatureStoreValue.expires_at < now,
            )
        )
        if not total:
            return {"total": 0, "expired": 0, "hit_rate": 1.0}
        return {
            "total": total,
            "expired": expired or 0,
            "hit_rate": 1.0 - ((expired or 0) / total),
        }

    async def warm_cache(
        self, feature_id: int,
        values: list[dict[str, Any]],
        ttl_seconds: int = 3600,
    ) -> int:
        count = 0
        for entry in values:
            await self.set_online_value(
                feature_id=feature_id,
                entity_key=entry["entity_key"],
                value=str(entry["value"]),
                value_type=entry.get("value_type"),
                ttl_seconds=ttl_seconds,
            )
            count += 1
        return count

    async def clear_cache(self, feature_id: int | None = None) -> int:
        q = delete(FeatureStoreValue)
        if feature_id is not None:
            q = q.where(FeatureStoreValue.feature_id == feature_id)
        r = await self.session.execute(q)
        return r.rowcount
