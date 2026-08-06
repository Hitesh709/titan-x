"""Time helpers enforcing a single timezone policy.

All application timestamps are UTC. ``utcnow()`` is the only entry point for
"now" so wall-clock/local-time drift cannot sneak into comparisons or
persisted values.
"""
from datetime import UTC, datetime


def utcnow() -> datetime:
    """Return the current UTC time as an aware datetime."""
    return datetime.now(UTC)


def ensure_aware(value: datetime) -> datetime:
    """Return ``value`` as an aware UTC datetime.

    SQLite stores ``DateTime(timezone=True)`` columns as naive values; this
    normalizes reads from any backend so they can be safely compared or
    subtracted against aware UTC timestamps.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


__all__ = ["utcnow", "ensure_aware"]
