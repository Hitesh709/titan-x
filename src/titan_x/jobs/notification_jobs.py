import structlog

from titan_x.jobs.base import ScheduledJob
from titan_x.services.notification_service import NotificationService

logger = structlog.get_logger(__name__)


class RetryNotificationsJob(ScheduledJob):
    def __init__(self) -> None:
        super().__init__("retry_notifications", "minutes", interval_minutes=5, max_retries=2, retry_delay=30)

    async def _run(self, payload: dict) -> dict:
        session = payload.get("session")
        settings = payload.get("settings")
        if session is None or settings is None:
            return {"status": "failed", "error": "Missing session or settings"}

        service = NotificationService(session, settings)
        retried_count = await service.retry_failed()

        logger.info("notification_retries_processed", retried=retried_count)
        return {"status": "success", "retried": retried_count}


class CleanupNotificationHistoryJob(ScheduledJob):
    def __init__(self) -> None:
        super().__init__("cleanup_notification_history", "daily", max_retries=1, retry_delay=30)

    async def _run(self, payload: dict) -> dict:
        session = payload.get("session")
        settings = payload.get("settings")
        if session is None or settings is None:
            return {"status": "failed", "error": "Missing session or settings"}

        service = NotificationService(session, settings)
        deleted_count = await service.cleanup_old_history()

        logger.info("notification_history_cleaned", deleted=deleted_count)
        return {"status": "success", "deleted": deleted_count}
