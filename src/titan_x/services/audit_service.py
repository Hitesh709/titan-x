import json
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.models.audit import AuditLog

CATEGORIES = {
    "api_call": "API request/response",
    "user_action": "User-initiated action (login, logout, etc.)",
    "ai_decision": "AI-generated trading decision",
    "config_change": "Configuration or preference change",
    "security_event": "Security-related event (failed login, etc.)",
}

SEVERITY_INFO = "info"
SEVERITY_WARNING = "warning"
SEVERITY_CRITICAL = "critical"


class AuditService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def log(
        self,
        action: str,
        entity_type: str,
        entity_id: int | None = None,
        user_id: int | None = None,
        details_json: str | None = None,
        ip_address: str | None = None,
        category: str = "api_call",
        severity: str = "info",
    ) -> AuditLog:
        entry = AuditLog(
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details_json=details_json,
            ip_address=ip_address,
            category=category,
            severity=severity,
        )
        self.session.add(entry)
        await self.session.flush()
        await self.session.refresh(entry)
        return entry

    async def log_api_call(
        self, user_id: int | None, method: str, path: str,
        status_code: int, ip_address: str | None = None,
        query_string: str = "", duration_ms: int | None = None,
    ) -> AuditLog:
        details = {"method": method, "path": path, "status_code": status_code}
        if query_string:
            details["query"] = query_string
        if duration_ms is not None:
            details["duration_ms"] = duration_ms
        severity = SEVERITY_INFO if status_code < 400 else SEVERITY_WARNING if status_code < 500 else SEVERITY_CRITICAL
        return await self.log(
            action=method.lower(),
            entity_type="api_call",
            user_id=user_id,
            details_json=json.dumps(details),
            ip_address=ip_address,
            category="api_call",
            severity=severity,
        )

    async def log_user_action(
        self, user_id: int, action: str, details: dict[str, Any] | None = None,
        ip_address: str | None = None,
    ) -> AuditLog:
        return await self.log(
            action=action,
            entity_type="user_action",
            user_id=user_id,
            details_json=json.dumps(details) if details else None,
            ip_address=ip_address,
            category="user_action",
            severity=SEVERITY_INFO,
        )

    async def log_ai_decision(
        self, symbol: str, direction: str, confidence: float | None = None,
        reasoning: str | None = None, user_id: int | None = None,
    ) -> AuditLog:
        details = {"symbol": symbol, "direction": direction}
        if confidence is not None:
            details["confidence"] = confidence
        if reasoning:
            details["reasoning"] = reasoning
        return await self.log(
            action=f"ai_{direction}",
            entity_type="ai_decision",
            entity_id=None,
            user_id=user_id,
            details_json=json.dumps(details),
            category="ai_decision",
            severity=SEVERITY_INFO,
        )

    async def log_config_change(
        self, user_id: int, config_key: str,
        old_value: str | None = None, new_value: str | None = None,
    ) -> AuditLog:
        details = {"config_key": config_key}
        if old_value is not None:
            details["old_value"] = old_value
        if new_value is not None:
            details["new_value"] = new_value
        return await self.log(
            action="config_change",
            entity_type="config",
            user_id=user_id,
            details_json=json.dumps(details),
            category="config_change",
            severity=SEVERITY_WARNING,
        )

    async def log_security_event(
        self, action: str, details: dict[str, Any] | None = None,
        user_id: int | None = None, ip_address: str | None = None,
        severity: str = "warning",
    ) -> AuditLog:
        return await self.log(
            action=action,
            entity_type="security_event",
            user_id=user_id,
            details_json=json.dumps(details) if details else None,
            ip_address=ip_address,
            category="security_event",
            severity=severity,
        )

    async def list_logs(
        self,
        user_id: int | None = None,
        action: str | None = None,
        entity_type: str | None = None,
        category: str | None = None,
        severity: str | None = None,
        limit: int = 50,
        offset: int = 0,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> tuple[Sequence[AuditLog], int]:
        base = select(AuditLog)
        filters = []
        if user_id is not None:
            filters.append(AuditLog.user_id == user_id)
        if action is not None:
            filters.append(AuditLog.action == action)
        if entity_type is not None:
            filters.append(AuditLog.entity_type == entity_type)
        if category is not None:
            filters.append(AuditLog.category == category)
        if severity is not None:
            filters.append(AuditLog.severity == severity)
        if since is not None:
            filters.append(AuditLog.created_at >= since)
        if until is not None:
            filters.append(AuditLog.created_at <= until)

        count_q = base.where(*filters) if filters else base
        q = base.where(*filters).order_by(AuditLog.created_at.desc()).offset(offset).limit(limit) if filters else base.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit)

        total = (await self.session.execute(select(func.count()).select_from(count_q.subquery()))).scalar() or 0
        result = await self.session.execute(q)
        rows = list(result.scalars().all())
        return rows, total

    async def get_stats(
        self, user_id: int | None = None,
        category: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> dict[str, Any]:
        base = select(AuditLog)
        filters = []
        if user_id is not None:
            filters.append(AuditLog.user_id == user_id)
        if category is not None:
            filters.append(AuditLog.category == category)
        if since is not None:
            filters.append(AuditLog.created_at >= since)
        if until is not None:
            filters.append(AuditLog.created_at <= until)

        where_clause = filters if filters else None

        total_q = select(func.count()).select_from(AuditLog)
        if where_clause:
            total_q = total_q.where(*where_clause)
        total = (await self.session.execute(total_q)).scalar() or 0

        by_category_q = (
            select(AuditLog.category, func.count().label("cnt"))
            .group_by(AuditLog.category)
        )
        if where_clause:
            by_category_q = by_category_q.where(*where_clause)

        if user_id is not None:
            by_category_q = by_category_q.where(AuditLog.user_id == user_id)

        by_category_rows = (await self.session.execute(by_category_q)).all()
        by_category = {row[0]: row[1] for row in by_category_rows}

        by_severity_q = (
            select(AuditLog.severity, func.count().label("cnt"))
            .group_by(AuditLog.severity)
        )
        if where_clause:
            by_severity_q = by_severity_q.where(*where_clause)
        if user_id is not None:
            by_severity_q = by_severity_q.where(AuditLog.user_id == user_id)

        by_severity_rows = (await self.session.execute(by_severity_q)).all()
        by_severity = {row[0]: row[1] for row in by_severity_rows}

        return {
            "total_events": total,
            "by_category": by_category,
            "by_severity": by_severity,
        }
