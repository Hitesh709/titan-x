from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field

from titan_x.api.dependencies import (
    get_auth_service,
    get_brute_force_protector,
    get_current_active_user,
    get_rate_limiter,
)
from titan_x.api.schemas import (
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    LogoutRequest,
    MFALoginRequest,
    MessageResponse,
    RefreshTokenRequest,
    RefreshTokenResponse,
    RegisterRequest,
    RegisterResponse,
    ResetPasswordRequest,
    SendVerificationRequest,
    SendVerificationResponse,
    TokenResponse,
    VerifyEmailRequest,
)
from titan_x.core.config import Settings, get_settings
from titan_x.core.security import create_mfa_challenge_token
from titan_x.infrastructure.brute_force_protection import BruteForceProtector
from titan_x.infrastructure.rate_limiter import RateLimiter
from titan_x.models.user import User
from titan_x.services.auth_service import AuthService
from titan_x.services.email_registration_service import EmailRegistrationService


auth_router = APIRouter(tags=["auth"])


class EmailRegistrationRequest(BaseModel):
    username: str = Field(min_length=3, max_length=80, pattern=r"^[A-Za-z0-9_.-]+$")
    email: EmailStr
    phone: str = Field(min_length=7, max_length=32)
    password: str = Field(min_length=8, max_length=128)
    confirm_password: str = Field(min_length=8, max_length=128)


class EmailRegistrationCreateResponse(BaseModel):
    challenge_id: str
    expires_in_seconds: int
    message: str


@auth_router.post("/auth/register/email-otp/create", response_model=EmailRegistrationCreateResponse)
async def create_email_otp_registration(
    body: EmailRegistrationRequest,
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    rate_limiter: Annotated[RateLimiter | None, Depends(get_rate_limiter)],
) -> EmailRegistrationCreateResponse:
    if rate_limiter is not None and settings.rate_limit_enabled:
        allowed, _, _ = await rate_limiter.check(
            f"signup-email-otp:{body.email.lower()}", 5, 300
        )
        if not allowed:
            raise HTTPException(status_code=429, detail="Too many signup attempts. Try again later.")

    async with request.app.state.session_factory() as session:
        service = EmailRegistrationService(session, settings)
        try:
            challenge_id, _ = await service.create(
                username=body.username,
                email=str(body.email),
                phone=body.phone,
                password=body.password,
                confirm_password=body.confirm_password,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return EmailRegistrationCreateResponse(
        challenge_id=challenge_id,
        expires_in_seconds=EmailRegistrationService.OTP_TTL_SECONDS,
        message="Verification OTP sent to your email address.",
    )


@auth_router.post("/auth/register/email-otp/verify", response_model=TokenResponse)
async def verify_email_otp_registration(
    body: dict,
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    rate_limiter: Annotated[RateLimiter | None, Depends(get_rate_limiter)],
) -> TokenResponse:
    challenge_id = str(body.get("challenge_id", "")).strip()
    otp = str(body.get("otp", "")).strip()
    if len(challenge_id) < 16 or not otp.isdigit() or len(otp) != 6:
        raise HTTPException(status_code=400, detail="Invalid verification request")

    if rate_limiter is not None and settings.rate_limit_enabled:
        allowed, _, _ = await rate_limiter.check(
            f"signup-email-otp-verify:{challenge_id}", 10, 300
        )
        if not allowed:
            raise HTTPException(status_code=429, detail="Too many OTP attempts. Try again later.")

    async with request.app.state.session_factory() as session:
        service = EmailRegistrationService(session, settings)
        try:
            _, access, refresh = await service.verify(challenge_id, otp)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return TokenResponse(access_token=access, refresh_token=refresh)


@auth_router.post("/auth/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, service: Annotated[AuthService, Depends(get_auth_service)]) -> RegisterResponse:
    try:
        user = await service.register(email=body.email, password=body.password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return RegisterResponse(id=user.id, email=user.email, role=user.role, is_active=user.is_active, is_verified=user.is_verified)


@auth_router.post("/auth/login", response_model=TokenResponse)
async def login(body: LoginRequest, service: Annotated[AuthService, Depends(get_auth_service)], rate_limiter: Annotated[RateLimiter | None, Depends(get_rate_limiter)], brute_force: Annotated[BruteForceProtector | None, Depends(get_brute_force_protector)], settings: Annotated[Settings, Depends(get_settings)]) -> TokenResponse:
    if rate_limiter is not None and settings.rate_limit_enabled:
        allowed, _, _ = await rate_limiter.check(f"login:{body.email}", settings.rate_limit_requests, settings.rate_limit_window_seconds)
        if not allowed:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many requests")
    if brute_force is not None:
        blocked = await brute_force.is_blocked(body.email, settings.brute_force_max_attempts, settings.brute_force_window_minutes, settings.brute_force_block_minutes)
        if blocked:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Account temporarily blocked. Try again later.")
    try:
        user = await service.authenticate(email=body.email, password=body.password)
    except ValueError as exc:
        if brute_force is not None and settings.rate_limit_enabled:
            await brute_force.record_failure_sorted(body.email, settings.brute_force_max_attempts, settings.brute_force_window_minutes, settings.brute_force_block_minutes)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))
    if brute_force is not None:
        await brute_force.reset_attempts(body.email)
    if user.mfa_enabled:
        challenge = create_mfa_challenge_token(user.id, settings)
        return TokenResponse(mfa_required=True, mfa_challenge=challenge)
    access, refresh, _ = await service.issue_tokens(user)
    return TokenResponse(access_token=access, refresh_token=refresh)


@auth_router.post("/auth/mfa-login", response_model=TokenResponse)
async def mfa_login(body: MFALoginRequest, service: Annotated[AuthService, Depends(get_auth_service)], rate_limiter: Annotated[RateLimiter | None, Depends(get_rate_limiter)], settings: Annotated[Settings, Depends(get_settings)]) -> TokenResponse:
    user_id = service.decode_mfa_challenge(body.challenge)
    if rate_limiter is not None and settings.rate_limit_enabled:
        allowed, _, _ = await rate_limiter.check(f"mfa-login:{user_id}", 5, 300)
        if not allowed:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many MFA attempts")
    user = await service.get_user(user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid MFA challenge")
    try:
        access, refresh, _ = await service.complete_mfa_login(user, body.code.strip())
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))
    return TokenResponse(access_token=access, refresh_token=refresh)


