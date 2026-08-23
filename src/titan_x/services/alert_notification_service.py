from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable


@dataclass(frozen=True, slots=True)
class Alert:
    alert_id: str
    severity: str
    event_type: str
    message: str
    symbol: str | None
    timestamp: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


NotificationHandler = Callable[[Alert], None | Awaitable[None]]


class AlertNotificationService:
    """Centralized alert creation, deduplication and notification dispatch."""

    VALID_SEVERITIES = {"INFO", "WARNING", "CRITICAL"}

    def __init__(self, *, dedupe_seconds: float = 30.0) -> None:
        if dedupe_seconds < 0:
            raise ValueError("dedupe_seconds cannot be negative")
        self.dedupe_seconds = dedupe_seconds
        self._handlers: list[NotificationHandler] = []
        self._recent: dict[str, float] = {}
        self._history: list[Alert] = []
        self._counter = 0

    def add_handler(self, handler: NotificationHandler) -> None:
        self._handlers.append(handler)

    async def emit(self, *, severity: str, event_type: str, message: str, symbol: str | None = None) -> Alert | None:
        severity = severity.upper()
        if severity not in self.VALID_SEVERITIES:
            raise ValueError("invalid severity")
        if not event_type.strip() or not message.strip():
            raise ValueError("event_type and message are required")
        key = f"{severity}|{event_type}|{symbol or ''}|{message}"
        now = datetime.now(timezone.utc)
        now_epoch = now.timestamp()
        previous = self._recent.get(key)
        if previous is not None and now_epoch - previous < self.dedupe_seconds:
            return None
        self._recent[key] = now_epoch
        self._counter += 1
        alert = Alert(f"ALT-{self._counter:08d}", severity, event_type, message, symbol, now.isoformat())
        self._history.append(alert)
        for handler in tuple(self._handlers):
            try:
                result = handler(alert)
                if hasattr(result, "__await__"):
                    await result
            except Exception:
                continue
        return alert

    def history(self, *, limit: int = 100) -> list[dict[str, Any]]:
        if limit <= 0:
            return []
        return [a.to_dict() for a in self._history[-limit:]]
