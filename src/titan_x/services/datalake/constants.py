"""Shared constants and layer validators for the data lake service mixins."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from titan_x.models.data_lake import DATALAKE_LAYERS

VALID_TRANSFORMATIONS = (
    "ingest",
    "validate",
    "normalize",
    "feature_engineer",
    "predict",
    "archive",
    "restore",
    "copy",
    "merge",
    "filter",
)

PIPELINE_STATUSES = ("pending", "running", "completed", "failed", "cancelled")


def _validate_layer(layer: str) -> None:
    if layer not in DATALAKE_LAYERS:
        raise ValueError(f"Invalid layer '{layer}'. Must be one of {DATALAKE_LAYERS}")


def _serialize_dt(val: Any) -> str | None:
    if isinstance(val, date | datetime):
        return val.isoformat()
    return val
