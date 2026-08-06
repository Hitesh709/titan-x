"""Snapshot, diff, and checksum mixins for :class:`DataLakeService`."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from typing import Any

from sqlalchemy import select

from titan_x.models.data_lake import DataLakeDiff, DataLakeSnapshot
from titan_x.services import datalake_storage as storage


class SnapshotMixin:
    async def create_snapshot(
        self,
        catalog_id: int,
        version: str,
        label: str,
        is_restore_point: bool = True,
        metadata_json: str | None = None,
    ) -> DataLakeSnapshot:
        cat = await self.get_dataset(dataset_id=catalog_id)
        if not cat:
            raise ValueError(f"Dataset {catalog_id} not found")

        ver = await self.get_version(catalog_id, version)
        ver_id = ver.id if ver else None

        rows = storage.load_dataset(cat.layer, cat.name)
        snapshot_dir = storage._ensure_dir(
            os.path.join(storage.get_lake_dir(), "snapshots", cat.name),
        )
        snapshot_path = os.path.join(
            snapshot_dir,
            f"{label.replace(' ', '_')}_{version}.json",
        )
        meta = storage.save_dataset(
            "metadata",
            f"snapshot_{cat.name}",
            rows,
            fmt="json",
            partition_date=None,
            version=label,
        )
        snapshot_path = meta["storage_path"]

        entry = DataLakeSnapshot(
            catalog_id=catalog_id,
            version_id=ver_id,
            version=version,
            label=label,
            snapshot_path=snapshot_path,
            checksum=meta["checksum"],
            row_count=meta["row_count"],
            is_restore_point=is_restore_point,
            metadata_json=metadata_json,
        )
        self.session.add(entry)
        await self.session.commit()
        await self.session.refresh(entry)
        return entry

    async def rollback_to_version(
        self,
        catalog_id: int,
        target_version: str,
        label: str | None = None,
    ) -> dict[str, Any]:
        current = await self.get_dataset(dataset_id=catalog_id)
        if not current:
            raise ValueError(f"Dataset {catalog_id} not found")

        ver = await self.get_version(catalog_id, target_version)
        if not ver:
            raise ValueError(f"Version {target_version} not found for dataset {catalog_id}")

        # Create a restore-point snapshot of the current state
        now_str = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        restore_label = label or f"pre_rollback_{now_str}"
        await self.create_snapshot(
            catalog_id,
            current.schema_version,
            label=restore_label,
            is_restore_point=True,
            metadata_json=json.dumps(
                {
                    "reason": f"Rollback to version {target_version}",
                    "rolled_back_at": now_str,
                }
            ),
        )

        # Load data from the version's storage path
        rows = storage.load_dataset(
            current.layer,
            current.name,
            version=target_version,
        )
        if not rows:
            # Try loading from the version's explicit storage path
            rows = storage.load_dataset_by_path(ver.storage_path)
        if not rows and ver.storage_path and os.path.isdir(ver.storage_path):
            rows = storage.load_dataset(current.layer, current.name, version=target_version)

        # Write data back as a new version
        new_ver_str = f"{target_version}.rollback.{now_str}"
        meta = storage.save_dataset(
            current.layer,
            current.name,
            rows,
            version=new_ver_str,
            fmt=current.format,
        )

        # Create the new version record
        await self.create_version(
            catalog_id=catalog_id,
            version=new_ver_str,
            storage_path=meta["storage_path"],
            row_count=meta["row_count"],
            checksum=meta["checksum"],
            parent_version=target_version,
            metadata_json=json.dumps(
                {
                    "type": "rollback",
                    "rolled_back_from": current.schema_version,
                    "rolled_back_to": target_version,
                    "timestamp": now_str,
                }
            ),
        )

        current.row_count = meta["row_count"]
        current.total_size_bytes = meta["file_size"]
        await self.session.commit()

        return {
            "status": "ok",
            "catalog_id": catalog_id,
            "new_version": new_ver_str,
            "parent_version": target_version,
            "rows_restored": meta["row_count"],
            "restore_point_label": restore_label,
        }

    async def list_snapshots(
        self,
        catalog_id: int | None = None,
    ) -> list[DataLakeSnapshot]:
        stmt = select(DataLakeSnapshot).order_by(
            DataLakeSnapshot.created_at.desc(),
        )
        if catalog_id:
            stmt = stmt.where(DataLakeSnapshot.catalog_id == catalog_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_snapshot(self, snapshot_id: int) -> DataLakeSnapshot | None:
        result = await self.session.execute(
            select(DataLakeSnapshot).where(DataLakeSnapshot.id == snapshot_id)
        )
        return result.scalar_one_or_none()


class DiffMixin:
    async def compute_diff(
        self,
        catalog_id: int,
        source_version: str,
        target_version: str,
        key_column: str | None = None,
    ) -> DataLakeDiff:
        cat = await self.get_dataset(dataset_id=catalog_id)
        if not cat:
            raise ValueError(f"Dataset {catalog_id} not found")

        src_ver = await self.get_version(catalog_id, source_version)
        dst_ver = await self.get_version(catalog_id, target_version)
        if not src_ver or not dst_ver:
            raise ValueError("Source or target version not found")

        src_rows = storage.load_dataset(
            cat.layer,
            cat.name,
            version=source_version,
        )
        dst_rows = storage.load_dataset(
            cat.layer,
            cat.name,
            version=target_version,
        )

        if not src_rows:
            src_rows = storage.load_dataset_by_path(src_ver.storage_path)
        if not dst_rows:
            dst_rows = storage.load_dataset_by_path(dst_ver.storage_path)

        # Normalise rows to dicts
        src_normalised = [dict(r) for r in src_rows]
        dst_normalised = [dict(r) for r in dst_rows]

        if not src_normalised and not dst_normalised:
            return await self._save_diff(
                catalog_id,
                src_ver.id,
                dst_ver.id,
                source_version,
                target_version,
                0,
                0,
                0,
                0,
                key_column=key_column,
            )

        # Pick a key column if none given
        all_keys = set()
        for r in src_normalised:
            all_keys.update(r.keys())
        for r in dst_normalised:
            all_keys.update(r.keys())

        if not key_column:
            candidates = [c for c in ("id", "symbol", "name", "date", "key") if c in all_keys]
            key_column = candidates[0] if candidates else None

        if not key_column:
            raise ValueError(
                "Cannot determine key column. Specify a key_column or ensure "
                "one of 'id', 'symbol', 'name', 'date', 'key' exists."
            )

        # Build lookup maps
        src_map: dict[str, dict] = {}
        for r in src_normalised:
            k = str(r.get(key_column, ""))
            src_map[k] = r

        dst_map: dict[str, dict] = {}
        for r in dst_normalised:
            k = str(r.get(key_column, ""))
            dst_map[k] = r

        src_keys = set(src_map.keys())
        dst_keys = set(dst_map.keys())

        added_keys = dst_keys - src_keys
        removed_keys = src_keys - dst_keys
        common_keys = src_keys & dst_keys

        modified = 0
        unchanged = 0
        diff_details: list[dict] = []

        for k in sorted(common_keys):
            if src_map[k] != dst_map[k]:
                modified += 1
                if len(diff_details) < 100:  # cap detail
                    diff_details.append(
                        {
                            "key": k,
                            "old": src_map[k],
                            "new": dst_map[k],
                        }
                    )
            else:
                unchanged += 1

        added = len(added_keys)
        removed = len(removed_keys)

        summary = {
            "key_column": key_column,
            "sample_changes": diff_details,
            "added_keys": sorted(added_keys)[:50],
            "removed_keys": sorted(removed_keys)[:50],
        }

        return await self._save_diff(
            catalog_id,
            src_ver.id,
            dst_ver.id,
            source_version,
            target_version,
            added,
            removed,
            modified,
            unchanged,
            key_column=key_column,
            diff_summary=json.dumps(summary),
        )

    async def get_diff(
        self,
        diff_id: int,
    ) -> DataLakeDiff | None:
        result = await self.session.execute(select(DataLakeDiff).where(DataLakeDiff.id == diff_id))
        return result.scalar_one_or_none()

    async def list_diffs(
        self,
        catalog_id: int | None = None,
        limit: int = 50,
    ) -> list[DataLakeDiff]:
        stmt = select(DataLakeDiff).order_by(
            DataLakeDiff.created_at.desc(),
        )
        if catalog_id:
            stmt = stmt.where(DataLakeDiff.catalog_id == catalog_id)
        stmt = stmt.limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def _save_diff(
        self,
        catalog_id: int,
        source_version_id: int,
        target_version_id: int,
        source_version: str,
        target_version: str,
        added: int,
        removed: int,
        modified: int,
        unchanged: int,
        key_column: str | None = None,
        diff_summary: str | None = None,
    ) -> DataLakeDiff:
        entry = DataLakeDiff(
            catalog_id=catalog_id,
            source_version_id=source_version_id,
            target_version_id=target_version_id,
            source_version=source_version,
            target_version=target_version,
            added_count=added,
            removed_count=removed,
            modified_count=modified,
            unchanged_count=unchanged,
            diff_summary=diff_summary,
            key_column=key_column,
        )
        self.session.add(entry)
        await self.session.commit()
        await self.session.refresh(entry)
        return entry


class ChecksumMixin:
    async def verify_checksum(self, catalog_id: int, version: str) -> dict[str, Any]:
        ver = await self.get_version(catalog_id, version)
        if not ver:
            raise ValueError(f"Version {version} not found for catalog {catalog_id}")

        cat = await self.get_dataset(dataset_id=catalog_id)
        if not cat:
            raise ValueError(f"Catalog {catalog_id} not found")

        rows = storage.load_dataset(cat.layer, cat.name, version=version)

        content = json.dumps(rows, default=str).encode("utf-8")
        actual = hashlib.sha256(content).hexdigest()[:32]
        stored = ver.checksum or ""

        return {
            "catalog_id": catalog_id,
            "version": version,
            "stored_checksum": stored,
            "actual_checksum": actual,
            "match": actual == stored,
            "row_count": len(rows),
        }
