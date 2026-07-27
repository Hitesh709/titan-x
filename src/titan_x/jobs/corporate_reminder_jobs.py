"""Scheduled jobs for corporate event reminders."""
import structlog

from titan_x.jobs.base import ScheduledJob
from titan_x.services.corporate_reminder_service import CorporateReminderService
from titan_x.services.notification_service import NotificationService

logger = structlog.get_logger(__name__)


class GenerateCorporateRemindersJob(ScheduledJob):
    def __init__(self) -> None:
        super().__init__(
            "generate_corporate_reminders", "daily",
            max_retries=2, retry_delay=30,
        )

    async def _run(self, payload: dict) -> dict:
        session = payload.get("session")
        settings = payload.get("settings")
        if session is None or settings is None:
            return {"status": "failed", "error": "Missing session or settings"}

        notify = NotificationService(session, settings)
        service = CorporateReminderService(session, notify)
        result = await service.generate_reminders()

        logger.info(
            "corporate_reminders_generated",
            found=result["reminders_found"],
            sent=result["notifications_sent"],
        )
        return {"status": "success", **result}
