from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from titan_x.api.dependencies import (
    get_auth_service,
    get_brute_force_protector,
    get_current_active_user,
    get_current_user,
    get_rate_limiter,
    require_api_key,
)
from titan_x.api.schemas import (
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    LogoutRequest,
    MessageResponse,
    RefreshTokenRequest,
    RefreshTokenResponse,
    RegisterRequest,
    RegisterResponse,
    ResetPasswordRequest,
    TokenResponse,
    VerifyEmailRequest,
)
from titan_x.core.config import Settings, get_settings
from titan_x.infrastructure.brute_force_protection import BruteForceProtector
from titan_x.infrastructure.rate_limiter import RateLimiter
from titan_x.models.user import User
from titan_x.services.auth_service import AuthService

auth_router = APIRouter(tags=["auth"])


@auth_router.post("/auth/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> RegisterResponse:
    try:
        user = await service.register(email=body.email, password=body.password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return RegisterResponse(id=user.id, email=user.email, role=user.role, is_active=user.is_active, is_verified=user.is_verified)


@auth_router.post("/auth/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
    rate_limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
    brute_force: Annotated[BruteForceProtector, Depends(get_brute_force_protector)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenResponse:
    if settings.rate_limit_enabled:
        allowed, remaining, _ = await rate_limiter.check(f"login:{body.email}", settings.rate_limit_requests, settings.rate_limit_window_seconds)
        if not allowed:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many requests")

    blocked = await brute_force.is_blocked(body.email, settings.brute_force_max_attempts, settings.brute_force_window_minutes, settings.brute_force_block_minutes)
    if blocked:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Account temporarily blocked. Try again later.")

    try:
        _, access, refresh, _ = await service.login(email=body.email, password=body.password)
    except ValueError as exc:
        if settings.rate_limit_enabled:
            await brute_force.record_failure_sorted(body.email, settings.brute_force_max_attempts, settings.brute_force_window_minutes, settings.brute_force_block_minutes)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))

    await brute_force.reset_attempts(body.email)
    return TokenResponse(access_token=access, refresh_token=refresh)


@auth_router.post("/auth/refresh", response_model=RefreshTokenResponse)
async def refresh(
    body: RefreshTokenRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> RefreshTokenResponse:
    try:
        access, new_refresh, _ = await service.refresh(body.access_token, current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))
    return RefreshTokenResponse(access_token=access, refresh_token=new_refresh)


@auth_router.post("/auth/logout", response_model=MessageResponse)
async def logout(
    body: LogoutRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> MessageResponse:
    await service.logout(body.refresh_token, current_user.id)
    return MessageResponse(message="Logged out successfully")


@auth_router.post("/auth/forgot-password", response_model=ForgotPasswordResponse)
async def forgot_password(
    body: ForgotPasswordRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> ForgotPasswordResponse:
    await service.forgot_password(email=body.email)
    return ForgotPasswordResponse(
        message="If the email exists, a password reset link has been sent"
    )


@auth_router.post("/auth/reset-password", response_model=MessageResponse)
async def reset_password(
    body: ResetPasswordRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> MessageResponse:
    try:
        await service.reset_password(token=body.token, new_password=body.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return MessageResponse(message="Password reset successfully")


@auth_router.post("/auth/verify-email", response_model=MessageResponse)
async def verify_email(
    body: VerifyEmailRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> MessageResponse:
    try:
        await service.verify_email(token=body.token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return MessageResponse(message="Email verified successfully")


@auth_router.get("/auth/me", response_model=RegisterResponse)
async def get_me(
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> RegisterResponse:
    return RegisterResponse(
        id=current_user.id,
        email=current_user.email,
        role=current_user.role,
        is_active=current_user.is_active,
        is_verified=current_user.is_verified,
    )
