from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.core.config import Settings
from titan_x.core.security import (
    create_access_token,
    create_email_verification_token,
    create_password_reset_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from titan_x.db.repository import BaseRepository
from titan_x.models.refresh_token import RefreshToken
from titan_x.models.user import User


class AuthService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._session = session
        self._settings = settings
        self._user_repo = BaseRepository(session, User)
        self._token_repo = BaseRepository(session, RefreshToken)

    async def register(self, email: str, password: str) -> User:
        existing = await self._user_repo.get_multi(email=email, limit=1)
        if existing:
            raise ValueError("Email already registered")

        user = await self._user_repo.create(
            email=email,
            hashed_password=hash_password(password),
        )
        return user

    async def authenticate(self, email: str, password: str) -> User:
        result = await self._session.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if user is None or not verify_password(password, user.hashed_password):
            raise ValueError("Invalid email or password")
        return user

    async def issue_tokens(self, user: User) -> tuple[str, str, str]:
        access_token = create_access_token(user.id, self._settings)
        refresh_token, jti, expires_at = create_refresh_token(user.id, self._settings)
        await self._token_repo.create(
            token_jti=jti,
            user_id=user.id,
            expires_at=expires_at,
        )
        return access_token, refresh_token, jti

    async def login(self, email: str, password: str) -> tuple[User, str, str, str]:
        user = await self.authenticate(email, password)
        access_token, refresh_token, jti = await self.issue_tokens(user)
        return user, access_token, refresh_token, jti

    async def refresh(self, refresh_token_jti: str, user_id: int) -> tuple[str, str, str]:
        result = await self._session.execute(
            select(RefreshToken).where(
                RefreshToken.token_jti == refresh_token_jti,
                RefreshToken.user_id == user_id,
            )
        )
        token_record = result.scalar_one_or_none()
        if token_record is None or token_record.is_revoked:
            raise ValueError("Invalid or revoked refresh token")
        if token_record.is_expired:
            raise ValueError("Refresh token expired")

        token_record.revoked_at = datetime.now(timezone.utc)
        new_access = create_access_token(user_id, self._settings)
        new_refresh, new_jti, new_expires = create_refresh_token(user_id, self._settings)
        await self._token_repo.create(
            token_jti=new_jti,
            user_id=user_id,
            expires_at=new_expires,
        )
        return new_access, new_refresh, new_jti

    async def logout(self, refresh_token_jti: str, user_id: int) -> None:
        result = await self._session.execute(
            select(RefreshToken).where(
                RefreshToken.token_jti == refresh_token_jti,
                RefreshToken.user_id == user_id,
                RefreshToken.revoked_at.is_(None),
            )
        )
        token_record = result.scalar_one_or_none()
        if token_record is not None:
            token_record.revoked_at = datetime.now(timezone.utc)

    async def forgot_password(self, email: str) -> str | None:
        result = await self._session.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if user is None:
            return None
        return create_password_reset_token(user.id, user.email, self._settings)

    async def reset_password(self, token: str, new_password: str) -> None:
        try:
            payload = decode_token(
                token,
                self._settings.jwt_secret_key.get_secret_value(),
                self._settings.jwt_algorithm,
            )
        except ValueError:
            raise ValueError("Invalid or expired reset token")

        if payload.get("type") != "password_reset":
            raise ValueError("Invalid token type")

        user_id = int(payload["sub"])
        user = await self._user_repo.get(user_id)
        if user is None:
            raise ValueError("User not found")

        await self._user_repo.update(user.id, hashed_password=hash_password(new_password))

        # Password reset is a security boundary: immediately invalidate every
        # outstanding refresh session so a stolen/old session cannot survive a
        # credential change.
        await self._session.execute(
            update(RefreshToken)
            .where(
                RefreshToken.user_id == user.id,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.now(timezone.utc))
        )

    async def verify_email(self, token: str) -> None:
        try:
            payload = decode_token(
                token,
                self._settings.jwt_secret_key.get_secret_value(),
                self._settings.jwt_algorithm,
            )
        except ValueError:
            raise ValueError("Invalid or expired verification token")

        if payload.get("type") != "email_verification":
            raise ValueError("Invalid token type")

        user_id = int(payload["sub"])
        user = await self._user_repo.get(user_id)
        if user is None:
            raise ValueError("User not found")

        await self._user_repo.update(user.id, is_verified=True)

    def decode_refresh_token(self, token: str) -> tuple[str, int]:
        """Return (jti, user_id) from a refresh token JWT."""
        try:
            payload = decode_token(
                token,
                self._settings.jwt_secret_key.get_secret_value(),
                self._settings.jwt_algorithm,
            )
        except ValueError:
            raise ValueError("Invalid or expired refresh token")
        if payload.get("type") != "refresh":
            raise ValueError("Invalid token type")
        return str(payload["jti"]), int(payload["sub"])

    def decode_mfa_challenge(self, token: str) -> int:
        try:
            payload = decode_token(
                token,
                self._settings.jwt_secret_key.get_secret_value(),
                self._settings.jwt_algorithm,
            )
        except ValueError:
            raise ValueError("Invalid or expired MFA challenge")
        if payload.get("type") != "mfa_challenge":
            raise ValueError("Invalid MFA challenge")
        return int(payload["sub"])

    async def create_verification_token(self, user_id: int, email: str) -> str:
        user = await self._user_repo.get(user_id)
        if user is None:
            raise ValueError("User not found")
        if user.is_verified:
            raise ValueError("Email already verified")
        return create_email_verification_token(user.id, user.email, self._settings)

    async def get_user_for_verification(self, email: str) -> tuple[User, str] | None:
        """Return (user, verification_token) for an unverified user, else None."""
        result = await self._session.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if user is None or user.is_verified:
            return None
        return user, create_email_verification_token(user.id, user.email, self._settings)
