"""User-facing MFA enrollment and verification endpoints.

MFA is opt-in. Enrollment requires an authenticated user and a fresh TOTP
verification before the account is marked MFA-enabled.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.api.dependencies import get_current_active_user
from titan_x.db.session import get_db
from titan_x.models.user import User
from titan_x.security.mfa import verify_totp
from titan_x.security.mfa_enrollment import begin_enrollment
from titan_x.security.mfa_storage import decrypt_mfa_secret, encrypt_mfa_secret, hash_recovery_code

router = APIRouter(prefix="/mfa", tags=["MFA"])


class EnrollmentResponse(BaseModel):
    provisioning_uri: str
    recovery_codes: list[str]


class VerifyRequest(BaseModel):
    code: str = Field(pattern=r"^\d{6}$")


@router.post("/enroll", response_model=EnrollmentResponse)
async def enroll_mfa(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    if current_user.mfa_enabled:
        raise HTTPException(status_code=409, detail="MFA is already enabled")
    secret, encrypted, uri, recovery_codes = begin_enrollment(current_user.email)
    current_user.mfa_secret_encrypted = encrypted
    await db.commit()
    # The plaintext secret is deliberately not returned. The provisioning URI
    # contains the secret and is shown once to the authenticated user.
    return EnrollmentResponse(provisioning_uri=uri, recovery_codes=recovery_codes)


@router.post("/verify")
async def verify_mfa_enrollment(
    payload: VerifyRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
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


@router.post("/disable")
async def disable_mfa(
    payload: VerifyRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    if not current_user.mfa_enabled or not current_user.mfa_secret_encrypted:
        return {"mfa_enabled": False}
    secret = decrypt_mfa_secret(current_user.mfa_secret_encrypted)
    if not verify_totp(secret, payload.code):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid MFA code")
    current_user.mfa_enabled = False
    current_user.mfa_secret_encrypted = None
    await db.commit()
    return {"mfa_enabled": False}
