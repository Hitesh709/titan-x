from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True, slots=True)
class ServiceHealth:
    service: str
    status: str
    latency_ms: float | None
    error_rate: float
    timestamp: str


class ProductionMonitoringService:
    def __init__(self) -> None:
        self._health: dict[str, ServiceHealth] = {}

    def record(self, service: str, *, status: str, latency_ms: float | None = None, error_rate: float = 0.0) -> ServiceHealth:
        status = status.upper()
        if status not in {"HEALTHY", "DEGRADED", "DOWN"}:
            raise ValueError("invalid health status")
        if error_rate < 0 or error_rate > 100:
            raise ValueError("error_rate must be between 0 and 100")
        health = ServiceHealth(service, status, latency_ms, float(error_rate), datetime.now(timezone.utc).isoformat())
        self._health[service] = health
        return health

    def snapshot(self) -> dict[str, Any]:
        return {name: asdict(value) for name, value in self._health.items()}

    def overall_status(self) -> str:
        statuses = {h.status for h in self._health.values()}
        if "DOWN" in statuses:
            return "DOWN"
        if "DEGRADED" in statuses:
            return "DEGRADED"
        return "HEALTHY"
