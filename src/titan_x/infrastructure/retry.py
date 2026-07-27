import asyncio
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

import structlog

logger = structlog.get_logger(__name__)

F = TypeVar("F", bound=Callable[..., Awaitable[Any]])


@dataclass
class RetryConfig:
    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    jitter: bool = True
    backoff_factor: float = 2.0


def retry_async(config: RetryConfig) -> Callable[[F], F]:
    def decorator(func: F) -> F:
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exc: Exception | None = None
            for attempt in range(1, config.max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as exc:
                    last_exc = exc
                    if attempt == config.max_attempts:
                        logger.error("retry_exhausted", func=func.__name__, attempts=attempt, error=str(exc))
                        raise
                    delay: float = min(config.base_delay * (config.backoff_factor ** (attempt - 1)), config.max_delay)
                    if config.jitter:
                        delay = delay * (0.5 + random.random() * 0.5)
                    logger.warning("retry_attempt", func=func.__name__, attempt=attempt, delay_seconds=round(delay, 2), error=str(exc))
                    await asyncio.sleep(delay)
            raise last_exc  # type: ignore[misc]
        return wrapper  # type: ignore[return-value]
    return decorator
