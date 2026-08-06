"""Value objects shared by the market data collection pipeline."""
from dataclasses import dataclass, field


@dataclass
class SyncResult:
    total: int = 0
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    errors: int = 0
    error_message: str | None = None
    duration_ms: int | None = None


@dataclass
class ValidationOutcome:
    passed: bool = False
    checks_passed: int = 0
    checks_failed: int = 0
    errors: list[str] = field(default_factory=list)