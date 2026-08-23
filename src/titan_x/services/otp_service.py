from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.models.user import User


class OtpService:
    """Passwordless OTP support with hashed, short-lived codes.

    Delivery is intentionally provider-independent. Email delivery is implemented
    by the application email service; SMS can be added later without changing the
    account/OTP data model.
    """

    TTL_MINUTES = 5
    MAX_ATTEMPTS = 5
    RESEND_SECONDS = 60

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def normalize_email(email: str) -> str:
        return email.strip().lower()

    @staticmethod
    def _hash(code: str) -> str:
        return hashlib.sha256(code.encode("utf-8")).hexdigest()

    def generate_code(self) -> str:
        return f"{secrets.randbelow(1_000_000):06d}"

    async def request_email_otp(self, email: str) -> tuple[str, datetime]:
        email = self.normalize_email(email)
        result = await self._session.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if user is None:
            user = User(email=email, hashed_password="!otp-only")
            self._session.add(user)
            await self._session.flush()

        code = self.generate_code()
        now = datetime.now(timezone.utc)
        # Temporary attributes are kept in memory for this first zero-cost phase.
        # They are replaced by a persistent OTP table before high-volume production.
        user._otp_hash = self._hash(code)
        user._otp_expires_at = now + timedelta(minutes=self.TTL_MINUTES)
        user._otp_attempts = 0
        user._otp_sent_at = now
        await self._session.commit()
        return code, user._otp_expires_at

    async def verify_email_otp(self, email: str, code: str) -> User:
        email = self.normalize_email(email)
        result = await self._session.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if user is None or not getattr(user, "_otp_hash", None):
            raise ValueError("OTP not found or expired")
        expires = getattr(user, "_otp_expires_at", None)
        if expires is None or expires < datetime.now(timezone.utc):
            raise ValueError("OTP expired")
        attempts = int(getattr(user, "_otp_attempts", 0))
        if attempts >= self.MAX_ATTEMPTS:
            raise ValueError("Too many OTP attempts")
        if not secrets.compare_digest(self._hash(code.strip()), user._otp_hash):
            user._otp_attempts = attempts + 1
            await self._session.commit()
            raise ValueError("Invalid OTP")
        user.is_verified = True
        user._otp_hash = None
        user._otp_expires_at = None
        user._otp_attempts = 0
        await self._session.commit()
        return user
