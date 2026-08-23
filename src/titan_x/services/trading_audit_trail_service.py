from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True, slots=True)
class AuditEvent:
    event_id: str
    event_type: str
    actor: str
    symbol: str | None
    payload: dict[str, Any]
    timestamp: str
    previous_hash: str
    event_hash: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TradingAuditTrailService:
    """Append-only hash-chained audit trail for trading lifecycle events."""

    def __init__(self) -> None:
        self._events: list[AuditEvent] = []

    def record(self, *, event_type: str, actor: str, payload: dict[str, Any], symbol: str | None = None) -> AuditEvent:
        if not event_type.strip() or not actor.strip():
            raise ValueError("event_type and actor are required")
        previous_hash = self._events[-1].event_hash if self._events else "GENESIS"
        timestamp = datetime.now(timezone.utc).isoformat()
        event_id = str(uuid.uuid4())
        canonical = json.dumps({
            "event_id": event_id,
            "event_type": event_type,
            "actor": actor,
            "symbol": symbol,
            "payload": payload,
            "timestamp": timestamp,
            "previous_hash": previous_hash,
        }, sort_keys=True, separators=(",", ":"), default=str)
        event_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        event = AuditEvent(event_id, event_type, actor, symbol, dict(payload), timestamp, previous_hash, event_hash)
        self._events.append(event)
        return event

    def verify(self) -> bool:
        previous = "GENESIS"
        for event in self._events:
            if event.previous_hash != previous:
                return False
            canonical = json.dumps({
                "event_id": event.event_id,
                "event_type": event.event_type,
                "actor": event.actor,
                "symbol": event.symbol,
                "payload": event.payload,
                "timestamp": event.timestamp,
                "previous_hash": event.previous_hash,
            }, sort_keys=True, separators=(",", ":"), default=str)
            if hashlib.sha256(canonical.encode("utf-8")).hexdigest() != event.event_hash:
                return False
            previous = event.event_hash
        return True

    def list_events(self, *, limit: int = 100) -> list[dict[str, Any]]:
        if limit <= 0:
            return []
        return [event.to_dict() for event in self._events[-limit:]]

    def latest(self) -> AuditEvent | None:
        return self._events[-1] if self._events else None
