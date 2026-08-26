import hmac
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response

from titan_x.api.dependencies import get_qr_auth_service
from titan_x.api.schemas import QRChallengeRequest, QRCreateResponse, QRLoginRequest, QRRegistrationCreateResponse, QRRegistrationRequest, QRSMSWebhookRequest, QRStatusResponse, RegisterResponse
from titan_x.core.audit import audit_event_later
from titan_x.core.config import Settings, get_settings
from titan_x.infrastructure.rate_limiter import RateLimiter
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


async def _set_browser_cookie(response: Response, request: Request, browser_session: str, settings: Settings) -> None:
    response.set_cookie(QRAuthService.BROWSER_COOKIE, browser_session, max_age=QRAuthService.CHALLENGE_TTL_SECONDS + 30, httponly=True, secure=request.url.scheme == "https" or settings.environment == "production", samesite="lax", path="/api/v1/auth/qr")


@router.post("/auth/qr/create", response_model=QRCreateResponse)
async def create_qr(body: QRLoginRequest, request: Request, response: Response, settings: Annotated[Settings, Depends(get_settings)], service: Annotated[QRAuthService, Depends(get_qr_auth_service)]) -> QRCreateResponse:
    await _check_rate(request, settings, "create", 10)
    browser_session = service.create_browser_session()
    try:
        challenge, raw = await service.create_login_challenge(body.identifier, browser_session, request.client.host if request.client else None, request.headers.get("User-Agent"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await _set_browser_cookie(response, request, browser_session, settings)
    audit_event_later(request, action="LOGIN_QR_CREATED", entity_type="auth_challenge", category="security", severity="info")
    return QRCreateResponse(challenge_id=challenge.challenge_id, qr_data_url=service._qr(raw, "LOGIN"), expires_at=challenge.expires_at, expires_in_seconds=service.CHALLENGE_TTL_SECONDS, sms_number=settings.qr_sms_number)


@router.post("/auth/qr/register/create", response_model=QRRegistrationCreateResponse)
async def create_registration_qr(body: QRRegistrationRequest, request: Request, response: Response, settings: Annotated[Settings, Depends(get_settings)], service: Annotated[QRAuthService, Depends(get_qr_auth_service)]) -> QRRegistrationCreateResponse:
    await _check_rate(request, settings, "register", 5)
    browser_session = service.create_browser_session()
    try:
        challenge, raw = await service.create_registration_challenge(body.username, body.password, body.confirm_password, body.email, body.phone, browser_session, request.client.host if request.client else None, request.headers.get("User-Agent"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await _set_browser_cookie(response, request, browser_session, settings)
    audit_event_later(request, action="LOGIN_QR_CREATED", entity_type="registration_challenge", category="security", severity="info")
    return QRRegistrationCreateResponse(challenge_id=challenge.challenge_id, qr_data_url=service._qr(raw, "REGISTRATION"), expires_at=challenge.expires_at, expires_in_seconds=service.CHALLENGE_TTL_SECONDS, sms_number=settings.qr_sms_number)


@router.post("/auth/qr/sms/webhook", response_model=dict)
async def sms_webhook(body: QRSMSWebhookRequest, request: Request, settings: Annotated[Settings, Depends(get_settings)], service: Annotated[QRAuthService, Depends(get_qr_auth_service)], x_qr_sms_signature: str | None = Header(default=None)) -> dict:
    await _check_rate(request, settings, "sms-webhook", 60)
    if not service.verify_webhook(body.from_number, body.body, x_qr_sms_signature):
        raise HTTPException(status_code=401, detail="Invalid SMS webhook signature")
    message = body.body.strip()
    if not message.startswith(QRAuthService.SMS_PREFIX):
        raise HTTPException(status_code=400, detail="Unsupported SMS verification message")
    raw = message[len(QRAuthService.SMS_PREFIX):].strip()
    try:
        challenge = await service.sms_approve(raw, body.from_number)
    except ValueError as exc:
        audit_event_later(request, action="LOGIN_QR_FAILED", entity_type="auth_challenge", category="security", severity="warning")
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit_event_later(request, action="LOGIN_QR_APPROVED", entity_type="auth_challenge", category="security", severity="info", user_id=challenge.customer_id)
    return {"status": "approved"}


@router.get("/auth/qr/status/{challenge_id}", response_model=QRStatusResponse)
async def qr_status(challenge_id: str, request: Request, service: Annotated[QRAuthService, Depends(get_qr_auth_service)]) -> QRStatusResponse:
    browser_session = request.cookies.get(QRAuthService.BROWSER_COOKIE)
    if not browser_session:
        raise HTTPException(status_code=401, detail="QR browser session missing")
    try:
        state, user, tokens = await service.status_and_consume(challenge_id, browser_session)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if tokens and user:
        access, refresh = tokens
        return QRStatusResponse(status="USED", access_token=access, refresh_token=refresh, user=RegisterResponse(id=user.id, email=user.email, role=user.role, is_active=user.is_active, is_verified=user.is_verified))
    return QRStatusResponse(status=state)


@router.post("/auth/qr/cancel")
async def cancel_qr(body: QRChallengeRequest, request: Request, service: Annotated[QRAuthService, Depends(get_qr_auth_service)]) -> dict:
    browser_session = request.cookies.get(QRAuthService.BROWSER_COOKIE)
    if not browser_session:
        raise HTTPException(status_code=401, detail="QR browser session missing")
    try:
        await service.cancel(body.challenge_id, browser_session)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"message": "QR login cancelled"}
