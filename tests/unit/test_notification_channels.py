import pytest
import pytest_asyncio

from titan_x.infrastructure.notification_channels import (
    EmailChannel,
    LogChannel,
    PushChannel,
    SMSChannel,
)


class TestLogChannel:
    @pytest.mark.asyncio
    async def test_send(self):
        channel = LogChannel()
        result = await channel.send("user_1", "Test", "Body")
        assert result is True


class TestEmailChannel:
    @pytest.mark.asyncio
    async def test_send_log_only(self):
        channel = EmailChannel(log_only=True)
        result = await channel.send("test@example.com", "Test", "Body")
        assert result is False

    @pytest.mark.asyncio
    async def test_send_configured_log_only(self):
        channel = EmailChannel(host="smtp.example.com", user="u", password="p", log_only=True)
        result = await channel.send("test@example.com", "Test", "Body")
        assert result is True

    @pytest.mark.asyncio
    async def test_not_configured(self):
        channel = EmailChannel(log_only=False)
        result = await channel.send("test@example.com", "Test", "Body")
        assert result is False


class TestPushChannel:
    @pytest.mark.asyncio
    async def test_send_log_only(self):
        channel = PushChannel(log_only=True)
        result = await channel.send("user_1", "Test", "Body")
        assert result is False

    @pytest.mark.asyncio
    async def test_send_enabled(self):
        channel = PushChannel(enabled=True, log_only=True)
        result = await channel.send("user_1", "Test", "Body")
        assert result is True


class TestSMSChannel:
    @pytest.mark.asyncio
    async def test_send_log_only(self):
        channel = SMSChannel(log_only=True)
        result = await channel.send("+15551234567", "Test", "Body")
        assert result is False

    @pytest.mark.asyncio
    async def test_send_enabled(self):
        channel = SMSChannel(enabled=True, log_only=True)
        result = await channel.send("+15551234567", "Test", "Body")
        assert result is True


class TestDeliveryService:
    @pytest.mark.asyncio
    async def test_deliver(self):
        from titan_x.core.config import Settings
        from titan_x.services.notification_delivery_service import NotificationDeliveryService

        settings = Settings(
            database_url="sqlite+aiosqlite:///",
            redis_url="redis://localhost:6379/0",
            api_key="test-api-key-1234567890abcdef!!!!!",
            jwt_secret_key="test-jwt-secret-1234567890abcdef!!!!!",
            notification_log_only=True,
        )
        service = NotificationDeliveryService(settings)
        results = await service.deliver(1, "Test", "Body")
        assert "email" in results
        assert "push" in results
        assert "sms" in results
        assert "log" in results
        assert results["log"] is True
