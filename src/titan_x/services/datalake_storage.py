"""Data Lake file storage layer.

Handles reading/writing partitioned datasets to the local filesystem
in Parquet, CSV, or JSON format.  All I/O is sync (blocking) because
pandas file operations are CPU-bound.  Callers wrap in run_in_executor
when used inside async contexts.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

BASE_LAKE_DIR: str | None = None


def get_lake_dir() -> str:
    if BASE_LAKE_DIR:
        return BASE_LAKE_DIR
    return os.environ.get(
        "DATALAKE_DIR",
        os.path.join(os.getcwd(), "data_lake"),
    )


def _ensure_dir(path: str) -> str:
    Path(path).mkdir(parents=True, exist_ok=True)
    return path


def _partition_path(
    layer: str,
    dataset_name: str,
    partition_date: date | None = None,
    version: str | None = None,
) -> str:
    parts = [get_lake_dir(), layer, dataset_name]
    if partition_date:
        parts.append(f"dt={partition_date.isoformat()}")
    if version:
        parts.append(f"ver={version}")
    return os.path.join(*parts)


def _compute_checksum(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()[:32]


def save_dataset(
    layer: str,
    dataset_name: str,
    rows: list[dict[str, Any]],
    partition_date: date | None = None,
    version: str | None = None,
    fmt: str = "parquet",
) -> dict[str, Any]:
    """Save rows as a dataset file on disk.

    Returns metadata dict with storage_path, file_size, row_count, checksum.
    """
    dir_path = _ensure_dir(_partition_path(layer, dataset_name, partition_date, version))
    file_id = uuid4().hex[:12]
    ext = {"parquet": ".parquet", "csv": ".csv", "json": ".json"}.get(fmt, ".parquet")
    filepath = os.path.join(dir_path, f"{file_id}{ext}")

    if fmt == "json":
        content = json.dumps(rows, default=str, indent=2).encode("utf-8")
        with open(filepath, "wb") as f:
            f.write(content)
    elif fmt == "csv":
        if rows:
            header = list(rows[0].keys())
            lines = [",".join(header)]
            for r in rows:
                lines.append(
                    ",".join(
                        str(r.get(k, "")).replace(",", ";") for k in header
                    )
                )
            content = "\n".join(lines).encode("utf-8")
        else:
            content = b""
        with open(filepath, "wb") as f:
            f.write(content)
    else:
        try:
            import pandas as pd
            df = pd.DataFrame(rows)
            df.to_parquet(filepath, index=False)
        except ImportError:
            content = json.dumps(rows, default=str).encode("utf-8")
            filepath = filepath.replace(".parquet", ".json")
            with open(filepath, "wb") as f:
                f.write(content)
        with open(filepath, "rb") as f:
            content = f.read()

    file_size = os.path.getsize(filepath)
    checksum = _compute_checksum(content)
    row_count = len(rows)

    return {
        "storage_path": filepath,
        "file_size": file_size,
        "row_count": row_count,
        "checksum": checksum,
        "file_format": fmt,
    }


def load_dataset(
    layer: str,
    dataset_name: str,
    partition_date: date | None = None,
    version: str | None = None,
) -> list[dict[str, Any]]:
    """Load all rows from a dataset directory.  Merges multiple files."""
    dir_path = _partition_path(layer, dataset_name, partition_date, version)
    if not os.path.isdir(dir_path):
        return []

    all_rows: list[dict[str, Any]] = []
    for fname in sorted(os.listdir(dir_path)):
        fpath = os.path.join(dir_path, fname)
        if not os.path.isfile(fpath):
            continue
        ext = os.path.splitext(fname)[1].lower()
        try:
            if ext == ".json":
                with open(fpath, "r") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        all_rows.extend(data)
                    else:
                        all_rows.append(data)
            elif ext == ".csv":
                with open(fpath, "r") as f:
                    lines = f.read().strip().split("\n")
                    if not lines:
                        continue
                    hdr = [h.strip() for h in lines[0].split(",")]
                    for line in lines[1:]:
                        vals = line.split(",")
                        all_rows.append(
                            {hdr[i]: vals[i] if i < len(vals) else "" for i in range(len(hdr))}
                        )
            elif ext == ".parquet":
                try:
                    import pandas as pd
                    df = pd.read_parquet(fpath)
                    all_rows.extend(df.to_dict(orient="records"))
                except ImportError:
                    pass
        except Exception:
            pass
    return all_rows


def load_dataset_by_path(path: str) -> list[dict[str, Any]]:
    """Load rows from a specific file or directory path."""
    if not os.path.exists(path):
        return []
    if os.path.isfile(path):
        return _load_file(path)
    if os.path.isdir(path):
        all_rows: list[dict[str, Any]] = []
        for fname in sorted(os.listdir(path)):
            fpath = os.path.join(path, fname)
            if os.path.isfile(fpath):
                all_rows.extend(_load_file(fpath))
        return all_rows
    return []


def _load_file(fpath: str) -> list[dict[str, Any]]:
    ext = os.path.splitext(fpath)[1].lower()
    try:
        if ext == ".json":
            with open(fpath, "r") as f:
                data = json.load(f)
                return data if isinstance(data, list) else [data]
        elif ext == ".csv":
            with open(fpath, "r") as f:
                lines = f.read().strip().split("\n")
                if not lines:
                    return []
                hdr = [h.strip() for h in lines[0].split(",")]
                result = []
                for line in lines[1:]:
                    vals = line.split(",")
                    result.append(
                        {hdr[i]: vals[i] if i < len(vals) else "" for i in range(len(hdr))}
                    )
                return result
        elif ext == ".parquet":
            import pandas as pd  # type: ignore
            df = pd.read_parquet(fpath)
            return df.to_dict(orient="records")
    except Exception:
        pass
    return []


def list_datasets(layer: str) -> list[dict[str, Any]]:
    """List all dataset directories within a given layer."""
    dir_path = os.path.join(get_lake_dir(), layer)
    if not os.path.isdir(dir_path):
        return []
    results = []
    for name in sorted(os.listdir(dir_path)):
        full = os.path.join(dir_path, name)
        if os.path.isdir(full):
            results.append({
                "name": name,
                "path": full,
                "file_count": len([
                    f for f in os.listdir(full)
                    if os.path.isfile(os.path.join(full, f))
                ]),
            })
    return results


def delete_dataset(
    layer: str,
    dataset_name: str,
    partition_date: date | None = None,
    version: str | None = None,
) -> bool:
    """Remove a dataset directory and all its files."""
    dir_path = _partition_path(layer, dataset_name, partition_date, version)
    if not os.path.isdir(dir_path):
        return False
    import shutil
    shutil.rmtree(dir_path)
    return True


def get_storage_stats() -> dict[str, Any]:
    """Return aggregate storage statistics for the entire data lake."""
    lake_dir = get_lake_dir()
    if not os.path.isdir(lake_dir):
        return {"total_size_bytes": 0, "total_files": 0, "layers": {}}

    total_size = 0
    total_files = 0
    layers: dict[str, dict] = {}

    for layer_name in sorted(os.listdir(lake_dir)):
        layer_path = os.path.join(lake_dir, layer_name)
        if not os.path.isdir(layer_path):
            continue
        layer_size = 0
        layer_files = 0
        for root, _dirs, files in os.walk(layer_path):
            for f in files:
                fpath = os.path.join(root, f)
                try:
                    layer_size += os.path.getsize(fpath)
                    layer_files += 1
                except OSError:
                    pass
        total_size += layer_size
        total_files += layer_files
        layers[layer_name] = {
            "size_bytes": layer_size,
            "file_count": layer_files,
        }

    return {
        "total_size_bytes": total_size,
        "total_files": total_files,
        "layers": layers,
    }
