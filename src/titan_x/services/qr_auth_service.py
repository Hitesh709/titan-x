from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import secrets
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

import qrcode
from qrcode.image.svg import SvgPathImage
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.core.config import Settings
from titan_x.core.security import create_access_token, create_refresh_token, hash_password
from titan_x.db.repository import BaseRepository
from titan_x.models.auth_challenge import AuthChallenge
from titan_x.models.refresh_token import RefreshToken
from titan_x.models.user import User


class QRAuthService:
    CHALLENGE_TTL_SECONDS = 120
    EMAIL_OTP_TTL_SECONDS = 10 * 60
    EMAIL_OTP_MAX_ATTEMPTS = 5
    EMAIL_OTP_RESEND_SECONDS = 60
    BROWSER_COOKIE = "titan_x_qr_session"
    SMS_PREFIX = "TXQR:"

    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._session = session
        self._settings = settings
        self._challenge_repo = BaseRepository(session, AuthChallenge)
        self._token_repo = BaseRepository(session, RefreshToken)

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
        if raw.startswith("+") and 7 <= len(digits) <= 15:
            return "+" + digits
        if 7 <= len(digits) <= 15:
            return "+" + digits
        raise ValueError("Invalid phone number")

    def create_browser_session(self) -> str:
        return secrets.token_urlsafe(32)

    def _qr(self, raw_challenge: str, operation: str = "LOGIN") -> str:
        flow = "registration" if operation == "REGISTRATION" else "login"
        target = f"{self._settings.frontend_url.rstrip('/')}/mobile-auth?challenge={raw_challenge}&flow={flow}"
        svg = qrcode.make(target, image_factory=SvgPathImage).to_string(encoding="unicode")
        return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode("ascii")

    async def create_login_challenge(self, identifier: str, browser_session: str, ip_address: str | None, user_agent: str | None) -> tuple[AuthChallenge, str]:
        identifier = identifier.strip()
        result = await self._session.execute(select(User).where((User.email == identifier.lower()) | (User.username == identifier)))
        user = result.scalar_one_or_none()
        if user is None or not user.is_active or not user.phone:
            raise ValueError("QR login is not available for this account")
        phone = self.normalize_phone(user.phone)
        return await self._create_challenge(browser_session, "LOGIN", user.id, phone, None, None, None, None, ip_address, user_agent)

    async def create_registration_challenge(self, username: str, password: str, confirm_password: str, email: str | None, phone: str | None, browser_session: str, ip_address: str | None, user_agent: str | None) -> tuple[AuthChallenge, str]:
        if password != confirm_password:
            raise ValueError("Passwords do not match")
        email_value = email.lower().strip() if email else None
        phone_value = self.normalize_phone(phone) if phone else None
        if not email_value and not phone_value:
            raise ValueError("Email or phone is required")
        if email_value and not phone_value:
            raise ValueError("Mobile number is required for QR + SMS registration")
        checks = [select(User).where(User.username == username.strip())]
        if email_value:
            checks.append(select(User).where(User.email == email_value))
        if phone_value:
            checks.append(select(User).where(User.phone == phone_value))
        for query in checks:
            if (await self._session.execute(query)).scalar_one_or_none() is not None:
                raise ValueError("Account information is already registered")
        return await self._create_challenge(browser_session, "REGISTRATION", None, phone_value, username.strip(), email_value, phone_value, hash_password(password), ip_address, user_agent)

    async def _create_challenge(self, browser_session: str, operation: str, customer_id: int | None, verification_phone: str | None, registration_username: str | None, registration_email: str | None, registration_phone: str | None, registration_password_hash: str | None, ip_address: str | None, user_agent: str | None) -> tuple[AuthChallenge, str]:
        raw = secrets.token_urlsafe(32)
        public_id = secrets.token_urlsafe(18)
        now = self._now()
        challenge = await self._challenge_repo.create(
            challenge_id=public_id,
            challenge_hash=self._hash(raw),
            customer_id=customer_id,
            browser_session_id=self._hash(browser_session),
            status="PENDING",
            operation=operation,
            expires_at=now + timedelta(seconds=self.CHALLENGE_TTL_SECONDS),
            verification_phone=verification_phone,
            registration_username=registration_username,
            registration_email=registration_email,
            registration_phone=registration_phone,
            registration_password_hash=registration_password_hash,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return challenge, raw

    async def create_challenge(self, *args, **kwargs):
        return await self.create_login_challenge(*args, **kwargs)

    async def _get_by_raw(self, raw: str) -> AuthChallenge:
        if not raw or len(raw) > 128:
            raise ValueError("Invalid QR challenge")
        result = await self._session.execute(select(AuthChallenge).where(AuthChallenge.challenge_hash == self._hash(raw)))
        challenge = result.scalar_one_or_none()
        if challenge is None:
            raise ValueError("Invalid QR challenge")
        if challenge.expires_at <= self._now() and challenge.status in {"PENDING", "SCANNED", "APPROVED", "EMAIL_OTP_REQUIRED"}:
            challenge.status = "EXPIRED"
            await self._session.flush()
            raise ValueError("QR challenge expired")
        return challenge

    async def _send_email_otp(self, challenge: AuthChallenge) -> None:
        if not challenge.registration_email:
            return
        if not self._settings.smtp_host or not self._settings.smtp_user or not self._settings.smtp_password:
            raise ValueError("Email OTP is not configured. Please configure SMTP settings.")
        now = self._now()
        if challenge.email_otp_sent_at and (now - challenge.email_otp_sent_at).total_seconds() < self.EMAIL_OTP_RESEND_SECONDS:
            return
        otp = f"{secrets.randbelow(1_000_000):06d}"
        message = EmailMessage()
        message["Subject"] = "Titan X email verification code"
        message["From"] = f"{self._settings.smtp_from_name} <{self._settings.smtp_from_email}>"
        message["To"] = challenge.registration_email
        message.set_content(f"Your Titan X verification code is {otp}.\n\nThis code expires in {self.EMAIL_OTP_TTL_SECONDS // 60} minutes.\nDo not share this code with anyone.")

        def send() -> None:
            with smtplib.SMTP(self._settings.smtp_host, self._settings.smtp_port, timeout=15) as smtp:
                smtp.starttls()
                smtp.login(self._settings.smtp_user, self._settings.smtp_password)
                smtp.send_message(message)

        await asyncio.to_thread(send)
        challenge.email_otp_hash = self._hash(otp)
        challenge.email_otp_expires_at = now + timedelta(seconds=self.EMAIL_OTP_TTL_SECONDS)
        challenge.email_otp_attempts = 0
        challenge.email_otp_sent_at = now
        await self._session.flush()

    async def sms_approve(self, raw_challenge: str, from_number: str) -> AuthChallenge:
        challenge = await self._get_by_raw(raw_challenge)
        phone = self.normalize_phone(from_number)
        if challenge.status != "PENDING":
            raise ValueError("QR challenge is no longer pending")
        if not challenge.verification_phone or not hmac.compare_digest(phone, self.normalize_phone(challenge.verification_phone)):
            raise ValueError("SMS sender does not match the verified mobile number")
        now = self._now()
        if challenge.operation == "REGISTRATION" and challenge.registration_email:
            await self._send_email_otp(challenge)
            challenge.expires_at = now + timedelta(seconds=self.EMAIL_OTP_TTL_SECONDS)
        result = await self._session.execute(update(AuthChallenge).where(AuthChallenge.id == challenge.id, AuthChallenge.status == "PENDING", AuthChallenge.expires_at > now).values(status="APPROVED", customer_id=challenge.customer_id, scanned_at=now, approved_at=now))
        if result.rowcount != 1:
            raise ValueError("QR challenge was already used or expired")
        await self._session.flush()
        return challenge

    async def verify_registration_email_otp(self, challenge_id: str, otp: str) -> None:
        result = await self._session.execute(select(AuthChallenge).where(AuthChallenge.challenge_id == challenge_id))
        challenge = result.scalar_one_or_none()
        if challenge is None or challenge.operation != "REGISTRATION":
            raise ValueError("Invalid registration challenge")
        now = self._now()
        if challenge.expires_at <= now or challenge.status in {"EXPIRED", "CANCELLED", "DECLINED", "USED"}:
            raise ValueError("QR registration challenge expired or is no longer usable")
        if not challenge.registration_email:
            raise ValueError("Email verification is not required")
        if challenge.email_verified_at is not None:
            return
        if challenge.email_otp_expires_at is None or challenge.email_otp_expires_at <= now:
            raise ValueError("Email OTP expired")
        if challenge.email_otp_attempts >= self.EMAIL_OTP_MAX_ATTEMPTS:
            raise ValueError("Too many email OTP attempts")
        challenge.email_otp_attempts += 1
        if not hmac.compare_digest(challenge.email_otp_hash or "", self._hash(otp.strip())):
            await self._session.flush()
            raise ValueError("Invalid email OTP")
        challenge.email_verified_at = now
        challenge.email_otp_hash = None
        await self._session.flush()

    async def decline(self, raw_challenge: str, from_number: str) -> None:
        challenge = await self._get_by_raw(raw_challenge)
        phone = self.normalize_phone(from_number)
        if challenge.status != "PENDING" or not challenge.verification_phone or not hmac.compare_digest(phone, self.normalize_phone(challenge.verification_phone)):
            raise ValueError("Invalid QR decline request")
        result = await self._session.execute(update(AuthChallenge).where(AuthChallenge.id == challenge.id, AuthChallenge.status == "PENDING").values(status="DECLINED", declined_at=self._now()))
        if result.rowcount != 1:
            raise ValueError("QR challenge could not be declined")

    async def cancel(self, challenge_id: str, browser_session: str) -> None:
        result = await self._session.execute(select(AuthChallenge).where(AuthChallenge.challenge_id == challenge_id))
        challenge = result.scalar_one_or_none()
        if challenge is None or not hmac.compare_digest(challenge.browser_session_id, self._hash(browser_session)):
            raise ValueError("Invalid browser challenge session")
        if challenge.status in {"PENDING", "SCANNED", "APPROVED", "EMAIL_OTP_REQUIRED"}:
            challenge.status = "CANCELLED"
            challenge.cancelled_at = self._now()
            await self._session.flush()

    def verify_webhook(self, from_number: str, body: str, signature: str | None) -> bool:
        secret = self._settings.qr_sms_webhook_secret
        if secret is None:
            return self._settings.environment != "production"
        if not signature:
            return False
        expected = hmac.new(secret.get_secret_value().encode(), f"{from_number}|{body}".encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    async def status_and_consume(self, challenge_id: str, browser_session: str) -> tuple[str, User | None, tuple[str, str] | None]:
        result = await self._session.execute(select(AuthChallenge).where(AuthChallenge.challenge_id == challenge_id))
        challenge = result.scalar_one_or_none()
        if challenge is None or not hmac.compare_digest(challenge.browser_session_id, self._hash(browser_session)):
            raise ValueError("Invalid browser challenge session")
        if challenge.status in {"PENDING", "SCANNED", "APPROVED", "EMAIL_OTP_REQUIRED"} and challenge.expires_at <= self._now():
            challenge.status = "EXPIRED"
            await self._session.flush()
            return "EXPIRED", None, None
        if challenge.status == "DECLINED":
            return "DECLINED", None, None
        if challenge.status == "CANCELLED":
            return "CANCELLED", None, None
        if challenge.status == "PENDING":
            return "PENDING", None, None
        if challenge.operation == "REGISTRATION" and challenge.registration_email and challenge.email_verified_at is None:
            return "EMAIL_OTP_REQUIRED", None, None
        if challenge.status != "APPROVED":
            return challenge.status, None, None
        if challenge.operation == "REGISTRATION":
            existing = await self._session.execute(select(User).where(User.username == challenge.registration_username))
            if existing.scalar_one_or_none() is not None:
                raise ValueError("Username is already registered")
            user = User(username=challenge.registration_username, email=challenge.registration_email, phone=challenge.registration_phone, hashed_password=challenge.registration_password_hash or "", is_active=True, is_verified=True, role="normal")
            self._session.add(user)
            await self._session.flush()
        else:
            user = await self._session.get(User, challenge.customer_id) if challenge.customer_id else None
            if user is None or not user.is_active:
                raise ValueError("Account is inactive")
        consumed = await self._session.execute(update(AuthChallenge).where(AuthChallenge.id == challenge.id, AuthChallenge.status == "APPROVED").values(status="USED", used_at=self._now()).returning(AuthChallenge.id))
        if consumed.first() is None:
            return "USED", None, None
        access = create_access_token(user.id, self._settings)
        refresh, jti, expires_at = create_refresh_token(user.id, self._settings)
        await self._token_repo.create(token_jti=jti, user_id=user.id, expires_at=expires_at)
        await self._session.flush()
        return "USED", user, (access, refresh)
