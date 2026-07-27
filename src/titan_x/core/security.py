import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from titan_x.core.config import Settings

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return _pwd_context.verify(plain_password, hashed_password)


def generate_jti() -> str:
    return secrets.token_hex(32)


def _create_token(
    payload: dict[str, Any],
    secret_key: str,
    algorithm: str,
    expires_delta: timedelta,
) -> str:
    to_encode = payload.copy()
    now = datetime.now(timezone.utc)
    to_encode.update({"iat": now, "exp": now + expires_delta})
    return jwt.encode(to_encode, secret_key, algorithm=algorithm)


def create_access_token(
    user_id: int,
    settings: Settings,
    expires_delta: timedelta | None = None,
) -> str:
    expire = expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    return _create_token(
        payload={"sub": str(user_id), "type": "access", "jti": generate_jti()},
        secret_key=settings.jwt_secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
        expires_delta=expire,
    )


def create_refresh_token(
    user_id: int,
    settings: Settings,
    expires_delta: timedelta | None = None,
) -> tuple[str, str, datetime]:
    jti = generate_jti()
    expire = expires_delta or timedelta(days=settings.refresh_token_expire_days)
    expires_at = datetime.now(timezone.utc) + expire
    token = _create_token(
        payload={"sub": str(user_id), "type": "refresh", "jti": jti},
        secret_key=settings.jwt_secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
        expires_delta=expire,
    )
    return token, jti, expires_at


def create_password_reset_token(user_id: int, email: str, settings: Settings) -> str:
    expire = timedelta(minutes=settings.password_reset_token_expire_minutes)
    return _create_token(
        payload={
            "sub": str(user_id),
            "email": email,
            "type": "password_reset",
            "jti": generate_jti(),
        },
        secret_key=settings.jwt_secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
        expires_delta=expire,
    )


def create_email_verification_token(user_id: int, email: str, settings: Settings) -> str:
    expire = timedelta(hours=settings.email_verification_token_expire_hours)
    return _create_token(
        payload={
            "sub": str(user_id),
            "email": email,
            "type": "email_verification",
            "jti": generate_jti(),
        },
        secret_key=settings.jwt_secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
        expires_delta=expire,
    )


def decode_token(token: str, secret_key: str, algorithm: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, secret_key, algorithms=[algorithm])
    except JWTError:
        raise ValueError("Invalid or expired token")
    return payload
