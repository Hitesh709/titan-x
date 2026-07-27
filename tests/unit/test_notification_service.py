from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from titan_x.core.config import Settings
from titan_x.db.base import Base
from titan_x.infrastructure.notification_channels import LogChannel
from titan_x.infrastructure.sms_providers import LogSMSProvider, TwilioSMSProvider
from titan_x.models.notification_history import DeliveryLog, NotificationHistory, NotificationRetry
from titan_x.models.user import User
from titan_x.services.notification_service import NotificationService


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as sess:
        await sess.execute(select(1).where(True))
        yield sess
    await engine.dispose()


@pytest_asyncio.fixture
def settings() -> Settings:
    return Settings(
        database_url="sqlite+aiosqlite:///",
        redis_url="redis://localhost:6379/0",
        api_key="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        jwt_secret_key="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        notification_log_only=True,
        retry_queue_enabled=False,
    )


@pytest_asyncio.fixture
async def user(session: AsyncSession) -> User:
    u = User(email="test@example.com", hashed_password="h", phone="+15551234567", fcm_token="fcm_abc123")
    session.add(u)
    await session.flush()
    return u


@pytest_asyncio.fixture
async def service(session: AsyncSession, settings: Settings) -> NotificationService:
    return NotificationService(session, settings)


class TestSendNotification:
    @pytest.mark.asyncio
    async def test_send_log_only_creates_history(self, service: NotificationService, session: AsyncSession, user: User):
        result = await service.send_notification(
            user_id=user.id, title="Test", message="Hello", notification_type="test",
            channels=["log"], user_email=user.email,
        )
        assert result["notification_id"] is not None
        assert result["overall_status"] == "sent"
        assert "log" in result["channel_results"]
        assert result["channel_results"]["log"] == "sent"

        history = await session.get(NotificationHistory, result["notification_id"])
        assert history is not None
        assert history.title == "Test"
        assert history.message == "Hello"
        assert history.notification_type == "test"
        assert history.status == "sent"
        assert history.sent_at is not None

    @pytest.mark.asyncio
    async def test_send_creates_delivery_logs(self, service: NotificationService, session: AsyncSession, user: User):
        result = await service.send_notification(
            user_id=user.id, title="Test", message="Hello", channels=["log"],
        )
        logs = await session.execute(
            select(DeliveryLog).where(DeliveryLog.notification_history_id == result["notification_id"])
        )
        delivery_logs = logs.scalars().all()
        assert len(delivery_logs) == 1
        assert delivery_logs[0].channel_name == "log"
        assert delivery_logs[0].status == "sent"

    @pytest.mark.asyncio
    async def test_send_with_reference(self, service: NotificationService, session: AsyncSession, user: User):
        result = await service.send_notification(
            user_id=user.id, title="Alert", message="Price hit", notification_type="alert",
            reference_type="alert", reference_id=42, channels=["log"],
        )
        history = await session.get(NotificationHistory, result["notification_id"])
        assert history.reference_type == "alert"
        assert history.reference_id == 42
        assert history.notification_type == "alert"

    @pytest.mark.asyncio
    async def test_send_channel_failure(self, service: NotificationService, session: AsyncSession, user: User):
        class FailingChannel(LogChannel):
            name = "failing"

            async def send(self, to, title, message, data=None):
                raise RuntimeError("Delivery failed")

        service._channels = {"failing": FailingChannel()}
        service._resolve_channels = lambda channels: {"failing": FailingChannel()}
        result = await service.send_notification(
            user_id=user.id, title="Test", message="Fail", channels=["failing"],
        )
        assert result["overall_status"] == "failed"
        assert result["channel_results"]["failing"] == "failed"
        history = await session.get(NotificationHistory, result["notification_id"])
        assert history.status == "failed"

    @pytest.mark.asyncio
    async def test_send_creates_retry_on_failure(self, session: AsyncSession, user: User):
        settings = Settings(
            database_url="sqlite+aiosqlite:///",
            redis_url="redis://localhost:6379/0",
            api_key="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            jwt_secret_key="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            notification_log_only=True,
            retry_queue_enabled=True,
            retry_base_delay_seconds=60,
            retry_max_attempts=3,
        )
        service = NotificationService(session, settings)

        class FailingChannel(LogChannel):
            name = "failing"

            async def send(self, to, title, message, data=None):
                return False

        service._resolve_channels = lambda channels: {"failing": FailingChannel()}
        result = await service.send_notification(
            user_id=user.id, title="Test", message="Retry", channels=["failing"],
        )
        retries = await session.execute(
            select(NotificationRetry).where(NotificationRetry.notification_history_id == result["notification_id"])
        )
        retry_list = retries.scalars().all()
        assert len(retry_list) == 1
        assert retry_list[0].channel_name == "failing"
        assert retry_list[0].max_attempts == 3
        assert retry_list[0].status == "pending"


