from __future__ import annotations
import base64, hashlib, secrets
from datetime import datetime, timedelta, timezone
import qrcode
from qrcode.image.svg import SvgPathImage
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat, load_pem_public_key
from titan_x.core.config import Settings
from titan_x.core.security import create_access_token, create_refresh_token
from titan_x.db.repository import BaseRepository
from titan_x.models.auth_challenge import AuthChallenge
from titan_x.models.refresh_token import RefreshToken
from titan_x.models.user import User
from titan_x.models.user_device import UserDevice

class QRAuthService:
    CHALLENGE_TTL_SECONDS = 60
    BROWSER_COOKIE = "titan_x_qr_session"
    QR_PREFIX = "titan-x:qr-login:"
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._session = session; self._settings = settings; self._challenge_repo = BaseRepository(session, AuthChallenge); self._device_repo = BaseRepository(session, UserDevice); self._token_repo = BaseRepository(session, RefreshToken)
    @staticmethod
    def _hash(value: str) -> str: return hashlib.sha256(value.encode("utf-8")).hexdigest()
    @staticmethod
    def _now() -> datetime: return datetime.now(timezone.utc)
    def create_browser_session(self) -> str: return secrets.token_urlsafe(32)
    async def create_challenge(self, browser_session: str, ip_address: str | None, user_agent: str | None) -> tuple[AuthChallenge, str, str]:
        raw_challenge = secrets.token_urlsafe(32); public_id = secrets.token_urlsafe(18); now = self._now()
        challenge = await self._challenge_repo.create(challenge_id=public_id, challenge_hash=self._hash(raw_challenge), browser_session_id=self._hash(browser_session), status="PENDING", expires_at=now + timedelta(seconds=self.CHALLENGE_TTL_SECONDS), ip_address=ip_address, user_agent=user_agent)
        qr_target = f"{self._settings.frontend_url.rstrip('/')}/mobile-auth?challenge={raw_challenge}"
        qr_svg = qrcode.make(qr_target, image_factory=SvgPathImage).to_string(encoding="unicode")
        qr_data_url = "data:image/svg+xml;base64," + base64.b64encode(qr_svg.encode("utf-8")).decode("ascii")
        return challenge, raw_challenge, qr_data_url
    async def register_device(self, user: User, device_name: str, public_key: str) -> UserDevice:
        try: key = load_pem_public_key(public_key.encode("utf-8"))
        except (ValueError, TypeError) as exc: raise ValueError("Invalid device public key") from exc
        if not isinstance(key, Ed25519PublicKey): raise ValueError("Only Ed25519 device public keys are supported")
        normalized = key.public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo).decode("utf-8")
        existing = await self._session.execute(select(UserDevice).where(UserDevice.customer_id == user.id, UserDevice.device_public_key == normalized, UserDevice.revoked_at.is_(None)))
        if existing.scalar_one_or_none() is not None: raise ValueError("Device is already registered")
        return await self._device_repo.create(customer_id=user.id, device_name=device_name.strip()[:120] or "Registered mobile", device_public_key=normalized, device_status="active")
    async def revoke_device(self, user: User, device_id: int) -> None:
        device = await self._device_repo.get(device_id)
        if device is None or device.customer_id != user.id: raise ValueError("Device not found")
        device.device_status = "revoked"; device.revoked_at = self._now()
    async def _get_by_raw(self, raw_challenge: str) -> AuthChallenge:
        if not raw_challenge or len(raw_challenge) > 128: raise ValueError("Invalid QR challenge")
        result = await self._session.execute(select(AuthChallenge).where(AuthChallenge.challenge_hash == self._hash(raw_challenge)))
        challenge = result.scalar_one_or_none()
        if challenge is None: raise ValueError("Invalid QR challenge")
        if challenge.expires_at <= self._now() and challenge.status in {"PENDING", "SCANNED"}: challenge.status = "EXPIRED"; raise ValueError("QR challenge expired")
        return challenge
    async def _get_by_public_id(self, challenge_id: str) -> AuthChallenge:
        if not challenge_id or len(challenge_id) > 64: raise ValueError("Invalid QR challenge")
        result = await self._session.execute(select(AuthChallenge).where(AuthChallenge.challenge_id == challenge_id))
        challenge = result.scalar_one_or_none()
        if challenge is None: raise ValueError("Invalid QR challenge")
        if challenge.expires_at <= self._now() and challenge.status in {"PENDING", "SCANNED"}: challenge.status = "EXPIRED"; raise ValueError("QR challenge expired")
        return challenge
    async def scan(self, raw_challenge: str, user: User, device_id: int) -> AuthChallenge:
        device = await self._device_repo.get(device_id)
        if device is None or device.customer_id != user.id or not device.is_active: raise ValueError("Invalid or revoked device")
        challenge = await self._get_by_raw(raw_challenge)
        if challenge.status != "PENDING": raise ValueError("QR challenge is no longer pending")
        now = self._now(); result = await self._session.execute(update(AuthChallenge).where(AuthChallenge.id == challenge.id, AuthChallenge.status == "PENDING", AuthChallenge.expires_at > now).values(status="SCANNED", customer_id=user.id, device_id=device.id, scanned_at=now))
        if result.rowcount != 1: raise ValueError("QR challenge was already claimed")
        device.last_seen_at = now; await self._session.flush(); return challenge
    async def approve(self, raw_challenge: str, user: User, device_id: int, signature_b64: str) -> AuthChallenge:
        device = await self._device_repo.get(device_id)
        if device is None or device.customer_id != user.id or not device.is_active: raise ValueError("Invalid or revoked device")
        challenge = await self._get_by_raw(raw_challenge)
        if challenge.status != "SCANNED" or challenge.customer_id != user.id or challenge.device_id != device.id: raise ValueError("QR challenge is not awaiting approval")
        try:
            public_key = load_pem_public_key(device.device_public_key.encode("utf-8"))
            if not isinstance(public_key, Ed25519PublicKey): raise ValueError("Unsupported device key")
            signature = base64.b64decode(signature_b64, validate=True); public_key.verify(signature, (self.QR_PREFIX + raw_challenge).encode("utf-8"))
        except (ValueError, InvalidSignature, UnicodeError) as exc: raise ValueError("Invalid device signature") from exc
        now = self._now(); result = await self._session.execute(update(AuthChallenge).where(AuthChallenge.id == challenge.id, AuthChallenge.status == "SCANNED", AuthChallenge.customer_id == user.id, AuthChallenge.device_id == device.id, AuthChallenge.expires_at > now).values(status="APPROVED", approved_at=now))
        if result.rowcount != 1: raise ValueError("QR challenge could not be approved")
        device.last_seen_at = now; await self._session.flush(); return challenge
    async def decline(self, raw_challenge: str, user: User, device_id: int) -> None:
        device = await self._device_repo.get(device_id)
        if device is None or device.customer_id != user.id or not device.is_active: raise ValueError("Invalid or revoked device")
        challenge = await self._get_by_raw(raw_challenge)
        if challenge.status != "SCANNED" or challenge.customer_id != user.id or challenge.device_id != device.id: raise ValueError("QR challenge is not awaiting decision")
        result = await self._session.execute(update(AuthChallenge).where(AuthChallenge.id == challenge.id, AuthChallenge.status == "SCANNED").values(status="DECLINED", declined_at=self._now()))
        if result.rowcount != 1: raise ValueError("QR challenge could not be declined")
    async def cancel(self, challenge_id: str, browser_session: str) -> None:
        challenge = await self._get_by_public_id(challenge_id)
        if challenge.browser_session_id != self._hash(browser_session): raise ValueError("Invalid browser challenge session")
        if challenge.status in {"PENDING", "SCANNED"}: challenge.status = "CANCELLED"; challenge.cancelled_at = self._now()
    async def status_and_consume(self, challenge_id: str, browser_session: str) -> tuple[str, User | None, tuple[str, str] | None]:
        challenge = await self._get_by_public_id(challenge_id)
        if not secrets.compare_digest(challenge.browser_session_id, self._hash(browser_session)): raise ValueError("Invalid browser challenge session")
        if challenge.status in {"PENDING", "SCANNED"} and challenge.expires_at <= self._now(): challenge.status = "EXPIRED"; return "EXPIRED", None, None
        if challenge.status == "DECLINED": return "DECLINED", None, None
        if challenge.status != "APPROVED" or challenge.customer_id is None: return challenge.status, None, None
        result = await self._session.execute(update(AuthChallenge).where(AuthChallenge.id == challenge.id, AuthChallenge.status == "APPROVED").values(status="USED", used_at=self._now()).returning(AuthChallenge.customer_id))
        row = result.first()
        if row is None: return "USED", None, None
        user = await self._session.get(User, int(row[0]))
        if user is None or not user.is_active: raise ValueError("Account is inactive")
        access = create_access_token(user.id, self._settings); refresh, jti, expires_at = create_refresh_token(user.id, self._settings)
        await self._token_repo.create(token_jti=jti, user_id=user.id, expires_at=expires_at); await self._session.flush()
        return "USED", user, (access, refresh)
