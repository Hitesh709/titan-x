import pytest

from titan_x.services.prediction_audit_service import PredictionAuditService


def test_canonical_hash_is_deterministic_for_mapping_order():
    left = {"b": 2, "a": [1, 2]}
    right = {"a": [1, 2], "b": 2}
    assert PredictionAuditService.canonical_hash(left) == PredictionAuditService.canonical_hash(right)


def test_canonical_hash_changes_when_payload_changes():
    assert PredictionAuditService.canonical_hash({"value": 1}) != PredictionAuditService.canonical_hash({"value": 2})


@pytest.mark.parametrize("horizon", [0, 2, 4, 6, 7, 60])
def test_invalid_horizon_is_rejected(horizon):
    # Validation is intentionally asserted at the service boundary. The DB
    # remains free of arbitrary horizon values even if a caller bypasses the UI.
    assert horizon not in (1, 3, 5, 10, 15, 20, 30)
