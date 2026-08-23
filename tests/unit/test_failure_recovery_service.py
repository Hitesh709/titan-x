import pytest
from titan_x.services.failure_recovery_service import FailureRecoveryService


def test_retries_and_recovers() -> None:
    service = FailureRecoveryService(max_retries=2)
    attempts = {"n": 0}
    def operation():
        attempts["n"] += 1
        if attempts["n"] < 2:
            raise RuntimeError("temporary")
        return "ok"
    assert service.call("market-data", operation) == "ok"
    assert attempts["n"] == 2


def test_circuit_opens_after_failures() -> None:
    service = FailureRecoveryService(max_retries=0)
    def operation():
        raise RuntimeError("down")
    for _ in range(5):
        with pytest.raises(RuntimeError):
            service.call("broker", operation)
    with pytest.raises(RuntimeError, match="circuit open"):
        service.call("broker", lambda: "ok")
