import json
from collections.abc import Sequence
from datetime import datetime
from typing import Any

import structlog
from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.db.repository import BaseRepository
from titan_x.models.strategy import Strategy, StrategyShare
from titan_x.services.advanced_screener_service import AdvancedScreenerService

logger = structlog.get_logger(__name__)


class StrategyService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = BaseRepository(session, Strategy)
        self._share_repo = BaseRepository(session, StrategyShare)
        self._screener = AdvancedScreenerService(session)

    async def get_strategy(self, strategy_id: int, user_id: int) -> dict[str, Any] | None:
        strategy = await self._repo.get(strategy_id)
        if strategy is None:
            return None
        if strategy.user_id == user_id or strategy.is_public:
            return self._to_dict(strategy)
        if await self._has_share_access(strategy_id, user_id):
            return self._to_dict(strategy)
        return None

    async def list_user_strategies(
        self, user_id: int, include_public: bool = True,
        skip: int = 0, limit: int = 20,
    ) -> tuple[Sequence[Strategy], int]:
        conditions = [Strategy.user_id == user_id]
        if include_public:
            shared_ids_subq = (
                select(StrategyShare.strategy_id)
                .where(StrategyShare.shared_with_user_id == user_id)
            ).scalar_subquery()
            conditions.append(Strategy.id.in_(shared_ids_subq))
            conditions.append(Strategy.is_public.is_(True))
        stmt = select(Strategy).where(or_(*conditions)).order_by(desc(Strategy.updated_at))
        count_stmt = select(func.count()).select_from(Strategy).where(or_(*conditions))
        total = (await self._session.execute(count_stmt)).scalar() or 0
        stmt = stmt.offset(skip).limit(limit)
        rows = (await self._session.execute(stmt)).scalars().all()
        return rows, total

    async def clone_strategy(
        self, strategy_id: int, user_id: int,
        new_name: str | None = None,
    ) -> dict[str, Any] | None:
        original = await self._repo.get(strategy_id)
        if original is None:
            return None
        if original.user_id != user_id and not original.is_public:
            has_access = await self._has_share_access(strategy_id, user_id)
            if not has_access:
                return None
        name = new_name or f"{original.name} (clone)"
        cloned = await self._repo.create(
            user_id=user_id,
            name=name,
            description=original.description,
            entry_criteria_json=original.entry_criteria_json,
            exit_criteria_json=original.exit_criteria_json,
            risk_rules_json=original.risk_rules_json,
            position_rules_json=original.position_rules_json,
            filters_json=original.filters_json,
            tags_json=original.tags_json,
            version=1,
            is_active=True,
            is_public=False,
            cloned_from_id=strategy_id,
        )
        return self._to_dict(cloned)

    async def update_strategy(
        self, strategy_id: int, user_id: int,
        name: str | None = None, description: str | None = None,
        entry_criteria: list[dict[str, Any]] | None = None,
        exit_criteria: list[dict[str, Any]] | None = None,
        risk_rules: dict[str, Any] | None = None,
        position_rules: dict[str, Any] | None = None,
        filters: dict[str, Any] | None = None,
        tags: list[str] | None = None,
        is_active: bool | None = None,
        is_public: bool | None = None,
        schedule_cron: str | None = None,
        schedule_enabled: bool | None = None,
    ) -> dict[str, Any] | None:
        strategy = await self._repo.get(strategy_id)
        if strategy is None or strategy.user_id != user_id:
            return None
        if name is not None:
            strategy.name = name
        if description is not None:
            strategy.description = description
        if entry_criteria is not None:
            strategy.entry_criteria_json = json.dumps(entry_criteria)
        if exit_criteria is not None:
            strategy.exit_criteria_json = json.dumps(exit_criteria)
        if risk_rules is not None:
            strategy.risk_rules_json = json.dumps(risk_rules)
        if position_rules is not None:
            strategy.position_rules_json = json.dumps(position_rules)
        if filters is not None:
            strategy.filters_json = json.dumps(filters)
        if tags is not None:
            strategy.tags_json = json.dumps(tags)
        if is_active is not None:
            strategy.is_active = is_active
        if is_public is not None:
            strategy.is_public = is_public
        if schedule_cron is not None:
            strategy.schedule_cron = schedule_cron
        if schedule_enabled is not None:
            strategy.schedule_enabled = schedule_enabled
        strategy.version += 1
        await self._session.flush()
        await self._session.refresh(strategy)
        return self._to_dict(strategy)

    async def delete_strategy(self, strategy_id: int, user_id: int) -> bool:
        strategy = await self._repo.get(strategy_id)
        if strategy is None or strategy.user_id != user_id:
            return False
        await self._session.delete(strategy)
        await self._session.flush()
        return True

    async def run_strategy(
        self, strategy_id: int, user_id: int,
        skip: int = 0, limit: int = 50,
    ) -> dict[str, Any] | None:
        strategy = await self._repo.get(strategy_id)
        if strategy is None:
            return None
        if strategy.user_id != user_id and not strategy.is_public:
            has_access = await self._has_share_access(strategy_id, user_id)
            if not has_access:
                return None
        if not strategy.filters_json:
            return {"total": 0, "skip": skip, "limit": limit, "results": [], "filters_applied": []}
        filters = json.loads(strategy.filters_json)
        result = await self._screener.run_screen(filters, user_id, strategy_id, skip, limit)
        strategy.last_run_at = func.now()
        strategy.last_results_count = result["total"]
        await self._session.flush()
        await self._session.refresh(strategy)
        return result

    async def share_strategy(
        self, strategy_id: int, owner_id: int,
        target_user_id: int, permission: str = "view",
    ) -> dict[str, Any] | None:
        strategy = await self._repo.get(strategy_id)
        if strategy is None or strategy.user_id != owner_id:
            return None
        if target_user_id == owner_id:
            return None
        existing = await self._session.execute(
            select(StrategyShare).where(
                StrategyShare.strategy_id == strategy_id,
                StrategyShare.shared_with_user_id == target_user_id,
            )
        )
        existing_share = existing.scalar_one_or_none()
        if existing_share:
            existing_share.permission = permission
            await self._session.flush()
            return {"id": existing_share.id, "strategy_id": strategy_id, "shared_with_user_id": target_user_id, "permission": permission}
        share = await self._share_repo.create(
            strategy_id=strategy_id,
            shared_by_user_id=owner_id,
            shared_with_user_id=target_user_id,
            permission=permission,
        )
        return {"id": share.id, "strategy_id": strategy_id, "shared_with_user_id": target_user_id, "permission": permission}

    async def unshare_strategy(
        self, strategy_id: int, owner_id: int, target_user_id: int,
    ) -> bool:
        strategy = await self._repo.get(strategy_id)
        if strategy is None or strategy.user_id != owner_id:
            return False
        share = await self._session.execute(
            select(StrategyShare).where(
                StrategyShare.strategy_id == strategy_id,
                StrategyShare.shared_with_user_id == target_user_id,
            )
        )
        share_obj = share.scalar_one_or_none()
        if share_obj is None:
            return False
        await self._session.delete(share_obj)
        await self._session.flush()
        return True

    async def list_shares(
        self, strategy_id: int, owner_id: int,
    ) -> list[dict[str, Any]]:
        strategy = await self._repo.get(strategy_id)
        if strategy is None or strategy.user_id != owner_id:
            return []
        rows = await self._session.execute(
            select(StrategyShare).where(
                StrategyShare.strategy_id == strategy_id,
            )
        )
        return [{
            "id": r.id,
            "shared_with_user_id": r.shared_with_user_id,
            "permission": r.permission,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        } for r in rows.scalars().all()]

    async def set_schedule(
        self, strategy_id: int, user_id: int,
        cron: str | None, enabled: bool = True,
    ) -> dict[str, Any] | None:
        strategy = await self._repo.get(strategy_id)
        if strategy is None or strategy.user_id != user_id:
            return None
        strategy.schedule_cron = cron
        strategy.schedule_enabled = enabled
        await self._session.flush()
        await self._session.refresh(strategy)
        return self._to_dict(strategy)

    async def _has_share_access(self, strategy_id: int, user_id: int) -> bool:
        result = await self._session.execute(
            select(StrategyShare).where(
                StrategyShare.strategy_id == strategy_id,
                StrategyShare.shared_with_user_id == user_id,
            )
        )
        return result.scalar_one_or_none() is not None

    def _to_dict(self, strategy: Strategy) -> dict[str, Any]:
        return {
            "id": strategy.id,
            "user_id": strategy.user_id,
            "name": strategy.name,
            "description": strategy.description,
            "entry_criteria_json": strategy.entry_criteria_json,
            "exit_criteria_json": strategy.exit_criteria_json,
            "risk_rules_json": strategy.risk_rules_json,
            "position_rules_json": strategy.position_rules_json,
            "filters_json": strategy.filters_json,
            "tags_json": strategy.tags_json,
            "version": strategy.version,
            "is_active": strategy.is_active,
            "is_public": strategy.is_public,
            "cloned_from_id": strategy.cloned_from_id,
            "schedule_cron": strategy.schedule_cron,
            "schedule_enabled": strategy.schedule_enabled,
            "last_run_at": strategy.last_run_at.isoformat() if strategy.last_run_at else None,
            "last_results_count": strategy.last_results_count,
            "created_at": strategy.created_at.isoformat() if strategy.created_at else None,
            "updated_at": strategy.updated_at.isoformat() if strategy.updated_at else None,
        }
