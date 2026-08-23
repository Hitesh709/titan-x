import pytest
from titan_x.services.production_monitoring_service import ProductionMonitoringService


def test_health_and_overall_status() -> None:
    service = ProductionMonitoringService()
    service.record("api", status="HEALTHY", latency_ms=20)
    service.record("broker", status="DEGRADED", error_rate=2)
    assert service.overall_status() == "DEGRADED"
    service.record("broker", status="DOWN", error_rate=100)
    assert service.overall_status() == "DOWN"


def test_invalid_status() -> None:
    with pytest.raises(ValueError):
        ProductionMonitoringService().record("api", status="UNKNOWN")
