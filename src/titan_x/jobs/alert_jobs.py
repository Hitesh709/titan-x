import structlog

from titan_x.jobs.base import ScheduledJob
from titan_x.services.alert_evaluation_service import AlertEvaluationService
from titan_x.services.notification_delivery_service import NotificationDeliveryService

logger = structlog.get_logger(__name__)


class ProcessAlertsJob(ScheduledJob):
    def __init__(self) -> None:
        super().__init__("process_alerts", "daily", max_retries=2, retry_delay=30)

    async def _run(self, payload: dict) -> dict:
        session = payload.get("session")
        settings = payload.get("settings")
        if session is None or settings is None:
            return {"status": "failed", "error": "Missing session or settings"}

        delivery = NotificationDeliveryService(settings)
        evaluator = AlertEvaluationService(session, delivery)
        triggered_count = await evaluator.evaluate_all_active_alerts()

        logger.info("alerts_processed", triggered=triggered_count)
        return {"status": "success", "alerts_triggered": triggered_count}
