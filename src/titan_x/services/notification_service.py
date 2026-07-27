from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from sqlalchemy import and_, delete, desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from titan_x.core.config import Settings
from titan_x.infrastructure.firebase_channel import FirebaseChannel
from titan_x.infrastructure.notification_channels import (
    EmailChannel,
    LogChannel,
    NotificationChannel,
    PushChannel,
)
from titan_x.infrastructure.sms_providers import (
    AWSSNSProvider,
    LogSMSProvider,
    SMSProvider,
    TwilioSMSProvider,
)
from titan_x.models.notification_history import DeliveryLog, NotificationHistory, NotificationRetry
from titan_x.models.user import User

logger = structlog.get_logger(__name__)


class NotificationService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._session = session
        self._settings = settings
        self._log_only = settings.notification_log_only
        self._channels: dict[str, NotificationChannel] = {}
        self._sms_provider: SMSProvider | None = None

    async def send_notification(
        self,
        user_id: int,
        title: str,
        message: str,
        notification_type: str = "general",
        reference_type: str | None = None,
        reference_id: int | None = None,
        channels: list[str] | None = None,
        user_email: str | None = None,
        user_phone: str | None = None,
        user_fcm_token: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "notification_id": None,
            "channel_results": {},
            "overall_status": "pending",
        }

        history = NotificationHistory(
            user_id=user_id,
            title=title,
            message=message,
            notification_type=notification_type,
            channel=",".join(channels) if channels else "all",
            status="pending",
            reference_type=reference_type,
            reference_id=reference_id,
        )
        self._session.add(history)
        await self._session.flush()
        result["notification_id"] = history.id

        channel_instances = self._resolve_channels(channels)
        overall_success = True

        for channel_name, channel in channel_instances.items():
            recipient = self._resolve_recipient(channel_name, user_id, user_email, user_phone, user_fcm_token)
            if not recipient:
                continue

            delivery_log = DeliveryLog(
                notification_history_id=history.id,
                channel_name=channel_name,
                recipient=recipient,
                status="pending",
                attempt_number=1,
            )
            self._session.add(delivery_log)
            await self._session.flush()

            try:
                ok = await channel.send(recipient, title, message, data)
                delivery_log.status = "sent" if ok else "failed"
                if not ok:
                    delivery_log.error_message = "Channel returned failure"
                    overall_success = False
            except Exception as exc:
                delivery_log.status = "failed"
                delivery_log.error_message = str(exc)
                overall_success = False

            result["channel_results"][channel_name] = delivery_log.status

        history.status = "sent" if overall_success else "failed"
        if overall_success:
            history.sent_at = datetime.now(tz=timezone.utc)
        else:
            history.error_message = "One or more channels failed"

        await self._session.flush()

        failed_logs = [dl for dl in result["channel_results"].items() if dl[1] == "failed"]
        if failed_logs and self._settings.retry_queue_enabled:
            for channel_name, _ in failed_logs:
                recipient = self._resolve_recipient(channel_name, user_id, user_email, user_phone, user_fcm_token)
                if recipient:
                    base_delay = self._settings.retry_base_delay_seconds
                    retry = NotificationRetry(
                        notification_history_id=history.id,
                        channel_name=channel_name,
                        recipient=recipient,
                        max_attempts=self._settings.retry_max_attempts,
                        attempts=1,
                        last_error=history.error_message,
                        next_retry_at=datetime.now(tz=timezone.utc) + timedelta(seconds=base_delay),
                        status="pending",
                    )
                    self._session.add(retry)

        overall_status_str: str = "sent" if overall_success else "failed"
        result["overall_status"] = overall_status_str
        await self._session.flush()
        return result

    async def retry_failed(self, batch_size: int | None = None) -> int:
        bs = batch_size or self._settings.retry_batch_size
        now = datetime.now(tz=timezone.utc)

        result = await self._session.execute(
            select(NotificationRetry)
            .where(
                NotificationRetry.status == "pending",
                NotificationRetry.next_retry_at <= now,
                NotificationRetry.attempts < NotificationRetry.max_attempts,
            )
            .order_by(NotificationRetry.next_retry_at)
            .limit(bs)
        )
        retries = result.scalars().all()
        if not retries:
            return 0

        retried = 0
        for retry in retries:
            ok = await self._retry_single(retry)
            if ok:
                retried += 1
        return retried

    async def _retry_single(self, retry: NotificationRetry) -> bool:
        history_result = await self._session.execute(
            select(NotificationHistory).where(NotificationHistory.id == retry.notification_history_id)
        )
        history = history_result.scalar_one_or_none()
        if not history:
            retry.status = "failed"
            retry.last_error = "Notification history not found"
            return False

        channels = self._resolve_channels([retry.channel_name])
        channel = channels.get(retry.channel_name)
        if not channel:
            retry.status = "failed"
            retry.last_error = f"Channel {retry.channel_name} not available"
            return False

        retry.attempts += 1
        try:
            ok = await channel.send(retry.recipient, history.title, history.message)
            if ok:
                retry.status = "completed"
                delivery_log = DeliveryLog(
                    notification_history_id=history.id,
                    channel_name=retry.channel_name,
                    recipient=retry.recipient,
                    status="sent",
                    attempt_number=retry.attempts + 1,
                )
                self._session.add(delivery_log)
                return True
            else:
                retry.last_error = "Channel returned failure"
        except Exception as exc:
            retry.last_error = str(exc)

        if retry.attempts >= retry.max_attempts:
            retry.status = "failed"
        else:
            delay = self._compute_backoff(retry.attempts)
            retry.next_retry_at = datetime.now(tz=timezone.utc) + timedelta(seconds=delay)

        return False

    async def get_history(
        self,
        user_id: int | None = None,
        status: str | None = None,
        notification_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[NotificationHistory]:
        query = select(NotificationHistory).options(selectinload(NotificationHistory.delivery_logs))
        if user_id is not None:
            query = query.where(NotificationHistory.user_id == user_id)
        if status is not None:
            query = query.where(NotificationHistory.status == status)
        if notification_type is not None:
            query = query.where(NotificationHistory.notification_type == notification_type)
        query = query.order_by(desc(NotificationHistory.created_at)).offset(offset).limit(limit)
        result = await self._session.execute(query)
        return result.unique().scalars().all()

    async def get_delivery_logs(
        self,
        notification_id: int | None = None,
        channel_name: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> Sequence[DeliveryLog]:
        query = select(DeliveryLog)
        if notification_id is not None:
            query = query.where(DeliveryLog.notification_history_id == notification_id)
        if channel_name is not None:
            query = query.where(DeliveryLog.channel_name == channel_name)
        if status is not None:
            query = query.where(DeliveryLog.status == status)
        query = query.order_by(desc(DeliveryLog.created_at)).limit(limit)
        result = await self._session.execute(query)
        return result.scalars().all()

    async def get_pending_retries(self, limit: int = 50) -> Sequence[NotificationRetry]:
        result = await self._session.execute(
            select(NotificationRetry)
            .where(NotificationRetry.status == "pending")
            .order_by(NotificationRetry.next_retry_at)
            .limit(limit)
        )
        return result.scalars().all()

    async def cleanup_old_history(self) -> int:
        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=self._settings.notification_history_retention_days)
        result = await self._session.execute(
            delete(NotificationHistory).where(NotificationHistory.created_at < cutoff)
        )
        return result.rowcount

    async def get_user_notification_preferences(self, user_id: int) -> dict[str, bool]:
        user_result = await self._session.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()
        if not user:
            return {"email": False, "push": False, "sms": False}
        prefs: dict[str, bool] = {
            "email": bool(user.email),
            "push": bool(user.fcm_token),
            "sms": bool(user.phone),
        }
        return prefs

    def _resolve_channels(self, channel_names: list[str] | None = None) -> dict[str, NotificationChannel]:
        s = self._settings
        if not channel_names:
            channel_names = ["email", "push", "firebase", "sms", "log"]

        available: dict[str, NotificationChannel] = {}
        for name in channel_names:
            if name == "log":
                available["log"] = LogChannel()
            elif name == "email":
                available["email"] = EmailChannel(
                    host=s.smtp_host, port=s.smtp_port,
                    user=s.smtp_user, password=s.smtp_password,
                    from_email=s.smtp_from_email, from_name=s.smtp_from_name,
                    log_only=self._log_only,
                )
            elif name == "push":
                available["push"] = PushChannel(
                    enabled=s.push_enabled,
                    config_json=s.push_config_json,
                    log_only=self._log_only,
                )
            elif name == "firebase":
                available["firebase"] = FirebaseChannel(
                    credentials_json=s.firebase_credentials_json,
                    enabled=s.firebase_enabled,
                    log_only=self._log_only,
                )
            elif name == "sms":
                available["sms"] = self._build_sms_channel()

        return available

    def _build_sms_channel(self) -> PushChannel:
        s = self._settings
        if self._log_only or not s.sms_enabled:
            return PushChannel(enabled=False, log_only=True)

        provider = s.sms_provider
        if provider == "twilio" and s.sms_twilio_account_sid:
            self._sms_provider = TwilioSMSProvider(
                s.sms_twilio_account_sid, s.sms_twilio_auth_token or "",
                s.sms_twilio_from_number or "",
            )
        elif provider == "aws_sns" and s.sms_aws_access_key:
            self._sms_provider = AWSSNSProvider(
                s.sms_aws_access_key, s.sms_aws_secret_key or "",
                region=s.sms_aws_region,
            )
        else:
            self._sms_provider = LogSMSProvider()

        class SMSChannelWrapper(NotificationChannel):
            name = "sms"

            def __init__(self, provider: SMSProvider, enabled: bool, log_only: bool) -> None:
                self._provider = provider
                self._enabled = enabled
                self._log_only = log_only

            async def send(self, to: str, title: str, message: str, data: dict[str, Any] | None = None) -> bool:
                if self._log_only or not self._enabled:
                    logger.info("notification_via_sms", to=to, title=title, message=message, provider=self._provider.name)
                    return self._enabled
                try:
                    return await self._provider.send(to, message)
                except Exception:
                    logger.exception("sms_send_failed", to=to)
                    return False

        return SMSChannelWrapper(self._sms_provider, s.sms_enabled, self._log_only)

    def _resolve_recipient(
        self, channel_name: str, user_id: int,
        user_email: str | None, user_phone: str | None,
        user_fcm_token: str | None,
    ) -> str | None:
        if channel_name == "email":
            return user_email or f"user_{user_id}@titanx.local"
        elif channel_name in ("sms",):
            return user_phone or f"+1-555-{user_id:07d}"
        elif channel_name in ("push", "firebase"):
            return user_fcm_token or f"device_{user_id}"
        return f"user_{user_id}"

    def _compute_backoff(self, attempt: int) -> int:
        base = self._settings.retry_base_delay_seconds
        max_delay = self._settings.retry_max_delay_seconds
        delay = base * (2 ** (attempt - 1))
        import random
        jitter = random.uniform(0.8, 1.2)
        return min(int(delay * jitter), max_delay)
