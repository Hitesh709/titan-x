from typing import Any

import structlog

from titan_x.infrastructure.notification_channels import NotificationChannel

logger = structlog.get_logger(__name__)


class FirebaseChannel(NotificationChannel):
    name = "firebase"

    def __init__(self, credentials_json: str | None = None, enabled: bool = False, log_only: bool = True) -> None:
        self._credentials_json = credentials_json
        self._enabled = enabled
        self._log_only = log_only
        self._initialized = False
        self._app = None

    async def send(self, to: str, title: str, message: str, data: dict[str, Any] | None = None) -> bool:
        if self._log_only or not self._enabled:
            logger.info("notification_via_firebase", to=to, title=title, message=message, data=data, enabled=self._enabled)
            return self._enabled
        return await self._send_fcm(to, title, message, data)

    async def _send_fcm(self, to: str, title: str, message: str, data: dict[str, Any] | None = None) -> bool:
        try:
            return await self._try_send_fcm(to, title, message, data)
        except ImportError:
            logger.warning("firebase_admin_not_installed_falling_back_to_log", to=to)
            logger.info("notification_via_firebase", to=to, title=title, message=message, data=data)
            return False
        except Exception:
            logger.exception("firebase_send_failed", to=to, title=title)
            return False

    async def _try_send_fcm(self, to: str, title: str, message: str, data: dict[str, Any] | None = None) -> bool:
        import firebase_admin
        from firebase_admin import credentials, messaging

        if not self._initialized:
            if self._credentials_json:
                import json
                cred_dict = json.loads(self._credentials_json)
                cred = credentials.Certificate(cred_dict)
            else:
                cred = credentials.ApplicationDefault()
            self._app = firebase_admin.initialize_app(cred)
            self._initialized = True

        notification = messaging.Notification(title=title, body=message)
        fcm_data = {k: str(v) for k, v in (data or {}).items()}
        msg = messaging.Message(
            notification=notification,
            data=fcm_data,
            token=to,
        )
        response = messaging.send(msg)
        logger.info("firebase_message_sent", message_id=response)
        return True
