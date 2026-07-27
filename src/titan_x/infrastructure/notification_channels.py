from abc import ABC, abstractmethod
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class NotificationChannel(ABC):
    name: str = "abstract"

    @abstractmethod
    async def send(
        self, to: str, title: str, message: str,
        data: dict[str, Any] | None = None,
    ) -> bool:
        ...


class LogChannel(NotificationChannel):
    name = "log"

    async def send(self, to: str, title: str, message: str, data: dict[str, Any] | None = None) -> bool:
        logger.info("notification_via_log", to=to, title=title, message=message, data=data)
        return True


class EmailChannel(NotificationChannel):
    name = "email"

    def __init__(
        self, host: str | None = None, port: int = 587,
        user: str | None = None, password: str | None = None,
        from_email: str = "noreply@titanx.com", from_name: str = "Titan X",
        log_only: bool = True,
    ) -> None:
        self._host = host
        self._port = port
        self._user = user
        self._password = password
        self._from_email = from_email
        self._from_name = from_name
        self._log_only = log_only
        self._configured = bool(host and user and password)

    async def send(self, to: str, title: str, message: str, data: dict[str, Any] | None = None) -> bool:
        if self._log_only or not self._configured:
            logger.info("notification_via_email", to=to, title=title, message=message, data=data, configured=self._configured)
            return self._configured
        return await self._send_smtp(to, title, message)

    async def _send_smtp(self, to: str, title: str, message: str) -> bool:
        try:
            import smtplib
            from email.mime.text import MIMEText

            msg = MIMEText(message, "plain" if "<html>" not in message else "html")
            msg["Subject"] = title
            msg["From"] = f"{self._from_name} <{self._from_email}>"
            msg["To"] = to

            with smtplib.SMTP(self._host, self._port) as server:
                server.starttls()
                server.login(self._user, self._password)
                server.send_message(msg)
            return True
        except Exception:
            logger.exception("email_send_failed", to=to, title=title)
            return False


class PushChannel(NotificationChannel):
    name = "push"

    def __init__(self, enabled: bool = False, config_json: str = "{}", log_only: bool = True) -> None:
        self._enabled = enabled
        self._log_only = log_only

    async def send(self, to: str, title: str, message: str, data: dict[str, Any] | None = None) -> bool:
        if self._log_only or not self._enabled:
            logger.info("notification_via_push", to=to, title=title, message=message, data=data)
            return self._enabled
        return await self._send_push(to, title, message, data)

    async def _send_push(self, to: str, title: str, message: str, data: dict[str, Any] | None = None) -> bool:
        logger.info("push_notification_stub", to=to, title=title, message=message)
        return True


class SMSChannel(NotificationChannel):
    name = "sms"

    def __init__(self, enabled: bool = False, provider: str = "log", config_json: str = "{}", log_only: bool = True) -> None:
        self._enabled = enabled
        self._provider = provider
        self._log_only = log_only

    async def send(self, to: str, title: str, message: str, data: dict[str, Any] | None = None) -> bool:
        if self._log_only or not self._enabled:
            logger.info("notification_via_sms", to=to, title=title, message=message, provider=self._provider)
            return self._enabled
        return await self._send_sms(to, message)

    async def _send_sms(self, to: str, message: str) -> bool:
        logger.info("sms_notification_stub", to=to, message=message)
        return True
