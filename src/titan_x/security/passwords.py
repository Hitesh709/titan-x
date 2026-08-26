"""Password hashing helpers.

Argon2id is preferred for new credentials. Existing password migration should be
performed at login rather than storing plaintext or reversible passwords.
"""
from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, encoded_hash: str) -> bool:
    try:
        return _hasher.verify(encoded_hash, password)
    except (VerifyMismatchError, VerificationError):
        return False


def needs_rehash(encoded_hash: str) -> bool:
    return _hasher.check_needs_rehash(encoded_hash)
