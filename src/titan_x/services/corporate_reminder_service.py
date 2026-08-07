"""Corporate event reminders service.

Manages 7 event types: quarterly results, AGM, EGM, dividend,
stock split, bonus shares, rights issue. Generates proactive
reminder notifications for subscribed users.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

import structlog
from sqlalchemy import and_, delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from titan_x.models.trading_calendar import CorporateCalendar, CorporateReminder
from titan_x.services.notification_service import NotificationService

logger = structlog.get_logger(__name__)

EVENT_TYPES = frozenset({
    "quarterly", "agm", "egm", "dividend", "split", "bonus", "rights",
})


class CorporateReminderService:
    """Service for corporate event reminders."""

    def __init__(
        self, session: AsyncSession,
        notification_service: NotificationService | None = None,
    ) -> None:
        self.session = session
        self._notify = notification_service

    # ═════════════════════════════════════════════════════════════════════
    # Corporate Event Management
    # ═════════════════════════════════════════════════════════════════════

    async def register_event(
        self,
        symbol: str,
        event_type: str,
        announcement_date: date | None = None,
        record_date: date | None = None,
        ex_date: date | None = None,
        payment_date: date | None = None,
        board_meeting_date: date | None = None,
        meeting_date: date | None = None,
        description: str | None = None,
        details_json: str | None = None,
        source: str | None = None,
        is_confirmed: bool = False,
    ) -> CorporateCalendar:
        if event_type not in EVENT_TYPES:
            raise ValueError(
                f"Invalid event type '{event_type}'. Must be one of: "
                f"{', '.join(sorted(EVENT_TYPES))}",
            )
        entry = CorporateCalendar(
            symbol=symbol.upper(),
            event_type=event_type,
            announcement_date=announcement_date,
            record_date=record_date,
            ex_date=ex_date or board_meeting_date or meeting_date,
            payment_date=payment_date,
            description=description,
            details_json=details_json,
            source=source,
            is_confirmed=is_confirmed,
        )
        self.session.add(entry)
        await self.session.commit()
        await self.session.refresh(entry)
        return entry

    async def register_quarterly(
        self, symbol: str, board_meeting_date: date,
        quarter: int | None = None, fiscal_year: int | None = None,
        description: str | None = None, source: str | None = None,
    ) -> CorporateCalendar:
        import json
        details = {}
        if quarter is not None:
            details["quarter"] = quarter
        if fiscal_year is not None:
            details["fiscal_year"] = fiscal_year
        desc = description or (
            f"Q{quarter} FY{fiscal_year} Results Board Meeting"
            if quarter and fiscal_year else "Quarterly Results Board Meeting"
        )
        return await self.register_event(
            symbol=symbol, event_type="quarterly",
            board_meeting_date=board_meeting_date,
            description=desc,
            details_json=json.dumps(details) if details else None,
            source=source,
        )

    async def register_agm(
        self, symbol: str, meeting_date: date,
        venue: str | None = None, chairman: str | None = None,
        resolutions: str | None = None,
        book_closure_start: date | None = None,
        book_closure_end: date | None = None,
        source: str | None = None,
    ) -> CorporateCalendar:
        import json
        details: dict[str, Any] = {}
        if venue:
            details["venue"] = venue
        if chairman:
            details["chairman"] = chairman
        if resolutions:
            details["resolutions"] = resolutions
        if book_closure_start:
            details["book_closure_start"] = book_closure_start.isoformat()
        if book_closure_end:
            details["book_closure_end"] = book_closure_end.isoformat()
        return await self.register_event(
            symbol=symbol, event_type="agm",
            meeting_date=meeting_date,
            description=f"Annual General Meeting - {symbol}",
            details_json=json.dumps(details) if details else None,
            source=source,
        )

    async def register_egm(
        self, symbol: str, meeting_date: date,
        purpose: str | None = None, venue: str | None = None,
        source: str | None = None,
    ) -> CorporateCalendar:
        import json
        details: dict[str, Any] = {}
        if purpose:
            details["purpose"] = purpose
        if venue:
            details["venue"] = venue
        desc = purpose or f"Extraordinary General Meeting - {symbol}"
        return await self.register_event(
            symbol=symbol, event_type="egm",
            meeting_date=meeting_date,
            description=desc,
            details_json=json.dumps(details) if details else None,
            source=source,
        )

    async def register_dividend(
        self, symbol: str, ex_date: date,
        record_date: date | None = None,
        payment_date: date | None = None,
        amount_per_share: float | None = None,
        dividend_type: str | None = None,
        announcement_date: date | None = None,
        source: str | None = None,
    ) -> CorporateCalendar:
        import json
        details: dict[str, Any] = {}
        if amount_per_share is not None:
            details["amount_per_share"] = amount_per_share
        if dividend_type:
            details["dividend_type"] = dividend_type
        desc_parts = [f"Dividend - {symbol}"]
        if amount_per_share is not None:
            desc_parts.append(f"₹{amount_per_share}/share")
        if dividend_type:
            desc_parts.append(f"({dividend_type})")
        return await self.register_event(
            symbol=symbol, event_type="dividend",
            ex_date=ex_date, record_date=record_date,
            payment_date=payment_date,
            announcement_date=announcement_date,
            description=" ".join(desc_parts),
            details_json=json.dumps(details) if details else None,
            source=source,
        )

    async def register_split(
        self, symbol: str, ex_date: date,
        record_date: date | None = None,
        old_face_value: float | None = None,
        new_face_value: float | None = None,
        ratio_numerator: int | None = None,
        ratio_denominator: int | None = None,
        source: str | None = None,
    ) -> CorporateCalendar:
        import json
        details: dict[str, Any] = {}
        if old_face_value is not None:
            details["old_face_value"] = old_face_value
        if new_face_value is not None:
            details["new_face_value"] = new_face_value
        if ratio_numerator is not None:
            details["ratio_numerator"] = ratio_numerator
        if ratio_denominator is not None:
            details["ratio_denominator"] = ratio_denominator
        desc = f"Stock Split - {symbol}"
        if ratio_numerator and ratio_denominator:
            desc += f" ({ratio_numerator}:{ratio_denominator})"
        elif old_face_value and new_face_value:
            desc += f" (₹{old_face_value} → ₹{new_face_value})"
        return await self.register_event(
            symbol=symbol, event_type="split",
            ex_date=ex_date, record_date=record_date,
            description=desc,
            details_json=json.dumps(details) if details else None,
            source=source,
        )

    async def register_bonus(
        self, symbol: str, ex_date: date,
        record_date: date | None = None,
        ratio_numerator: int = 1, ratio_denominator: int = 1,
        source: str | None = None,
    ) -> CorporateCalendar:
        desc = f"Bonus Issue - {symbol} ({ratio_numerator}:{ratio_denominator})"
        import json
        details = {"ratio_numerator": ratio_numerator, "ratio_denominator": ratio_denominator}
        return await self.register_event(
            symbol=symbol, event_type="bonus",
            ex_date=ex_date, record_date=record_date,
            description=desc,
            details_json=json.dumps(details),
            source=source,
        )

    async def register_rights(
        self, symbol: str, ex_date: date,
        record_date: date | None = None,
        entitlement_ratio_numerator: int = 1,
        entitlement_ratio_denominator: int = 1,
        issue_price: float | None = None,
        premium: float | None = None,
        source: str | None = None,
    ) -> CorporateCalendar:
        import json
        details: dict[str, Any] = {
            "entitlement_ratio_numerator": entitlement_ratio_numerator,
            "entitlement_ratio_denominator": entitlement_ratio_denominator,
        }
        if issue_price is not None:
            details["issue_price"] = issue_price
        if premium is not None:
            details["premium"] = premium
        desc = (
            f"Rights Issue - {symbol} "
            f"({entitlement_ratio_numerator}:{entitlement_ratio_denominator})"
        )
        if issue_price is not None:
            desc += f" @ ₹{issue_price}"
        return await self.register_event(
            symbol=symbol, event_type="rights",
            ex_date=ex_date, record_date=record_date,
            description=desc,
            details_json=json.dumps(details),
            source=source,
        )

    # ═════════════════════════════════════════════════════════════════════
    # Query Events
    # ═════════════════════════════════════════════════════════════════════

    async def get_event(self, event_id: int) -> CorporateCalendar | None:
        from sqlalchemy import select
        result = await self.session.execute(
            select(CorporateCalendar).where(CorporateCalendar.id == event_id),
        )
        return result.scalar_one_or_none()

    async def list_events(
        self, symbol: str | None = None,
        event_type: str | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
        confirmed_only: bool = False,
    ) -> list[CorporateCalendar]:
        from sqlalchemy import select
        stmt = select(CorporateCalendar).order_by(
            CorporateCalendar.ex_date.desc().nullslast(),
            CorporateCalendar.announcement_date.desc().nullslast(),
        )
        if symbol:
            stmt = stmt.where(CorporateCalendar.symbol == symbol.upper())
        if event_type:
            stmt = stmt.where(CorporateCalendar.event_type == event_type)
        if from_date:
            stmt = stmt.where(CorporateCalendar.ex_date >= from_date)
        if to_date:
            stmt = stmt.where(CorporateCalendar.ex_date <= to_date)
        if confirmed_only:
            stmt = stmt.where(CorporateCalendar.is_confirmed.is_(True))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    # ═════════════════════════════════════════════════════════════════════
    # Reminder Subscriptions
    # ═════════════════════════════════════════════════════════════════════

    async def subscribe(
        self, user_id: int, event_id: int,
        days_before: int = 7,
    ) -> CorporateReminder:
        event = await self.get_event(event_id)
        if not event:
            raise ValueError(f"Event {event_id} not found")
        key_date = event.ex_date or event.announcement_date or date.today()
        reminder_date = key_date - timedelta(days=days_before)
        existing = await self._find_subscription(user_id, event_id, days_before)
        if existing:
            return existing
        reminder = CorporateReminder(
            user_id=user_id,
            event_id=event_id,
            event_type=event.event_type,
            symbol=event.symbol,
            days_before=days_before,
            reminder_date=reminder_date,
            status="pending",
        )
        self.session.add(reminder)
        await self.session.commit()
        await self.session.refresh(reminder)
        return reminder

    async def subscribe_multi(
        self, user_id: int, event_ids: list[int],
        days_before: int = 7,
    ) -> list[CorporateReminder]:
        results: list[CorporateReminder] = []
        for eid in event_ids:
            try:
                r = await self.subscribe(user_id, eid, days_before)
                results.append(r)
            except ValueError:
                continue
        return results

    async def unsubscribe(self, reminder_id: int, user_id: int | None = None) -> bool:
        stmt = select(CorporateReminder).where(CorporateReminder.id == reminder_id)
        if user_id is not None:
            stmt = stmt.where(CorporateReminder.user_id == user_id)
        result = await self.session.execute(stmt)
        reminder = result.scalar_one_or_none()
        if not reminder:
            return False
        await self.session.delete(reminder)
        await self.session.commit()
        return True

    async def get_user_reminders(
        self, user_id: int, status: str | None = None,
    ) -> list[CorporateReminder]:
        from sqlalchemy import select
        stmt = (
            select(CorporateReminder)
            .options(selectinload(CorporateReminder.event))
            .where(CorporateReminder.user_id == user_id)
            .order_by(CorporateReminder.reminder_date)
        )
        if status:
            stmt = stmt.where(CorporateReminder.status == status)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def acknowledge(self, reminder_id: int, user_id: int | None = None) -> bool:
        stmt = select(CorporateReminder).where(CorporateReminder.id == reminder_id)
        if user_id is not None:
            stmt = stmt.where(CorporateReminder.user_id == user_id)
        result = await self.session.execute(stmt)
        reminder = result.scalar_one_or_none()
        if not reminder:
            return False
        reminder.status = "acknowledged"
        await self.session.commit()
        return True

    # ═════════════════════════════════════════════════════════════════════
    # Reminder Generation Engine
    # ═════════════════════════════════════════════════════════════════════

    async def generate_reminders(
        self, target_date: date | None = None,
    ) -> dict[str, Any]:
        """Scan pending reminders and send notifications for due ones."""
        from sqlalchemy import select
        target = target_date or date.today()

        result = await self.session.execute(
            select(CorporateReminder)
            .options(selectinload(CorporateReminder.event))
            .where(
                CorporateReminder.status == "pending",
                CorporateReminder.reminder_date <= target,
            )
        )
        due = list(result.scalars().all())

        if not due:
            return {"reminders_found": 0, "notifications_sent": 0}

        sent = 0
        for reminder in due:
            if self._notify is None:
                reminder.status = "sent"
                reminder.sent_at = datetime.now(tz=timezone.utc)
                sent += 1
                continue

            symbol = reminder.symbol
            event_type = reminder.event_type.replace("_", " ").title()
            event = reminder.event
            key_date = (
                event.ex_date or event.announcement_date or event.payment_date
            )
            date_str = key_date.isoformat() if key_date else "TBA"
            title = f"Upcoming: {event_type} for {symbol}"
            message = (
                f"{symbol} has an upcoming {event_type} on {date_str}. "
                f"{event.description or ''}"
            ).strip()

            try:
                ntf_result = await self._notify.send_notification(
                    user_id=reminder.user_id,
                    title=title,
                    message=message,
                    notification_type="corporate_reminder",
                    reference_type="corporate_reminder",
                    reference_id=reminder.id,
                    channels=["log"],
                    data={
                        "event_id": reminder.event_id,
                        "event_type": reminder.event_type,
                        "symbol": symbol,
                        "key_date": date_str,
                    },
                )
                reminder.status = "sent"
                reminder.sent_at = datetime.now(tz=timezone.utc)
                reminder.notification_id = ntf_result.get("notification_id")
                sent += 1
            except Exception as exc:
                logger.error(
                    "reminder_notification_failed",
                    reminder_id=reminder.id, error=str(exc),
                )
                reminder.status = "pending"

        await self.session.commit()
        return {"reminders_found": len(due), "notifications_sent": sent}

    async def get_reminder_stats(self) -> dict[str, Any]:
        from sqlalchemy import func, select
        total = await self.session.execute(
            select(func.count(CorporateReminder.id))
        )
        pending = await self.session.execute(
            select(func.count(CorporateReminder.id)).where(
                CorporateReminder.status == "pending",
            )
        )
        sent = await self.session.execute(
            select(func.count(CorporateReminder.id)).where(
                CorporateReminder.status == "sent",
            )
        )
        by_type = await self.session.execute(
            select(
                CorporateReminder.event_type,
                func.count(CorporateReminder.id),
            ).group_by(CorporateReminder.event_type)
        )
        return {
            "total": total.scalar() or 0,
            "pending": pending.scalar() or 0,
            "sent": sent.scalar() or 0,
            "by_event_type": dict(by_type.all()),
        }

    async def _find_subscription(
        self, user_id: int, event_id: int, days_before: int,
    ) -> CorporateReminder | None:
        from sqlalchemy import select
        result = await self.session.execute(
            select(CorporateReminder).where(
                CorporateReminder.user_id == user_id,
                CorporateReminder.event_id == event_id,
                CorporateReminder.days_before == days_before,
            )
        )
        return result.scalar_one_or_none()
