from datetime import date
from unittest.mock import MagicMock

import pytest

from titan_x.services.prediction_audit_service import PredictionAuditService


def test_canonical_hash_is_deterministic_for_mapping_order() -> None:
    left = {"b": 2, "a": [1, 2]}
    right = {"a": [1, 2], "b": 2}
    assert PredictionAuditService.canonical_hash(left) == PredictionAuditService.canonical_hash(right)


def test_canonical_hash_changes_when_payload_changes() -> None:
    assert PredictionAuditService.canonical_hash({"value": 1}) != PredictionAuditService.canonical_hash(
        {"value": 2}
    )


@pytest.mark.parametrize("horizon", [0, 2, 4, 6, 7, 60])
@pytest.mark.asyncio
async def test_invalid_horizon_is_rejected(horizon: int) -> None:
    service = PredictionAuditService(MagicMock())
    with pytest.raises(ValueError, match="horizon_days"):
        await service.record_outcome(
            audit_id=1,
            horizon_days=horizon,
            observation_date=date(2026, 1, 15),
            entry_price=100.0,
            close_price=101.0,
        )
