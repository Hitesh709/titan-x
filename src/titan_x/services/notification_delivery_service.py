from typing import Any

import structlog

from titan_x.core.config import Settings
from titan_x.infrastructure.notification_channels import (
    EmailChannel,
    LogChannel,
    NotificationChannel,
    PushChannel,
    SMSChannel,
)
from titan_x.models.user import User

logger = structlog.get_logger(__name__)


class NotificationDeliveryService:
    def __init__(self, settings: Settings, channels: list[NotificationChannel] | None = None) -> None:
        self._log_only = settings.notification_log_only

        if channels:
            self._channels = channels
        else:
            self._channels = self._build_channels(settings)

    def _build_channels(self, settings: Settings) -> list[NotificationChannel]:
        return [
            EmailChannel(
                host=settings.smtp_host,
                port=settings.smtp_port,
                user=settings.smtp_user,
                password=settings.smtp_password,
                from_email=settings.smtp_from_email,
                from_name=settings.smtp_from_name,
                log_only=self._log_only,
            ),
            PushChannel(
                enabled=settings.push_enabled,
                config_json=settings.push_config_json,
                log_only=self._log_only,
            ),
            SMSChannel(
                enabled=settings.sms_enabled,
                provider=settings.sms_provider,
                config_json=settings.sms_config_json,
                log_only=self._log_only,
            ),
            LogChannel(),
        ]

    async def deliver(
        self, user_id: int, title: str, message: str,
        data: dict[str, Any] | None = None,
        user_email: str | None = None,
        user_phone: str | None = None,
    ) -> dict[str, bool]:
        results: dict[str, bool] = {}
        for channel in self._channels:
            try:
                to = self._resolve_recipient(channel, user_id, user_email, user_phone)
                if to:
                    ok = await channel.send(to, title, message, data)
                    results[channel.name] = ok
            except Exception:
                logger.exception("channel_delivery_failed", channel=channel.name)
                results[channel.name] = False
        return results

    async def deliver_to_user(
        self, user: User, title: str, message: str,
        data: dict[str, Any] | None = None,
    ) -> dict[str, bool]:
        return await self.deliver(
            user_id=user.id, title=title, message=message, data=data,
            user_email=user.email,
        )

    def _resolve_recipient(self, channel: NotificationChannel, user_id: int, user_email: str | None, user_phone: str | None) -> str | None:
        if channel.name == "email":
            return user_email or f"user_{user_id}@titanx.local"
        elif channel.name == "sms":
            return user_phone or f"+1-555-{user_id:07d}"
        return f"user_{user_id}"
