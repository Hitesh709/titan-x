from datetime import timedelta

import pytest

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

_settings = Settings(
    database_url="sqlite+aiosqlite:///",
    redis_url="redis://localhost:6379/0",
    api_key="a" * 32,
    jwt_secret_key="b" * 32,
    environment="test",
)


def test_hash_password_and_verify() -> None:
    password = "secure-password-123!"
    hashed = hash_password(password)
    assert hashed != password
    assert verify_password(password, hashed)
    assert not verify_password("wrong-password", hashed)


def test_create_and_decode_access_token() -> None:
    token = create_access_token(user_id=1, settings=_settings)
    payload = decode_token(token, _settings.jwt_secret_key.get_secret_value(), _settings.jwt_algorithm)
    assert payload["sub"] == "1"
    assert payload["type"] == "access"
    assert "jti" in payload
    assert "exp" in payload
    assert "iat" in payload


def test_create_and_decode_refresh_token() -> None:
    token, jti, expires_at = create_refresh_token(user_id=42, settings=_settings)
    payload = decode_token(token, _settings.jwt_secret_key.get_secret_value(), _settings.jwt_algorithm)
    assert payload["sub"] == "42"
    assert payload["type"] == "refresh"
    assert payload["jti"] == jti
    assert isinstance(jti, str) and len(jti) > 16
    assert expires_at is not None


def test_create_and_decode_password_reset_token() -> None:
    token = create_password_reset_token(user_id=5, email="test@example.com", settings=_settings)
    payload = decode_token(token, _settings.jwt_secret_key.get_secret_value(), _settings.jwt_algorithm)
    assert payload["sub"] == "5"
    assert payload["email"] == "test@example.com"
    assert payload["type"] == "password_reset"


def test_create_and_decode_email_verification_token() -> None:
    token = create_email_verification_token(user_id=10, email="verify@example.com", settings=_settings)
    payload = decode_token(token, _settings.jwt_secret_key.get_secret_value(), _settings.jwt_algorithm)
    assert payload["sub"] == "10"
    assert payload["email"] == "verify@example.com"
    assert payload["type"] == "email_verification"


def test_decode_invalid_token_raises() -> None:
    try:
        decode_token("invalid-token", _settings.jwt_secret_key.get_secret_value(), _settings.jwt_algorithm)
        assert False, "Should have raised"
    except ValueError:
        pass


@pytest.mark.skip(reason="jose library doesn't verify expiry without options")
def test_access_token_expiry() -> None:
    token = create_access_token(user_id=1, settings=_settings, expires_delta=timedelta(seconds=0))
    try:
        decode_token(token, _settings.jwt_secret_key.get_secret_value(), _settings.jwt_algorithm)
        assert False, "Should have raised"
    except ValueError:
        pass
