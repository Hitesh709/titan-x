import time
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any

import structlog

from titan_x.infrastructure.retry import RetryConfig, retry_async

logger = structlog.get_logger(__name__)


class JobError(Exception):
    pass


class BaseJob:
    def __init__(self, name: str, max_retries: int = 3, retry_delay: int = 60) -> None:
        self.name = name
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._log = logger.bind(job_name=name)

    async def execute(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        self._log.info("job_started", payload=payload)
        start: float = time.monotonic()
        try:
            retry_config = RetryConfig(
                max_attempts=self.max_retries + 1,
                base_delay=self.retry_delay,
                max_delay=3600,
                jitter=True,
            )
            result: dict[str, Any] = await retry_async(retry_config)(self._run)(payload or {})
            elapsed: float = time.monotonic() - start
            self._log.info("job_completed", duration_ms=int(elapsed * 1000))
            return {"status": "success", "duration_ms": int(elapsed * 1000), **result}
        except Exception as exc:
            elapsed = time.monotonic() - start
            self._log.error("job_failed", error=str(exc), duration_ms=int(elapsed * 1000))
            return {"status": "failed", "error": str(exc), "duration_ms": int(elapsed * 1000)}

    async def _run(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError


class ScheduledJob(BaseJob):
    def __init__(self, name: str, schedule_type: str, max_retries: int = 3, retry_delay: int = 60) -> None:
        super().__init__(name, max_retries, retry_delay)
        self.schedule_type = schedule_type