@auth_router.post("/auth/refresh", response_model=RefreshTokenResponse)
async def refresh(body: RefreshTokenRequest, service: Annotated[AuthService, Depends(get_auth_service)]) -> RefreshTokenResponse:
    try:
        jti, user_id = service.decode_refresh_token(body.refresh_token)
        access, new_refresh, _ = await service.refresh(jti, user_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))
    return RefreshTokenResponse(access_token=access, refresh_token=new_refresh)


@auth_router.post("/auth/logout", response_model=MessageResponse)
async def logout(body: LogoutRequest, service: Annotated[AuthService, Depends(get_auth_service)]) -> MessageResponse:
    try:
        jti, user_id = service.decode_refresh_token(body.refresh_token)
        await service.logout(jti, user_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))
    return MessageResponse(message="Logged out successfully")


@auth_router.post("/auth/logout-all", response_model=MessageResponse)
async def logout_all(
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> MessageResponse:
    count = await service.revoke_all_sessions(current_user.id)
    return MessageResponse(message=f"Revoked {count} active sessions")


@auth_router.post("/auth/forgot-password", response_model=ForgotPasswordResponse)
async def forgot_password(body: ForgotPasswordRequest, service: Annotated[AuthService, Depends(get_auth_service)], settings: Annotated[Settings, Depends(get_settings)]) -> ForgotPasswordResponse:
    token = await service.forgot_password(email=body.email)
    reset_url = None
    if token is not None:
        reset_url = f"{settings.frontend_url.rstrip('/')}/reset-password?token={token}"
    return ForgotPasswordResponse(message="If the email exists, a password reset link has been sent", reset_url=reset_url)


@auth_router.post("/auth/reset-password", response_model=MessageResponse)
async def reset_password(body: ResetPasswordRequest, service: Annotated[AuthService, Depends(get_auth_service)]) -> MessageResponse:
    try:
        await service.reset_password(token=body.token, new_password=body.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return MessageResponse(message="Password reset successfully")


@auth_router.post("/auth/send-verification", response_model=SendVerificationResponse)
async def send_verification(body: SendVerificationRequest, service: Annotated[AuthService, Depends(get_auth_service)], settings: Annotated[Settings, Depends(get_settings)]) -> SendVerificationResponse:
    result = await service.get_user_for_verification(email=body.email)
    if result is None:
        return SendVerificationResponse(message="If the email exists, a verification link has been sent")
    user, token = result
    verification_url = f"{settings.frontend_url.rstrip('/')}/verify-email?token={token}"
    return SendVerificationResponse(message="Verification email sent", verification_url=verification_url)


@auth_router.post("/auth/verify-email", response_model=MessageResponse)
async def verify_email(body: VerifyEmailRequest, service: Annotated[AuthService, Depends(get_auth_service)]) -> MessageResponse:
    try:
        await service.verify_email(token=body.token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return MessageResponse(message="Email verified successfully")


@auth_router.get("/auth/me", response_model=RegisterResponse)
async def get_me(current_user: Annotated[User, Depends(get_current_active_user)]) -> RegisterResponse:
    return RegisterResponse(id=current_user.id, email=current_user.email, role=current_user.role, is_active=current_user.is_active, is_verified=current_user.is_verified)
