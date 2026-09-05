from __future__ import annotations

import asyncio
import hashlib
import hmac
import secrets
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.core.config import Settings
from titan_x.core.security import create_access_token, create_refresh_token, hash_password
from titan_x.models.auth_challenge import AuthChallenge
from titan_x.models.refresh_token import RefreshToken
from titan_x.models.user import User


class EmailRegistrationService:
    OTP_TTL_SECONDS = 10 * 60
    OTP_MAX_ATTEMPTS = 5
    OTP_RESEND_SECONDS = 60
    CHALLENGE_TTL_SECONDS = 10 * 60
    RESEND_API_URL = "https://api.resend.com/emails"

    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._session = session
        self._settings = settings

    @staticmethod
    def _hash(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def normalize_phone(value: str) -> str:
        raw = value.strip()
        digits = "".join(ch for ch in raw if ch.isdigit())
        if 7 <= len(digits) <= 15:
            return "+" + digits
        raise ValueError("Invalid mobile number")

    async def create(self, username: str, email: str, phone: str, password: str, confirm_password: str) -> tuple[str, datetime]:
        username = username.strip()
        email = email.strip().lower()
        phone = self.normalize_phone(phone)
        if password != confirm_password:
            raise ValueError("Passwords do not match")
        if len(password) < 8:
            raise ValueError("Password must contain at least 8 characters")
        if not username:
            raise ValueError("Username is required")

        duplicate = await self._session.execute(
            select(User).where((User.username == username) | (User.email == email) | (User.phone == phone))
        )
        if duplicate.scalar_one_or_none() is not None:
            raise ValueError("Username, email, or mobile number is already registered")

        now = self._now()
        raw = secrets.token_urlsafe(32)
        challenge = AuthChallenge(
            challenge_id=secrets.token_urlsafe(24),
            challenge_hash=self._hash(raw),
            browser_session_id=self._hash(secrets.token_urlsafe(32)),
            status="EMAIL_OTP_REQUIRED",
            operation="REGISTRATION_EMAIL",
            expires_at=now + timedelta(seconds=self.CHALLENGE_TTL_SECONDS),
            registration_username=username,
            registration_email=email,
            registration_phone=phone,
            registration_password_hash=hash_password(password),
        )
        self._session.add(challenge)
        await self._session.flush()
        await self._send_otp(challenge)
        await self._session.commit()
        return challenge.challenge_id, challenge.email_otp_expires_at or (now + timedelta(seconds=self.OTP_TTL_SECONDS))

    def _message_content(self, challenge: AuthChallenge, otp: str) -> tuple[str, str]:
        text = (
            f"Your Titan X verification code is {otp}.\n\n"
            "This code expires in 10 minutes.\n"
            "Do not share this code with anyone."
        )
        html = (
            "<div style=\"font-family:Arial,sans-serif;line-height:1.6\">"
            "<h2>Titan X email verification</h2>"
            f"<p>Your verification code is <strong style=\"font-size:24px;letter-spacing:4px\">{otp}</strong>.</p>"
            "<p>This code expires in 10 minutes.</p>"
            "<p>Do not share this code with anyone.</p>"
            "</div>"
        )
        return text, html

    async def _send_via_resend(self, challenge: AuthChallenge, otp: str) -> bool:
        if self._settings.resend_api_key is None:
            return False
        recipient = challenge.registration_email or ""
        text, html = self._message_content(challenge, otp)
        from_email = self._settings.resend_from_email
        from_value = f"{self._settings.resend_from_name} <{from_email}>" if self._settings.resend_from_name else from_email
        payload = {
            "from": from_value,
            "to": [recipient],
            "subject": "Titan X email verification code",
            "text": text,
            "html": html,
        }
        headers = {
            "Authorization": f"Bearer {self._settings.resend_api_key.get_secret_value()}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(self.RESEND_API_URL, headers=headers, json=payload)
            if response.is_success:
                return True
            raise ValueError(f"Resend rejected email with HTTP {response.status_code}")
        except (httpx.HTTPError, ValueError) as exc:
            raise ValueError("Unable to send email verification code through Resend. Please check the Resend sender/domain configuration.") from exc

    async def _send_via_smtp(self, challenge: AuthChallenge, otp: str) -> bool:
        if not self._settings.smtp_host or not self._settings.smtp_user or not self._settings.smtp_password:
            return False
        text, _ = self._message_content(challenge, otp)
        message = EmailMessage()
        message["Subject"] = "Titan X email verification code"
        message["From"] = f"{self._settings.smtp_from_name} <{self._settings.smtp_from_email}>"
        message["To"] = challenge.registration_email or ""
        message.set_content(text)

        def send() -> None:
            with smtplib.SMTP(self._settings.smtp_host, self._settings.smtp_port, timeout=15) as smtp:
                smtp.starttls()
                smtp.login(self._settings.smtp_user, self._settings.smtp_password)
                smtp.send_message(message)

        try:
            await asyncio.to_thread(send)
            return True
        except (OSError, smtplib.SMTPException) as exc:
            raise ValueError("Unable to send email verification code through SMTP. Please try again.") from exc

    async def _send_otp(self, challenge: AuthChallenge) -> None:
        now = self._now()
        if challenge.email_otp_sent_at and (now - challenge.email_otp_sent_at).total_seconds() < self.OTP_RESEND_SECONDS:
            return
        otp = f"{secrets.randbelow(1_000_000):06d}"

        try:
            sent = await self._send_via_resend(challenge, otp)
            if not sent:
                sent = await self._send_via_smtp(challenge, otp)
        except ValueError:
            await self._session.rollback()
            raise

        if not sent:
            await self._session.rollback()
            raise ValueError("Email OTP is not configured. Configure Resend or SMTP email delivery.")

        challenge.email_otp_hash = self._hash(otp)
        challenge.email_otp_expires_at = now + timedelta(seconds=self.OTP_TTL_SECONDS)
        challenge.email_otp_attempts = 0
        challenge.email_otp_sent_at = now

    async def verify(self, challenge_id: str, otp: str) -> tuple[User, str, str]:
        result = await self._session.execute(
            select(AuthChallenge).where(AuthChallenge.challenge_id == challenge_id).with_for_update()
        )
        challenge = result.scalar_one_or_none()
        if challenge is None or challenge.operation != "REGISTRATION_EMAIL" or challenge.status != "EMAIL_OTP_REQUIRED":
            raise ValueError("Invalid or expired registration request")

        now = self._now()
        if challenge.expires_at <= now or challenge.email_otp_expires_at is None or challenge.email_otp_expires_at <= now:
            challenge.status = "EXPIRED"
            await self._session.commit()
            raise ValueError("Email OTP expired")
        if challenge.email_otp_attempts >= self.OTP_MAX_ATTEMPTS:
            raise ValueError("Too many email OTP attempts")

        challenge.email_otp_attempts += 1
        if not hmac.compare_digest(challenge.email_otp_hash or "", self._hash(otp.strip())):
            await self._session.commit()
            raise ValueError("Invalid email OTP")

        duplicate = await self._session.execute(
            select(User).where(
                (User.username == challenge.registration_username)
                | (User.email == challenge.registration_email)
                | (User.phone == challenge.registration_phone)
            ).with_for_update()
        )
        if duplicate.scalar_one_or_none() is not None:
            challenge.status = "CANCELLED"
            await self._session.commit()
            raise ValueError("Username, email, or mobile number is already registered")

        user = User(
            username=challenge.registration_username,
            email=challenge.registration_email or "",
            phone=challenge.registration_phone,
            hashed_password=challenge.registration_password_hash or "",
            is_active=True,
            is_verified=True,
            role="normal",
        )
        self._session.add(user)
        await self._session.flush()

        challenge.email_verified_at = now
        challenge.email_otp_hash = None
        challenge.email_otp_expires_at = None
        challenge.approved_at = now
        challenge.used_at = now
        challenge.status = "USED"

        access = create_access_token(user.id, self._settings)
        refresh, jti, expires_at = create_refresh_token(user.id, self._settings)
        self._session.add(RefreshToken(token_jti=jti, user_id=user.id, expires_at=expires_at))
        await self._session.commit()
        return user, access, refresh
