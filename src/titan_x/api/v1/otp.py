from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr

from titan_x.api.dependencies import get_auth_service
from titan_x.services.auth_service import AuthService
from titan_x.services.otp_service import OtpService

otp_router = APIRouter(tags=["auth-otp"])


class EmailOtpRequest(BaseModel):
    email: EmailStr


class VerifyEmailOtpRequest(BaseModel):
    email: EmailStr
    otp: str


class OtpResponse(BaseModel):
    message: str
    expires_in_seconds: int | None = None


@otp_router.post("/auth/otp/email/request", response_model=OtpResponse)
async def request_email_otp(
    body: EmailOtpRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> OtpResponse:
    # Provider-independent endpoint. Delivery is connected through the configured
    # email service before enabling this endpoint for public production traffic.
    from titan_x.api.dependencies import get_db_session
    session = await get_db_session()
    otp = OtpService(session)
    try:
        code, expires_at = await otp.request_email_otp(str(body.email))
        await service.send_otp_email(str(body.email), code)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc))
    return OtpResponse(message="OTP sent", expires_in_seconds=max(0, int((expires_at - __import__('datetime').datetime.now(__import__('datetime').timezone.utc)).total_seconds())))


@otp_router.post("/auth/otp/email/verify", response_model=OtpResponse)
async def verify_email_otp(body: VerifyEmailOtpRequest) -> OtpResponse:
    from titan_x.api.dependencies import get_db_session
    session = await get_db_session()
    otp = OtpService(session)
    try:
        await otp.verify_email_otp(str(body.email), body.otp)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return OtpResponse(message="Email verified successfully")
