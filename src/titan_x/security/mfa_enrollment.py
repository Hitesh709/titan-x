"""Framework-neutral MFA enrollment service helpers."""
from __future__ import annotations

from titan_x.security.mfa import build_totp_uri, generate_recovery_codes, generate_totp_secret, verify_totp
from titan_x.security.mfa_storage import encrypt_mfa_secret, hash_recovery_code


def begin_enrollment(email: str) -> tuple[str, str, list[str], list[str]]:
    secret = generate_totp_secret()
    uri = build_totp_uri(secret, email)
    codes = generate_recovery_codes()
    return secret, encrypt_mfa_secret(secret), uri, [hash_recovery_code(c) for c in codes]


def confirm_enrollment(encrypted_secret: str, code: str, decrypt_secret) -> bool:
    secret = decrypt_secret(encrypted_secret)
    return verify_totp(secret, code)
