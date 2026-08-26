from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from titan_x.api.dependencies import get_current_active_user, get_qr_auth_service
from titan_x.api.schemas import (
    MessageResponse,
    QRApproveRequest,
    QRChallengeRequest,
    QRCreateResponse,
    QRDeviceRegisterRequest,
    QRDeviceResponse,
    QRScanRequest,
    QRStatusResponse,
    RegisterResponse,
)
from titan_x.core.audit import audit_event_later
from titan_x.core.config import Settings, get_settings
from titan_x.infrastructure.rate_limiter import RateLimiter
from titan_x.models.user import User
from titan_x.services.qr_auth_service import QRAuthService

router = APIRouter(tags=["qr-auth"])


def _rate_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


async def _check_rate(request: Request, settings: Settings, suffix: str, limit: int) -> None:
    if not settings.rate_limit_enabled:
        return
    redis = getattr(request.app.state, "redis", None)
    if redis is None:
        return
    allowed, _, _ = await RateLimiter(redis).check(f"qr:{suffix}:{_rate_key(request)}", limit, 60)
    if not allowed:
        raise HTTPException(status_code=429, detail="Too many QR authentication requests")


@router.post("/auth/qr/create", response_model=QRCreateResponse)
async def create_qr(
    request: Request,
    response: Response,
    settings: Annotated[Settings, Depends(get_settings)],
    service: Annotated[QRAuthService, Depends(get_qr_auth_service)],
) -> QRCreateResponse:
    await _check_rate(request, settings, "create", 10)
    browser_session = service.create_browser_session()
    challenge, _, qr_data_url = await service.create_challenge(
        browser_session, request.client.host if request.client else None, request.headers.get("User-Agent")
    )
    response.set_cookie(
        QRAuthService.BROWSER_COOKIE,
        browser_session,
        max_age=QRAuthService.CHALLENGE_TTL_SECONDS + 30,
        httponly=True,
        secure=request.url.scheme == "https" or settings.environment == "production",
        samesite="lax",
        path="/api/v1/auth/qr",
    )
    audit_event_later(request, action="LOGIN_QR_CREATED", entity_type="auth_challenge", details={"challenge_id": "redacted"}, category="security", severity="info")
    return QRCreateResponse(challenge_id=challenge.challenge_id, qr_data_url=qr_data_url, expires_at=challenge.expires_at, expires_in_seconds=QRAuthService.CHALLENGE_TTL_SECONDS)


@router.get("/auth/qr/status/{challenge_id}", response_model=QRStatusResponse)
async def qr_status(
    challenge_id: str,
    request: Request,
    service: Annotated[QRAuthService, Depends(get_qr_auth_service)],
) -> QRStatusResponse:
    browser_session = request.cookies.get(QRAuthService.BROWSER_COOKIE)
    if not browser_session:
        raise HTTPException(status_code=401, detail="QR browser session missing")
    try:
        state, user, tokens = await service.status_and_consume(challenge_id, browser_session)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if tokens and user:
        access, refresh = tokens
        audit_event_later(request, action="LOGIN_QR_APPROVED", entity_type="auth_challenge", entity_id=user.id, category="security", severity="info")
        return QRStatusResponse(status="USED", access_token=access, refresh_token=refresh, user=RegisterResponse(id=user.id, email=user.email, role=user.role, is_active=user.is_active, is_verified=user.is_verified))
    return QRStatusResponse(status=state)


@router.post("/auth/qr/cancel", response_model=MessageResponse)
async def cancel_qr(
    body: QRChallengeRequest,
    request: Request,
    service: Annotated[QRAuthService, Depends(get_qr_auth_service)],
) -> MessageResponse:
    browser_session = request.cookies.get(QRAuthService.BROWSER_COOKIE)
    if not browser_session:
        raise HTTPException(status_code=401, detail="QR browser session missing")
    try:
        await service.cancel(body.challenge_id, browser_session)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit_event_later(request, action="LOGIN_QR_CANCELLED", entity_type="auth_challenge", category="security", severity="info")
    return MessageResponse(message="QR login cancelled")


@router.post("/auth/qr/scan", response_model=MessageResponse)
async def scan_qr(
    body: QRScanRequest,
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[QRAuthService, Depends(get_qr_auth_service)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> MessageResponse:
    await _check_rate(request, settings, "scan", 20)
    try:
        await service.scan(body.challenge_id, current_user, body.device_id)
    except ValueError as exc:
        audit_event_later(request, action="LOGIN_QR_FAILED", entity_type="auth_challenge", category="security", severity="warning", user_id=current_user.id)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit_event_later(request, action="LOGIN_QR_SCANNED", entity_type="auth_challenge", category="security", severity="info", user_id=current_user.id)
    return MessageResponse(message="Login request scanned. Awaiting approval.")


@router.post("/auth/qr/approve", response_model=MessageResponse)
async def approve_qr(
    body: QRApproveRequest,
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[QRAuthService, Depends(get_qr_auth_service)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> MessageResponse:
    await _check_rate(request, settings, "approve", 10)
    try:
        await service.approve(body.challenge_id, current_user, body.device_id, body.signature)
    except ValueError as exc:
        audit_event_later(request, action="LOGIN_QR_FAILED", entity_type="auth_challenge", category="security", severity="warning", user_id=current_user.id)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit_event_later(request, action="LOGIN_QR_APPROVED", entity_type="auth_challenge", category="security", severity="info", user_id=current_user.id)
    return MessageResponse(message="Login approved")


@router.post("/auth/qr/decline", response_model=MessageResponse)
async def decline_qr(
    body: QRChallengeRequest,
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[QRAuthService, Depends(get_qr_auth_service)],
) -> MessageResponse:
    try:
        await service.decline(body.challenge_id, current_user, body.device_id if hasattr(body, "device_id") else 0)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit_event_later(request, action="LOGIN_QR_DECLINED", entity_type="auth_challenge", category="security", severity="info", user_id=current_user.id)
    return MessageResponse(message="Login request declined")


@router.post("/auth/qr/devices", response_model=QRDeviceResponse, status_code=status.HTTP_201_CREATED)
async def register_device(
    body: QRDeviceRegisterRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[QRAuthService, Depends(get_qr_auth_service)],
) -> QRDeviceResponse:
    try:
        device = await service.register_device(current_user, body.device_name, body.public_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return QRDeviceResponse(id=device.id, device_name=device.device_name, device_status=device.device_status, created_at=device.created_at, last_seen_at=device.last_seen_at)
