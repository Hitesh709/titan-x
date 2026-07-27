import json
import time
import uuid
from collections.abc import Sequence
from datetime import date, datetime, timezone
from typing import Any

import structlog
from croniter import croniter
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.db.repository import BaseRepository
from titan_x.models.strategy import Strategy, StrategyExecution, StrategyShare
from titan_x.services.advanced_screener_service import AdvancedScreenerService

logger = structlog.get_logger(__name__)


class StrategyExecutionService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._exec_repo = BaseRepository(session, StrategyExecution)
        self._screener = AdvancedScreenerService(session)

    async def execute_strategy(
        self, strategy_id: int, user_id: int,
        execution_type: str = "manual",
        as_of_date: date | None = None,
        batch_id: str | None = None,
    ) -> dict[str, Any] | None:
        strategy = await self._session.get(Strategy, strategy_id)
        if strategy is None:
            return None
        if strategy.user_id != user_id and not strategy.is_public:
            has_share = await self._session.execute(
                select(StrategyShare).where(
                    StrategyShare.strategy_id == strategy_id,
                    StrategyShare.shared_with_user_id == user_id,
                )
            )
            if not has_share.scalar_one_or_none():
                return None

        exec_type = execution_type or "manual"
        batch = batch_id or (str(uuid.uuid4()) if exec_type == "batch" else None)

        execution = await self._exec_repo.create(
            strategy_id=strategy_id,
            user_id=user_id,
            execution_type=exec_type,
            batch_id=batch,
            as_of_date=as_of_date,
            status="running",
            total_results=0,
            started_at=datetime.now(timezone.utc),
        )
        await self._session.flush()

        start_ms = int(time.time() * 1000)
        error_message: str | None = None
        result: dict[str, Any] | None = None

        try:
            if not strategy.filters_json:
                filters_dict: dict[str, Any] = {}
            else:
                filters_dict = json.loads(strategy.filters_json)

            result = await self._screener.run_screen(
                filters_dict, user_id, strategy_id,
                as_of_date=as_of_date,
            )

            total = result["total"]
            now_utc = datetime.now(timezone.utc)
            strategy.last_run_at = now_utc
            strategy.last_results_count = total

            end_ms = int(time.time() * 1000)
            execution.status = "completed"
            execution.total_results = total
            execution.results_json = json.dumps(result.get("results", []))
            execution.filters_applied_json = json.dumps(result.get("filters_applied", []))
            execution.completed_at = now_utc
            execution.execution_time_ms = end_ms - start_ms

        except Exception as e:
            end_ms = int(time.time() * 1000)
            error_message = str(e)
            execution.status = "failed"
            execution.error_message = error_message
            execution.completed_at = datetime.now(timezone.utc)
            execution.execution_time_ms = end_ms - start_ms
            logger.error("strategy_execution_failed", strategy_id=strategy_id, error=error_message)

        await self._session.flush()
        await self._session.refresh(execution)
        return self._execution_to_dict(execution, result)

    async def execute_batch(
        self, strategy_ids: list[int], user_id: int,
        as_of_date: date | None = None,
    ) -> list[dict[str, Any]]:
        batch_id = str(uuid.uuid4())
        results: list[dict[str, Any]] = []
        for sid in strategy_ids:
            r = await self.execute_strategy(
                sid, user_id, execution_type="batch",
                as_of_date=as_of_date, batch_id=batch_id,
            )
            if r is not None:
                results.append(r)
        return results

    async def execute_scheduled(self) -> list[dict[str, Any]]:
        now = datetime.now(timezone.utc)
        rows = await self._session.execute(
            select(Strategy).where(
                Strategy.schedule_enabled.is_(True),
                Strategy.schedule_cron.isnot(None),
                Strategy.filters_json.isnot(None),
            )
        )
        results: list[dict[str, Any]] = []
        for strategy in rows.scalars().all():
            try:
                cron = strategy.schedule_cron
                if not cron:
                    continue
                last = strategy.last_run_at
                if last is not None and last.tzinfo is None:
                    last = last.replace(tzinfo=timezone.utc)
                if not croniter.is_valid(cron):
                    logger.warning("invalid_cron", strategy_id=strategy.id, cron=cron)
                    continue
                if last is not None and not croniter.match(cron, last):
                    continue
                if last is not None and croniter.match(cron, now):
                    if last is not None and (now - last).total_seconds() < 60:
                        continue
                r = await self.execute_strategy(
                    strategy.id, strategy.user_id,
                    execution_type="scheduled",
                )
                if r is not None:
                    results.append(r)
            except Exception as e:
                logger.error("scheduled_execution_error", strategy_id=strategy.id, error=str(e))
        return results

    async def get_executions(
        self, strategy_id: int, user_id: int,
        skip: int = 0, limit: int = 20,
    ) -> tuple[Sequence[StrategyExecution], int]:
        strategy = await self._session.get(Strategy, strategy_id)
        if strategy is None:
            return [], 0
        if strategy.user_id != user_id:
            has_share = await self._session.execute(
                select(StrategyShare).where(
                    StrategyShare.strategy_id == strategy_id,
                    StrategyShare.shared_with_user_id == user_id,
                )
            )
            if not has_share.scalar_one_or_none() and not strategy.is_public:
                return [], 0
        count_stmt = select(func.count()).select_from(StrategyExecution).where(
            StrategyExecution.strategy_id == strategy_id,
        )
        total = (await self._session.execute(count_stmt)).scalar() or 0
        stmt = (
            select(StrategyExecution)
            .where(StrategyExecution.strategy_id == strategy_id)
            .order_by(desc(StrategyExecution.started_at))
            .offset(skip).limit(limit)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return list(rows), total

    async def get_execution(
        self, execution_id: int, user_id: int,
    ) -> dict[str, Any] | None:
        execution = await self._exec_repo.get(execution_id)
        if execution is None:
            return None
        strategy = await self._session.get(Strategy, execution.strategy_id)
        if strategy is None:
            return None
        if strategy.user_id != user_id and not strategy.is_public:
            has_share = await self._session.execute(
                select(StrategyShare).where(
                    StrategyShare.strategy_id == execution.strategy_id,
                    StrategyShare.shared_with_user_id == user_id,
                )
            )
            if not has_share.scalar_one_or_none():
                return None
        return self._execution_to_dict(execution)

    async def get_batch_executions(
        self, batch_id: str, user_id: int,
    ) -> list[dict[str, Any]]:
        rows = await self._session.execute(
            select(StrategyExecution).where(
                StrategyExecution.batch_id == batch_id,
            ).order_by(StrategyExecution.started_at)
        )
        executions = rows.scalars().all()
        if not executions:
            return []
        result: list[dict[str, Any]] = []
        for ex in executions:
            strategy = await self._session.get(Strategy, ex.strategy_id)
            if strategy and (strategy.user_id == user_id or strategy.is_public):
                result.append(self._execution_to_dict(ex))
        return result

    def _execution_to_dict(
        self, execution: StrategyExecution,
        screen_result: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "id": execution.id,
            "strategy_id": execution.strategy_id,
            "user_id": execution.user_id,
            "execution_type": execution.execution_type,
            "batch_id": execution.batch_id,
            "as_of_date": execution.as_of_date.isoformat() if execution.as_of_date else None,
            "status": execution.status,
            "total_results": execution.total_results,
            "results": json.loads(execution.results_json) if execution.results_json else (screen_result.get("results") if screen_result else None),
            "filters_applied": json.loads(execution.filters_applied_json) if execution.filters_applied_json else (screen_result.get("filters_applied") if screen_result else None),
            "error_message": execution.error_message,
            "started_at": execution.started_at.isoformat() if execution.started_at else None,
            "completed_at": execution.completed_at.isoformat() if execution.completed_at else None,
            "execution_time_ms": execution.execution_time_ms,
        }
