from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable


@dataclass(frozen=True, slots=True)
class CircuitState:
    name: str
    state: str
    failures: int
    opened_at: str | None


class CircuitBreaker:
    def __init__(self, name: str, *, failure_threshold: int = 5, reset_after_seconds: float = 30.0):
        if failure_threshold <= 0 or reset_after_seconds < 0:
            raise ValueError("invalid circuit breaker configuration")
        self.name = name
        self.failure_threshold = failure_threshold
        self.reset_after_seconds = reset_after_seconds
        self.failures = 0
        self.state = "CLOSED"
        self.opened_at: float | None = None

    def allow(self) -> bool:
        if self.state != "OPEN":
            return True
        if self.opened_at is not None and datetime.now(timezone.utc).timestamp() - self.opened_at >= self.reset_after_seconds:
            self.state = "HALF_OPEN"
            return True
        return False

    def record_success(self) -> None:
        self.failures = 0
        self.state = "CLOSED"
        self.opened_at = None

    def record_failure(self) -> None:
        self.failures += 1
        if self.failures >= self.failure_threshold:
            self.state = "OPEN"
            self.opened_at = datetime.now(timezone.utc).timestamp()

    def snapshot(self) -> CircuitState:
        return CircuitState(self.name, self.state, self.failures, datetime.fromtimestamp(self.opened_at, timezone.utc).isoformat() if self.opened_at else None)


class FailureRecoveryService:
    def __init__(self, *, max_retries: int = 3):
        if max_retries < 0:
            raise ValueError("max_retries cannot be negative")
        self.max_retries = max_retries
        self._circuits: dict[str, CircuitBreaker] = {}

    def circuit(self, name: str) -> CircuitBreaker:
        return self._circuits.setdefault(name, CircuitBreaker(name))

    def call(self, name: str, operation: Callable[[], Any]) -> Any:
        breaker = self.circuit(name)
        if not breaker.allow():
            raise RuntimeError(f"circuit open: {name}")
        attempts = 0
        while True:
            try:
                result = operation()
                breaker.record_success()
                return result
            except Exception:
                breaker.record_failure()
                attempts += 1
                if attempts > self.max_retries:
                    raise

    def snapshot(self) -> list[dict[str, Any]]:
        return [c.snapshot().__dict__ for c in self._circuits.values()]