class TestRetryFailed:
    @pytest.mark.asyncio
    async def test_retry_successful(self, service: NotificationService, session: AsyncSession, user: User):
        history = NotificationHistory(
            user_id=user.id, title="Retry Test", message="Body",
            notification_type="test", channel="log", status="failed",
        )
        session.add(history)
        await session.flush()

        retry = NotificationRetry(
            notification_history_id=history.id,
            channel_name="log",
            recipient=f"user_{user.id}",
            max_attempts=3,
            attempts=1,
            last_error="Temporary failure",
            next_retry_at=datetime.now(tz=timezone.utc) - timedelta(minutes=5),
            status="pending",
        )
        session.add(retry)
        await session.flush()

        count = await service.retry_failed(batch_size=10)
        assert count == 1

    @pytest.mark.asyncio
    async def test_retry_max_attempts_exceeded(self, service: NotificationService, session: AsyncSession, user: User):
        history = NotificationHistory(
            user_id=user.id, title="Exhausted", message="Body",
            notification_type="test", channel="log", status="failed",
        )
        session.add(history)
        await session.flush()

        retry = NotificationRetry(
            notification_history_id=history.id,
            channel_name="nonexistent",
            recipient=f"user_{user.id}",
            max_attempts=2,
            attempts=2,
            last_error="Failed",
            next_retry_at=datetime.now(tz=timezone.utc) - timedelta(minutes=5),
            status="pending",
        )
        session.add(retry)
        await session.flush()

        count = await service.retry_failed(batch_size=10)
        assert count == 0

    @pytest.mark.asyncio
    async def test_no_pending_retries(self, service: NotificationService):
        count = await service.retry_failed(batch_size=10)
        assert count == 0


class TestQueryHistory:
    @pytest.mark.asyncio
    async def test_get_history(self, service: NotificationService, session: AsyncSession, user: User):
        for i in range(3):
            h = NotificationHistory(
                user_id=user.id, title=f"Test {i}", message="Body",
                notification_type="test", channel="log", status="sent",
                sent_at=datetime.now(tz=timezone.utc),
            )
            session.add(h)
        await session.flush()

        history = await service.get_history(user_id=user.id, limit=10)
        assert len(history) == 3

    @pytest.mark.asyncio
    async def test_get_history_filtered_by_status(self, service: NotificationService, session: AsyncSession, user: User):
        h1 = NotificationHistory(user_id=user.id, title="Sent", message="Body", notification_type="test", channel="log", status="sent", sent_at=datetime.now(tz=timezone.utc))
        h2 = NotificationHistory(user_id=user.id, title="Failed", message="Body", notification_type="test", channel="log", status="failed")
        session.add_all([h1, h2])
        await session.flush()

        sent = await service.get_history(user_id=user.id, status="sent")
        assert len(sent) == 1
        assert sent[0].title == "Sent"

        failed = await service.get_history(user_id=user.id, status="failed")
        assert len(failed) == 1
        assert failed[0].title == "Failed"

    @pytest.mark.asyncio
    async def test_get_delivery_logs(self, service: NotificationService, session: AsyncSession, user: User):
        history = NotificationHistory(user_id=user.id, title="Test", message="Body", notification_type="test", channel="log", status="sent", sent_at=datetime.now(tz=timezone.utc))
        session.add(history)
        await session.flush()

        log = DeliveryLog(notification_history_id=history.id, channel_name="log", recipient="test@test.com", status="sent")
        session.add(log)
        await session.flush()

        logs = await service.get_delivery_logs(notification_id=history.id)
        assert len(logs) == 1
        assert logs[0].channel_name == "log"
        assert logs[0].status == "sent"

    @pytest.mark.asyncio
    async def test_get_delivery_logs_empty(self, service: NotificationService):
        logs = await service.get_delivery_logs(notification_id=9999)
        assert len(logs) == 0


