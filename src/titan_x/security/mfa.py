"""TOTP MFA primitives for Titan-X.

Secrets must be encrypted at rest in production. Enrollment should require
recent authentication and recovery codes should be stored hashed.
"""
from __future__ import annotations

import base64
import secrets

import pyotp


def generate_totp_secret() -> str:
    return pyotp.random_base32()


def build_totp_uri(secret: str, email: str, issuer: str = "Titan-X") -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=issuer)


def verify_totp(secret: str, code: str) -> bool:
    if not code.isdigit() or len(code) != 6:
        return False
    return pyotp.TOTP(secret).verify(code, valid_window=1)


def generate_recovery_codes(count: int = 10) -> list[str]:
    return [base64.b32encode(secrets.token_bytes(5)).decode().rstrip("=") for _ in range(count)]
