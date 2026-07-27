from abc import ABC, abstractmethod
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class SMSProvider(ABC):
    name: str = "abstract"

    @abstractmethod
    async def send(self, to: str, message: str) -> bool:
        ...


class LogSMSProvider(SMSProvider):
    name = "log"

    async def send(self, to: str, message: str) -> bool:
        logger.info("sms_via_log", to=to, message=message)
        return True


class TwilioSMSProvider(SMSProvider):
    name = "twilio"

    def __init__(self, account_sid: str, auth_token: str, from_number: str) -> None:
        self._account_sid = account_sid
        self._auth_token = auth_token
        self._from_number = from_number
        self._client = None

    async def send(self, to: str, message: str) -> bool:
        try:
            return await self._try_send(to, message)
        except ImportError:
            logger.warning("twilio_not_installed_falling_back_to_log", to=to)
            logger.info("sms_via_twilio", to=to, message=message)
            return False
        except Exception:
            logger.exception("twilio_send_failed", to=to)
            return False

    async def _try_send(self, to: str, message: str) -> bool:
        from twilio.rest import Client
        self._client = Client(self._account_sid, self._auth_token)
        result = self._client.messages.create(
            body=message,
            from_=self._from_number,
            to=to,
        )
        logger.info("twilio_message_sent", sid=result.sid, to=to)
        return True


class AWSSNSProvider(SMSProvider):
    name = "aws_sns"

    def __init__(self, access_key: str, secret_key: str, region: str = "us-east-1") -> None:
        self._access_key = access_key
        self._secret_key = secret_key
        self._region = region
        self._client = None

    async def send(self, to: str, message: str) -> bool:
        try:
            return await self._try_send(to, message)
        except ImportError:
            logger.warning("boto3_not_installed_falling_back_to_log", to=to)
            logger.info("sms_via_aws_sns", to=to, message=message)
            return False
        except Exception:
            logger.exception("aws_sns_send_failed", to=to)
            return False

    async def _try_send(self, to: str, message: str) -> bool:
        import boto3
        self._client = boto3.client(
            "sns",
            aws_access_key_id=self._access_key,
            aws_secret_access_key=self._secret_key,
            region_name=self._region,
        )
        result = self._client.publish(
            PhoneNumber=to,
            Message=message,
        )
        logger.info("aws_sns_message_sent", message_id=result["MessageId"], to=to)
        return True
