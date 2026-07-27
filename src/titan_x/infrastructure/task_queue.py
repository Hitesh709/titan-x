import asyncio
import json
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import structlog
from redis.asyncio import Redis

logger = structlog.get_logger(__name__)


class TaskQueue:
    def __init__(self, redis: Redis, prefix: str = "q") -> None:
        self._redis = redis
        self._prefix = prefix

    def _queue_key(self, queue_name: str) -> str:
        return f"{self._prefix}:{queue_name}"

    def _processing_key(self, queue_name: str) -> str:
        return f"{self._prefix}:{queue_name}:processing"

    def _retry_key(self, queue_name: str) -> str:
        return f"{self._prefix}:{queue_name}:retry"

    async def enqueue(self, queue_name: str, task_type: str, payload: dict[str, Any], delay_seconds: int = 0) -> str:
        task_id: str = str(uuid.uuid4())
        task: dict[str, Any] = {
            "id": task_id,
            "type": task_type,
            "payload": payload,
            "created_at": time.time(),
            "retries": 0,
        }
        serialized: str = json.dumps(task, default=str)

        if delay_seconds > 0:
            await self._redis.zadd(self._retry_key(queue_name), {serialized: time.time() + delay_seconds})
        else:
            await self._redis.lpush(self._queue_key(queue_name), serialized)

        return task_id

    async def dequeue(self, queue_name: str, timeout: int = 5) -> dict[str, Any] | None:
        result: list[Any] = await self._redis.brpop(self._queue_key(queue_name), timeout=timeout)
        if result is None:
            return None
        _, serialized = result
        return json.loads(serialized)  # type: ignore[no-any-return]

    async def acknowledge(self, queue_name: str, task_id: str) -> None:
        await self._redis.srem(self._processing_key(queue_name), task_id)

    async def requeue(self, queue_name: str, task: dict[str, Any], delay_seconds: int = 0) -> None:
        task["retries"] = task.get("retries", 0) + 1
        serialized: str = json.dumps(task, default=str)
        if delay_seconds > 0:
            await self._redis.zadd(self._retry_key(queue_name), {serialized: time.time() + delay_seconds})
        else:
            await self._redis.lpush(self._queue_key(queue_name), serialized)

    async def move_delayed_to_ready(self, queue_name: str) -> int:
        now: float = time.time()
        ready: list[Any] = await self._redis.zrangebyscore(self._retry_key(queue_name), 0, now)
        if not ready:
            return 0
        pipe = self._redis.pipeline()
        for task_data in ready:
            pipe.lpush(self._queue_key(queue_name), task_data)
        pipe.zremrangebyscore(self._retry_key(queue_name), 0, now)
        results: list[Any] = await pipe.execute()
        return len(ready)

    async def queue_size(self, queue_name: str) -> int:
        return await self._redis.llen(self._queue_key(queue_name))

    async def close(self) -> None:
        await self._redis.aclose()


class Worker:
    def __init__(
        self,
        task_queue: TaskQueue,
        queue_name: str,
        handler: Callable[[dict[str, Any]], Awaitable[None]],
        poll_interval: int = 1,
        max_retries: int = 3,
    ) -> None:
        self._queue = task_queue
        self._queue_name = queue_name
        self._handler = handler
        self._poll_interval = poll_interval
        self._max_retries = max_retries
        self._running = False

    async def start(self) -> None:
        self._running = True
        logger.info("worker_started", queue=self._queue_name)
        while self._running:
            try:
                await self._queue.move_delayed_to_ready(self._queue_name)
                task: dict[str, Any] | None = await self._queue.dequeue(self._queue_name, timeout=self._poll_interval)
                if task is None:
                    continue
                await self._process(task)
            except Exception:
                logger.exception("worker_loop_error", queue=self._queue_name)

    async def _process(self, task: dict[str, Any]) -> None:
        logger.info("worker_processing", task_id=task.get("id"), task_type=task.get("type"), queue=self._queue_name)
        try:
            await self._handler(task)
            await self._queue.acknowledge(self._queue_name, task.get("id", ""))
            logger.info("worker_completed", task_id=task.get("id"), queue=self._queue_name)
        except Exception as exc:
            retries: int = task.get("retries", 0)
            if retries < self._max_retries:
                logger.warning("worker_retrying", task_id=task.get("id"), retries=retries + 1, queue=self._queue_name)
                await self._queue.requeue(self._queue_name, task, delay_seconds=2 ** (retries + 1))
            else:
                logger.error("worker_failed", task_id=task.get("id"), error=str(exc), queue=self._queue_name)

    async def stop(self) -> None:
        self._running = False
        logger.info("worker_stopped", queue=self._queue_name)