class TestRetryQuery:
    @pytest.mark.asyncio
    async def test_get_pending_retries(self, service: NotificationService, session: AsyncSession, user: User):
        history = NotificationHistory(user_id=user.id, title="Test", message="Body", notification_type="test", channel="log", status="failed")
        session.add(history)
        await session.flush()

        retry = NotificationRetry(
            notification_history_id=history.id, channel_name="email", recipient="test@test.com",
            max_attempts=3, attempts=1, last_error="err",
            next_retry_at=datetime.now(tz=timezone.utc) + timedelta(minutes=5),
            status="pending",
        )
        session.add(retry)
        await session.flush()

        pending = await service.get_pending_retries()
        assert len(pending) == 1
        assert pending[0].channel_name == "email"


class TestCleanup:
    @pytest.mark.asyncio
    async def test_cleanup_old_history(self, service: NotificationService, session: AsyncSession, user: User):
        old = NotificationHistory(
            user_id=user.id, title="Old", message="Body", notification_type="test",
            channel="log", status="sent",
            created_at=datetime.now(tz=timezone.utc) - timedelta(days=200),
            sent_at=datetime.now(tz=timezone.utc) - timedelta(days=200),
        )
        recent = NotificationHistory(
            user_id=user.id, title="Recent", message="Body", notification_type="test",
            channel="log", status="sent",
            created_at=datetime.now(tz=timezone.utc),
            sent_at=datetime.now(tz=timezone.utc),
        )
        session.add_all([old, recent])
        await session.flush()

        deleted = await service.cleanup_old_history()
        assert deleted == 1

        remaining = await service.get_history(user_id=user.id)
        assert len(remaining) == 1
        assert remaining[0].title == "Recent"


class TestUserPreferences:
    @pytest.mark.asyncio
    async def test_get_preferences_with_all_channels(self, service: NotificationService, session: AsyncSession, user: User):
        prefs = await service.get_user_notification_preferences(user.id)
        assert prefs["email"] is True
        assert prefs["push"] is True
        assert prefs["sms"] is True

    @pytest.mark.asyncio
    async def test_get_preferences_no_phone(self, service: NotificationService, session: AsyncSession, user: User):
        user.phone = None
        user.fcm_token = None
        await session.flush()

        prefs = await service.get_user_notification_preferences(user.id)
        assert prefs["email"] is True
        assert prefs["push"] is False
        assert prefs["sms"] is False

    @pytest.mark.asyncio
    async def test_get_preferences_nonexistent_user(self, service: NotificationService):
        prefs = await service.get_user_notification_preferences(9999)
        assert prefs["email"] is False
        assert prefs["push"] is False
        assert prefs["sms"] is False


class TestResolveChannels:
    @pytest.mark.asyncio
    async def test_default_channels_log_only(self, service: NotificationService):
        channels = service._resolve_channels()
        assert "log" in channels
        assert "email" in channels
        assert "push" in channels
        assert "sms" in channels
        assert "firebase" in channels

    @pytest.mark.asyncio
    async def test_specific_channels(self, service: NotificationService):
        channels = service._resolve_channels(["log", "email"])
        assert "log" in channels
        assert "email" in channels
        assert "push" not in channels
        assert len(channels) == 2


class TestBackoff:
    @pytest.mark.asyncio
    async def test_compute_backoff(self, service: NotificationService):
        b1 = service._compute_backoff(1)
        b2 = service._compute_backoff(2)
        b3 = service._compute_backoff(3)

        assert b1 >= 48
        assert b1 <= 72
        assert b2 >= 96
        assert b2 <= 144
        assert b3 >= 192
        assert b3 <= 288


class TestSMSProviders:
    @pytest.mark.asyncio
    async def test_log_sms_provider(self):
        provider = LogSMSProvider()
        result = await provider.send("+15551234567", "Hello")
        assert result is True

    @pytest.mark.asyncio
    async def test_twilio_provider_not_installed(self):
        provider = TwilioSMSProvider("sid", "token", "+15551234567")
        result = await provider.send("+15551234567", "Hello")
        assert result is False
