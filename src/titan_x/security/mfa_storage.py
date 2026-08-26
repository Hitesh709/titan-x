"""Helpers for safely handling MFA secrets and recovery codes.

Production deployments must set MFA_ENCRYPTION_KEY to a Fernet key and keep it
outside source control. Recovery codes are returned only at enrollment time;
callers should hash them before persistence.
"""
from __future__ import annotations

import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken


def _fernet() -> Fernet:
    key = os.getenv("MFA_ENCRYPTION_KEY")
    if not key:
        raise RuntimeError("MFA_ENCRYPTION_KEY is required for MFA secret storage")
    return Fernet(key.encode())


def encrypt_mfa_secret(secret: str) -> str:
    return _fernet().encrypt(secret.encode()).decode()


def decrypt_mfa_secret(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise ValueError("Invalid encrypted MFA secret") from exc


def hash_recovery_code(code: str) -> str:
    return hashlib.sha256(code.strip().encode()).hexdigest()
