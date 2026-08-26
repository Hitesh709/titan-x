"""User-facing MFA enrollment, recovery, and verification endpoints.

MFA is opt-in. Enrollment requires an authenticated user and a fresh TOTP
verification before the account is marked MFA-enabled. TOTP secrets are
encrypted at rest and recovery codes are stored only as hashes and consumed
once when used.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.api.dependencies import get_current_active_user, get_db
from titan_x.models.user import User
from titan_x.security.mfa import generate_recovery_codes, verify_totp
from titan_x.security.mfa_enrollment import begin_enrollment
from titan_x.security.mfa_storage import decrypt_mfa_secret, hash_recovery_code

router = APIRouter(prefix="/mfa", tags=["MFA"])


class EnrollmentResponse(BaseModel):
    provisioning_uri: str
    recovery_codes: list[str]


class VerifyRequest(BaseModel):
    code: str = Field(pattern=r"^\d{6}$")


class RecoveryCodeRequest(BaseModel):
    code: str = Field(min_length=8, max_length=64)


def _recovery_hashes(user: User) -> list[str]:
    if not user.mfa_recovery_codes_hashes:
        return []
    try:
        values = json.loads(user.mfa_recovery_codes_hashes)
    except (TypeError, ValueError):
        return []
    return [str(value) for value in values if isinstance(value, str)]


def _store_recovery_hashes(user: User, hashes: list[str]) -> None:
    user.mfa_recovery_codes_hashes = json.dumps(hashes, separators=(",", ":"))


def _consume_recovery_code(user: User, code: str) -> bool:
    candidate = hash_recovery_code(code)
    hashes = _recovery_hashes(user)
    if candidate not in hashes:
        return False
    hashes.remove(candidate)
    _store_recovery_hashes(user, hashes)
    return True


@router.post("/enroll", response_model=EnrollmentResponse)
async def enroll_mfa(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.mfa_enabled:
        raise HTTPException(status_code=409, detail="MFA is already enabled")
    _, encrypted, uri, recovery_codes = begin_enrollment(current_user.email)
    current_user.mfa_secret_encrypted = encrypted
    current_user.mfa_recovery_codes_hashes = json.dumps(
        [hash_recovery_code(code) for code in recovery_codes],
        separators=(",", ":"),
    )
    await db.commit()
    return EnrollmentResponse(provisioning_uri=uri, recovery_codes=recovery_codes)


@router.post("/verify")
async def verify_mfa_enrollment(
    payload: VerifyRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.mfa_enabled:
        raise HTTPException(status_code=409, detail="MFA is already enabled")
    if not current_user.mfa_secret_encrypted:
        raise HTTPException(status_code=400, detail="Start MFA enrollment first")
    secret = decrypt_mfa_secret(current_user.mfa_secret_encrypted)
    if not verify_totp(secret, payload.code):
        raise HTTPException(status_code=400, detail="Invalid MFA code")
    current_user.mfa_enabled = True
    await db.commit()
    return {"mfa_enabled": True}


@router.post("/recovery/verify")
async def verify_recovery_code(
    payload: RecoveryCodeRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    if not current_user.mfa_enabled:
        raise HTTPException(status_code=400, detail="MFA is not enabled")
    if not _consume_recovery_code(current_user, payload.code):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or already used recovery code")
    await db.commit()
    remaining = len(_recovery_hashes(current_user))
    return {"verified": True, "remaining_recovery_codes": remaining}


@router.post("/recovery/regenerate", response_model=EnrollmentResponse)
async def regenerate_recovery_codes(
    payload: VerifyRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    if not current_user.mfa_enabled or not current_user.mfa_secret_encrypted:
        raise HTTPException(status_code=400, detail="MFA is not enabled")
    secret = decrypt_mfa_secret(current_user.mfa_secret_encrypted)
    if not verify_totp(secret, payload.code):
        raise HTTPException(status_code=400, detail="Invalid MFA code")

    recovery_codes = generate_recovery_codes()
    _store_recovery_hashes(current_user, [hash_recovery_code(code) for code in recovery_codes])
    await db.commit()
    return EnrollmentResponse(
        provisioning_uri="",
        recovery_codes=recovery_codes,
    )


@router.post("/disable")
async def disable_mfa(
    payload: VerifyRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    if not current_user.mfa_enabled or not current_user.mfa_secret_encrypted:
        return {"mfa_enabled": False}
    secret = decrypt_mfa_secret(current_user.mfa_secret_encrypted)
    if not verify_totp(secret, payload.code):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid MFA code")
    current_user.mfa_enabled = False
    current_user.mfa_secret_encrypted = None
    current_user.mfa_recovery_codes_hashes = None
    await db.commit()
    return {"mfa_enabled": False}
